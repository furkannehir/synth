import { LocalVideoTrack, Track } from "livekit-client";
import { isTauriRuntime } from "./runtime";

const HEADER_BYTES = 32;
const FRAME_INTERVAL_MS = 67;
const FIRST_FRAME_TIMEOUT_MS = 8000;

export function isNativeScreenCaptureSupported() {
  return isTauriRuntime() && /Windows/i.test(window.navigator.userAgent);
}

async function nativeInvoke(command, args) {
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke(command, args);
}

export function listNativeCaptureSources() {
  return nativeInvoke("native_capture_list_sources");
}

export function decodeNativeFrame(value) {
  const bytes = value instanceof ArrayBuffer ? new Uint8Array(value) : ArrayBuffer.isView(value) ? new Uint8Array(value.buffer, value.byteOffset, value.byteLength) : Uint8Array.from(value);
  if (!bytes.length) return null;
  if (bytes.length < HEADER_BYTES) throw new Error("Incomplete native video frame");
  const header = new DataView(bytes.buffer, bytes.byteOffset, HEADER_BYTES);
  if (header.getUint32(0, true) !== 0x50434e53) throw new Error("Unknown native video frame format");
  const width = header.getUint32(4, true), height = header.getUint32(8, true);
  if (!width || !height || width > 1280 || height > 720 || bytes.length !== HEADER_BYTES + width * height * 4) throw new Error("Invalid native video frame size");
  return { width, height, sequence: header.getUint32(12, true), nativeMs: header.getFloat64(16, true), capturedMs: header.getFloat64(24, true), pixels: new Uint8ClampedArray(bytes.buffer, bytes.byteOffset + HEADER_BYTES, width * height * 4) };
}

export async function createNativeScreenTrack(sourceId, { invoke = nativeInvoke, signal } = {}) {
  if (signal?.aborted) throw new DOMException("Native preview cancelled", "AbortError");
  const session = await invoke("native_capture_start", { sourceId }).catch((error) => { throw error instanceof Error ? error : new Error(String(error)); });
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d", { alpha: false });
  let track, stream, timer, stopped = false, rejectFirst;
  const stop = () => {
    if (stopped) return;
    stopped = true;
    clearTimeout(timer);
    rejectFirst?.(new Error("Native preview stopped"));
    if (track) originalStop();
    else stream?.getTracks().forEach((mediaTrack) => mediaTrack.stop());
    void invoke("native_capture_stop", { sessionId: session.session_id }).catch(() => {});
    window.removeEventListener("pagehide", stop);
    signal?.removeEventListener("abort", stop);
  };
  let originalStop;
  try {
    if (signal?.aborted) throw new DOMException("Native preview cancelled", "AbortError");
    if (!context || typeof canvas.captureStream !== "function") throw new Error("Native video preview is unavailable in this WebView");
    canvas.width = 1280; canvas.height = 720;
    stream = canvas.captureStream(0);
    const raw = stream.getVideoTracks()[0];
    if (!raw || typeof raw.requestFrame !== "function") throw new Error("This WebView cannot stream native capture frames");
    raw.contentHint = "detail";
    track = new LocalVideoTrack(raw, undefined, true);
    track.source = Track.Source.ScreenShare;
    track.nativeCaptureLabel = session.label;
    originalStop = track.stop.bind(track);
    track.stop = stop;
    window.addEventListener("pagehide", stop);
    signal?.addEventListener("abort", stop, { once: true });

    const started = performance.now();
    let hasFrame = false;
    await new Promise((resolve, reject) => {
      rejectFirst = reject;
      const poll = async () => {
        if (stopped) return;
        const began = performance.now();
        try {
          const packet = await invoke("native_capture_frame", { sessionId: session.session_id });
          if (stopped) return;
          const frame = decodeNativeFrame(packet);
          if (frame) {
            if (canvas.width !== frame.width || canvas.height !== frame.height) { canvas.width = frame.width; canvas.height = frame.height; }
            context.putImageData(new ImageData(frame.pixels, frame.width, frame.height), 0, 0);
            raw.requestFrame();
            if (!hasFrame) { hasFrame = true; rejectFirst = null; resolve(); }
          } else if (!hasFrame && performance.now() - started > FIRST_FRAME_TIMEOUT_MS) {
            throw new Error("No frames received. Restore the selected window and try again.");
          }
        } catch (error) {
          if (stopped) return;
          const pending = rejectFirst;
          rejectFirst = null;
          stop();
          if (pending) pending(error);
          // MediaStreamTrack.stop does not itself dispatch ended; notify preview and LiveKit.
          raw.dispatchEvent(new Event("ended"));
          return;
        }
        timer = setTimeout(poll, Math.max(0, FRAME_INTERVAL_MS - (performance.now() - began)));
      };
      void poll();
    });
    return track;
  } catch (error) { stop(); throw error instanceof Error ? error : new Error(String(error)); }
}
