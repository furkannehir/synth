#[cfg(windows)]
pub mod native_capture;
mod session_store;
use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let builder = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.unminimize();
                let _ = window.show();
                let _ = window.set_focus();
            }
        }))
        .plugin(tauri_plugin_deep_link::init())
        .plugin(
            tauri::plugin::Builder::<tauri::Wry>::new("navigation-guard")
                .on_navigation(|_webview, url| session_store::is_app_url(url))
                .build(),
        )
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .setup(|app| {
            #[cfg(any(target_os = "linux", all(debug_assertions, windows)))]
            {
                use tauri_plugin_deep_link::DeepLinkExt;
                if let Err(error) = app.deep_link().register_all() {
                    log::warn!("Could not register desktop deep links: {error}");
                }
            }
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }
            Ok(())
        })
        .manage(session_store::SessionStore::default());
    #[cfg(windows)]
    let builder = builder
        .manage(native_capture::CaptureState::default())
        .on_window_event(|window, event| {
            if matches!(event, tauri::WindowEvent::Destroyed) && window.label() == "main" {
                window.state::<native_capture::CaptureState>().stop_all();
            }
        })
        .invoke_handler(tauri::generate_handler![
            session_store::read_desktop_session,
            session_store::write_desktop_session,
            native_capture::native_capture_list_sources,
            native_capture::native_capture_start,
            native_capture::native_capture_frame,
            native_capture::native_capture_stop
        ]);
    #[cfg(not(windows))]
    let builder = builder.invoke_handler(tauri::generate_handler![
        session_store::read_desktop_session,
        session_store::write_desktop_session
    ]);
    builder
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
