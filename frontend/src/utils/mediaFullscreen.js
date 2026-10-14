import { getCurrentWindow } from "@tauri-apps/api/window";
import { isTauriRuntime } from "./runtime";

let listeningDocument, desktopSession, desktopOpening;
let syncQueue = Promise.resolve();

function prepareDesktopFullscreen() {
  if (!isTauriRuntime() || desktopSession || desktopOpening) return;
  const window = getCurrentWindow();
  // Read this state before DOM fullscreen can change the native window.
  desktopOpening = { window, state: window.isFullscreen().then((value) => ({ value }), (error) => ({ error })) };
}

function syncDesktopWindow() {
  syncQueue = syncQueue.catch(() => {}).then(async () => {
    if (!isTauriRuntime()) return;
    if (document.fullscreenElement) {
      if (desktopSession) return;
      prepareDesktopFullscreen();
      const opening = desktopOpening;
      try {
        const state = await opening.state;
        if (state.error) throw state.error;
        if (!document.fullscreenElement) return;
        await opening.window.setFullscreen(true);
        desktopSession = { window: opening.window, wasFullscreen: state.value };
      } finally {
        if (desktopOpening === opening) desktopOpening = null;
      }
    } else {
      desktopOpening = null;
      if (desktopSession) {
        const session = desktopSession; desktopSession = null;
        await session.window.setFullscreen(session.wasFullscreen);
      }
    }
  });
  return syncQueue;
}

export async function toggleMediaFullscreen(element) {
  if (document.fullscreenElement === element) return exitMediaFullscreen(element);
  if (!element?.requestFullscreen) throw new Error("Fullscreen video is unavailable in this browser.");
  if (listeningDocument !== document) {
    listeningDocument = document;
    document.addEventListener("fullscreenchange", () => { void syncDesktopWindow().catch(() => {}); });
  }
  try {
    prepareDesktopFullscreen();
    const opening = desktopOpening;
    if (opening) {
      const state = await opening.state;
      if (desktopOpening !== opening) return;
      if (state.error) throw state.error;
    }
    // Browser requests run directly from the click. Desktop first snapshots its
    // native window while the WebView's transient user activation remains active.
    await element.requestFullscreen();
    await syncDesktopWindow();
  } catch (error) {
    if (document.fullscreenElement === element) await document.exitFullscreen().catch(() => {});
    await syncDesktopWindow().catch(() => {});
    throw error;
  }
}

export async function exitMediaFullscreen(element) {
  if (document.fullscreenElement === element) await document.exitFullscreen();
  await syncDesktopWindow();
}
