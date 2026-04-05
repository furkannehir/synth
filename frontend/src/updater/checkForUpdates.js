import { useState, useEffect } from "react";
import { isTauriRuntime } from "../utils/runtime";

/**
 * Forced-update hook.
 *
 * Returns { updating, status, progress } so the caller can render a
 * blocking overlay while the update downloads and installs.
 *
 * Flow:
 *   1. Check for updates on mount (only in Tauri runtime).
 *   2. If an update exists → download and install automatically.
 *   3. Relaunch the app once the install completes.
 *   4. The user cannot skip or dismiss the update.
 */
export function useForcedUpdate() {
  const [updating, setUpdating] = useState(false);
  const [status, setStatus] = useState("Checking for updates…");
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    if (!isTauriRuntime()) return;

    let cancelled = false;

    (async () => {
      try {
        const [{ check }, { relaunch }] = await Promise.all([
          import("@tauri-apps/plugin-updater"),
          import("@tauri-apps/plugin-process"),
        ]);

        const update = await check();

        if (!update || cancelled) return;

        // An update is available → force it
        setUpdating(true);
        setStatus(`Downloading Synth v${update.version}…`);

        let totalBytes = 0;
        let downloadedBytes = 0;

        await update.downloadAndInstall((event) => {
          switch (event.event) {
            case "Started":
              totalBytes = event.data.contentLength ?? 0;
              break;
            case "Progress":
              downloadedBytes += event.data.chunkLength;
              if (totalBytes > 0) {
                setProgress(Math.round((downloadedBytes / totalBytes) * 100));
              }
              break;
            case "Finished":
              setProgress(100);
              setStatus("Installing update…");
              break;
          }
        });

        setStatus("Restarting…");
        await relaunch();
      } catch (error) {
        console.error("Forced update failed:", error);
        // If the update check itself fails (e.g. network), let the user in
        // so the app is still usable when offline.
        setUpdating(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  return { updating, status, progress };
}
