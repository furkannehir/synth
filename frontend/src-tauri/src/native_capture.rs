//! Windows screen capture. No screen data is written to disk.
use serde::Serialize;
use std::{
    collections::HashMap,
    sync::{Arc, Mutex},
    time::{Duration, Instant},
};
use tauri::{State, WebviewWindow};
use windows::Win32::{
    Foundation::HWND,
    Graphics::Dwm::{DwmGetWindowAttribute, DWMWA_CLOAKED},
    UI::WindowsAndMessaging::IsIconic,
};
use windows_capture::{
    capture::{CaptureControl, Context, GraphicsCaptureApiHandler},
    frame::Frame,
    graphics_capture_api::InternalCaptureControl,
    monitor::Monitor,
    settings::{
        ColorFormat, CursorCaptureSettings, DirtyRegionSettings, DrawBorderSettings,
        GraphicsCaptureItemType, MinimumUpdateIntervalSettings, SecondaryWindowSettings, Settings,
    },
    window::Window,
};

const FRAME_INTERVAL: Duration = Duration::from_millis(66);
const LEASE: Duration = Duration::from_secs(4);
const HEADER_BYTES: usize = 32;
const MAGIC: u32 = 0x50434e53; // SNCP, little endian
type CaptureError = Box<dyn std::error::Error + Send + Sync>;

#[derive(Serialize)]
pub struct Source {
    pub id: String,
    pub label: String,
    pub kind: &'static str,
}
#[derive(Clone, Copy)]
enum CaptureItem {
    Window { window: Window, process: u32 },
    Screen(Monitor),
}
struct ListedSource {
    item: CaptureItem,
    label: String,
}
#[derive(Default)]
struct Registry {
    sources: HashMap<String, ListedSource>,
    next_id: u64,
    active: Option<Arc<Session>>,
}
#[derive(Default)]
pub struct CaptureState(Mutex<Registry>);

struct Frames {
    latest: Option<Vec<u8>>,
    sequence: u32,
    last_poll: Instant,
    ended: bool,
    error: Option<String>,
}
struct Shared {
    frames: Mutex<Frames>,
    started: Instant,
}
struct Session {
    id: String,
    shared: Arc<Shared>,
    control: Mutex<Option<CaptureControl<Handler, CaptureError>>>,
}

impl Session {
    fn stop(&self) {
        if let Ok(mut frames) = self.shared.frames.lock() {
            frames.ended = true;
            frames.latest = None;
        }
        if let Ok(mut control) = self.control.lock() {
            if let Some(control) = control.take() {
                let _ = control.stop();
            }
        }
    }
}
impl CaptureState {
    pub fn stop_all(&self) {
        let active = self
            .0
            .lock()
            .ok()
            .and_then(|mut registry| registry.active.take());
        if let Some(active) = active {
            active.stop();
        }
    }
    pub fn list(&self) -> Result<Vec<Source>, String> {
        let mut registry = self.0.lock().map_err(|_| "Capture state unavailable")?;
        registry.sources.clear();
        let mut sources = Vec::new();
        for window in Window::enumerate().map_err(|error| error.to_string())? {
            let process = window.process_id().unwrap_or(0);
            let label = window.title().unwrap_or_default();
            if !is_shareable_window(window) {
                continue;
            }
            // Stable across list refreshes; start still requires a currently listed source.
            let id = format!("window-{:x}-{process}", window.as_raw_hwnd() as usize);
            registry.sources.insert(
                id.clone(),
                ListedSource {
                    item: CaptureItem::Window { window, process },
                    label: label.clone(),
                },
            );
            sources.push(Source {
                id,
                label,
                kind: "window",
            });
        }
        for (index, monitor) in Monitor::enumerate()
            .map_err(|error| error.to_string())?
            .into_iter()
            .enumerate()
        {
            let width = monitor.width().unwrap_or(0);
            let height = monitor.height().unwrap_or(0);
            if width == 0 || height == 0 {
                continue;
            }
            let id = format!("screen-{:x}", monitor.as_raw_hmonitor() as usize);
            let label = format!("Screen {} · {width} × {height}", index + 1);
            registry.sources.insert(
                id.clone(),
                ListedSource {
                    item: CaptureItem::Screen(monitor),
                    label: label.clone(),
                },
            );
            sources.push(Source {
                id,
                label,
                kind: "screen",
            });
        }
        sources.sort_by(|a, b| a.label.to_lowercase().cmp(&b.label.to_lowercase()));
        Ok(sources)
    }
    pub fn start(&self, source_id: &str) -> Result<StartedCapture, String> {
        let mut registry = self.0.lock().map_err(|_| "Capture state unavailable")?;
        let source = registry
            .sources
            .get(source_id)
            .ok_or("Refresh sources and choose a window or screen")?;
        let item = source.item;
        let label = source.label.clone();
        match item {
            CaptureItem::Window { window, process }
                if !is_shareable_window(window) || window.process_id().ok() != Some(process) =>
            {
                return Err(
                    "This window closed or is hidden. Refresh sources and choose another window"
                        .into(),
                )
            }
            CaptureItem::Screen(monitor)
                if !Monitor::enumerate()
                    .map_err(|error| error.to_string())?
                    .contains(&monitor) =>
            {
                return Err("This screen disconnected. Choose another source".into())
            }
            _ => {}
        }
        if let Some(previous) = registry.active.take() {
            previous.stop();
        }
        let shared = Arc::new(Shared {
            started: Instant::now(),
            frames: Mutex::new(Frames {
                latest: None,
                sequence: 0,
                last_poll: Instant::now(),
                ended: false,
                error: None,
            }),
        });
        let control = match item {
            CaptureItem::Window { window, .. } => {
                Handler::start_free_threaded(capture_settings(window, shared.clone()))
            }
            CaptureItem::Screen(monitor) => {
                Handler::start_free_threaded(capture_settings(monitor, shared.clone()))
            }
        }
        .map_err(|error| error.to_string())?;
        registry.next_id += 1;
        let id = format!("capture-{}", registry.next_id);
        let session = Arc::new(Session {
            id: id.clone(),
            shared,
            control: Mutex::new(Some(control)),
        });
        registry.active = Some(session.clone());
        std::thread::spawn(move || loop {
            std::thread::sleep(Duration::from_millis(500));
            let expired = session
                .shared
                .frames
                .lock()
                .map(|frames| frames.ended || frames.last_poll.elapsed() > LEASE)
                .unwrap_or(true);
            if expired {
                session.stop();
                break;
            }
        });
        Ok(StartedCapture {
            session_id: id,
            label,
        })
    }
    pub fn frame(&self, session_id: &str) -> Result<Vec<u8>, String> {
        let session = self
            .0
            .lock()
            .map_err(|_| "Capture state unavailable")?
            .active
            .clone()
            .filter(|session| session.id == session_id)
            .ok_or("Capture session ended")?;
        let mut frames = session
            .shared
            .frames
            .lock()
            .map_err(|_| "Capture frame unavailable")?;
        if let Some(error) = &frames.error {
            return Err(error.clone());
        }
        if frames.ended {
            return Err("The selected source closed or capture stopped".into());
        }
        frames.last_poll = Instant::now();
        Ok(frames.latest.take().unwrap_or_default())
    }
    pub fn stop(&self, session_id: &str) {
        let session = self.0.lock().ok().and_then(|mut registry| {
            if registry
                .active
                .as_ref()
                .is_some_and(|session| session.id == session_id)
            {
                registry.active.take()
            } else {
                None
            }
        });
        if let Some(session) = session {
            session.stop();
        }
    }
}
impl Drop for CaptureState {
    fn drop(&mut self) {
        self.stop_all();
    }
}

fn capture_settings<T: TryInto<GraphicsCaptureItemType>>(
    item: T,
    shared: Arc<Shared>,
) -> Settings<Arc<Shared>, T> {
    Settings::new(
        item,
        CursorCaptureSettings::Default,
        DrawBorderSettings::Default,
        SecondaryWindowSettings::Exclude,
        MinimumUpdateIntervalSettings::Default,
        DirtyRegionSettings::Default,
        ColorFormat::Rgba8,
        shared,
    )
}

fn is_input_helper(process_name: &str) -> bool {
    matches!(
        process_name
            .rsplit(['/', '\\'])
            .next()
            .unwrap_or("")
            .to_ascii_lowercase()
            .as_str(),
        "textinputhost.exe" | "inputapp.exe" | "tabtip.exe"
    )
}

fn window_is_offerable(
    valid: bool,
    minimized: bool,
    cloaked: u32,
    own_process: bool,
    input_helper: bool,
    has_title: bool,
) -> bool {
    valid && !minimized && cloaked == 0 && !own_process && !input_helper && has_title
}

fn is_shareable_window(window: Window) -> bool {
    let hwnd = HWND(window.as_raw_hwnd());
    let mut cloaked = 0u32;
    // WS_VISIBLE can remain set on suspended UWP windows that DWM hides.
    let cloak_query = unsafe {
        DwmGetWindowAttribute(
            hwnd,
            DWMWA_CLOAKED,
            (&mut cloaked as *mut u32).cast(),
            std::mem::size_of::<u32>() as u32,
        )
    };
    let process = window.process_id().unwrap_or(0);
    window_is_offerable(
        window.is_valid() && cloak_query.is_ok() && process != 0,
        unsafe { IsIconic(hwnd).as_bool() },
        cloaked,
        process == std::process::id(),
        is_input_helper(&window.process_name().unwrap_or_default()),
        !window.title().unwrap_or_default().trim().is_empty(),
    )
}

#[derive(Serialize)]
pub struct StartedCapture {
    pub session_id: String,
    pub label: String,
}
struct Handler {
    shared: Arc<Shared>,
    last_frame: Option<Instant>,
}
impl GraphicsCaptureApiHandler for Handler {
    type Flags = Arc<Shared>;
    type Error = CaptureError;
    fn new(context: Context<Self::Flags>) -> Result<Self, Self::Error> {
        Ok(Self {
            shared: context.flags,
            last_frame: None,
        })
    }
    fn on_frame_arrived(
        &mut self,
        frame: &mut Frame,
        control: InternalCaptureControl,
    ) -> Result<(), Self::Error> {
        if self
            .last_frame
            .is_some_and(|last| last.elapsed() < FRAME_INTERVAL)
        {
            return Ok(());
        }
        if self
            .shared
            .frames
            .lock()
            .map(|frames| frames.ended)
            .unwrap_or(true)
        {
            control.stop();
            return Ok(());
        }
        let began = Instant::now();
        let result = (|| -> Result<Vec<u8>, CaptureError> {
            let mut buffer = frame.buffer()?;
            let width = buffer.width();
            let height = buffer.height();
            let pitch = buffer.row_pitch() as usize;
            let sequence = self
                .shared
                .frames
                .lock()
                .map_err(|_| "Capture state unavailable")?
                .sequence
                .wrapping_add(1);
            let mut packet = pack_rgba(buffer.as_raw_buffer(), width, height, pitch, sequence)?;
            packet[16..24].copy_from_slice(
                &began
                    .elapsed()
                    .as_secs_f64()
                    .mul_add(1000.0, 0.0)
                    .to_le_bytes(),
            );
            packet[24..32].copy_from_slice(
                &(self.shared.started.elapsed().as_secs_f64() * 1000.0).to_le_bytes(),
            );
            Ok(packet)
        })();
        self.last_frame = Some(began);
        let mut frames = self
            .shared
            .frames
            .lock()
            .map_err(|_| "Capture state unavailable")?;
        if frames.ended {
            return Ok(());
        }
        match result {
            Ok(packet) => {
                frames.sequence = u32::from_le_bytes(packet[12..16].try_into().unwrap());
                frames.latest = Some(packet);
            }
            Err(error) => {
                frames.error = Some(error.to_string());
                frames.ended = true;
                control.stop();
            }
        }
        Ok(())
    }
    fn on_closed(&mut self) -> Result<(), Self::Error> {
        if let Ok(mut frames) = self.shared.frames.lock() {
            frames.ended = true;
            frames.latest = None;
        }
        Ok(())
    }
}

// Bounded CPU sampling keeps the transferred RGBA frame at or below 720p.
fn pack_rgba(
    raw: &[u8],
    width: u32,
    height: u32,
    pitch: usize,
    sequence: u32,
) -> Result<Vec<u8>, &'static str> {
    if width == 0
        || height == 0
        || pitch < width as usize * 4
        || raw.len() < pitch * height as usize
    {
        return Err("Invalid capture dimensions");
    }
    let scale = (1280.0 / f64::from(width))
        .min(720.0 / f64::from(height))
        .min(1.0);
    let target_width = ((f64::from(width) * scale) as u32).max(2) & !1;
    let target_height = ((f64::from(height) * scale) as u32).max(2) & !1;
    let mut packet = vec![0; HEADER_BYTES + target_width as usize * target_height as usize * 4];
    packet[0..4].copy_from_slice(&MAGIC.to_le_bytes());
    packet[4..8].copy_from_slice(&target_width.to_le_bytes());
    packet[8..12].copy_from_slice(&target_height.to_le_bytes());
    packet[12..16].copy_from_slice(&sequence.to_le_bytes());
    for y in 0..target_height as usize {
        let source_y = y * height as usize / target_height as usize;
        for x in 0..target_width as usize {
            let source = source_y * pitch + x * width as usize / target_width as usize * 4;
            let target = HEADER_BYTES + (y * target_width as usize + x) * 4;
            packet[target..target + 3].copy_from_slice(&raw[source..source + 3]);
            packet[target + 3] = 255;
        }
    }
    Ok(packet)
}

fn check_window(window: &WebviewWindow) -> Result<(), String> {
    if window.label() != "main"
        || !super::session_store::is_app_url(&window.url().map_err(|_| "Cannot verify app window")?)
    {
        return Err("Native capture is only available in the Synth app window".into());
    }
    Ok(())
}
#[tauri::command]
pub fn native_capture_list_sources(
    window: WebviewWindow,
    state: State<'_, CaptureState>,
) -> Result<Vec<Source>, String> {
    check_window(&window)?;
    state.list()
}
#[tauri::command]
pub async fn native_capture_start(
    window: WebviewWindow,
    state: State<'_, CaptureState>,
    source_id: String,
) -> Result<StartedCapture, String> {
    check_window(&window)?;
    state.start(&source_id)
}
#[tauri::command]
pub fn native_capture_frame(
    window: WebviewWindow,
    state: State<'_, CaptureState>,
    session_id: String,
) -> Result<tauri::ipc::Response, String> {
    check_window(&window)?;
    state.frame(&session_id).map(tauri::ipc::Response::new)
}
#[tauri::command]
pub async fn native_capture_stop(
    window: WebviewWindow,
    state: State<'_, CaptureState>,
    session_id: String,
) -> Result<(), String> {
    check_window(&window)?;
    state.stop(&session_id);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn background_shell_and_hidden_windows_are_not_offered() {
        assert!(window_is_offerable(true, false, 0, false, false, true));
        for cloaked in [1, 2, 4] {
            assert!(!window_is_offerable(
                true, false, cloaked, false, false, true
            ));
        }
        assert!(!window_is_offerable(true, true, 0, false, false, true));
        assert!(!window_is_offerable(true, false, 0, false, true, true));
        assert!(!window_is_offerable(false, false, 0, false, false, true));
        assert!(is_input_helper(
            "C:\\Windows\\SystemApps\\TextInputHost.exe"
        ));
        assert!(is_input_helper("INPUTAPP.EXE"));
        assert!(
            !is_input_helper("SystemSettings.exe"),
            "An actually visible Settings window remains shareable"
        );
    }
    #[test]
    fn pixel_packet_strips_padding_and_preserves_rgba_order() {
        let packet = pack_rgba(
            &[
                1, 2, 3, 0, 4, 5, 6, 0, 99, 99, 99, 99, 7, 8, 9, 0, 10, 11, 12, 0, 99, 99, 99, 99,
            ],
            2,
            2,
            12,
            7,
        )
        .unwrap();
        assert_eq!(
            &packet[32..],
            &[1, 2, 3, 255, 4, 5, 6, 255, 7, 8, 9, 255, 10, 11, 12, 255]
        );
        assert_eq!(u32::from_le_bytes(packet[12..16].try_into().unwrap()), 7);
    }
    #[test]
    fn packets_are_bounded_and_invalid_buffers_rejected() {
        let raw = vec![42; 2560 * 1440 * 4];
        let packet = pack_rgba(&raw, 2560, 1440, 2560 * 4, 1).unwrap();
        assert_eq!(packet.len(), 32 + 1280 * 720 * 4);
        assert!(pack_rgba(&[], 2, 2, 8, 0).is_err());
        assert!(pack_rgba(&[], 0, 0, 0, 0).is_err());
    }
}
