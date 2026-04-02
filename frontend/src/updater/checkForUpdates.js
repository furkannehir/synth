import { isTauriRuntime } from "../utils/runtime";

let hasCheckedForUpdates = false;

export async function checkForDesktopUpdatesOnStartup() {
  if (hasCheckedForUpdates || !isTauriRuntime()) {
    return;
  }
  hasCheckedForUpdates = true;

  try {
    const [{ check }, { relaunch }] = await Promise.all([
      import("@tauri-apps/plugin-updater"),
      import("@tauri-apps/plugin-process"),
    ]);

    const update = await check();
    if (!update) {
      return;
    }

    const shouldInstall = window.confirm(
      `A new Synth version (${update.version}) is available. Install and restart now?`
    );

    if (!shouldInstall) {
      return;
    }

    await update.downloadAndInstall();
    await relaunch();
  } catch (error) {
    console.error("Update check failed", error);
  }
}
