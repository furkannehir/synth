import { useCallback, useEffect, useRef, useState } from "react";
import { listNativeCaptureSources } from "../utils/nativeScreenCapture";

export default function useNativeCaptureSources({ enabled = true, paused = false } = {}) {
  const [sources, setSources] = useState([]);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState("");
  const refreshRef = useRef(null);
  useEffect(() => {
    if (!enabled || paused) return;
    let disposed = false, pending = false;
    const refresh = async (quiet = false) => {
      if (disposed || pending) return;
      pending = true;
      if (!quiet) setLoading(true);
      try {
        const available = await listNativeCaptureSources();
        if (!disposed) { setSources(available); setError(""); }
      } catch (value) {
        if (!disposed) setError(String(value.message || value));
      } finally {
        pending = false;
        if (!disposed) setLoading(false);
      }
    };
    refreshRef.current = refresh;
    void refresh(true);
    const timer = setInterval(() => { void refresh(true); }, 2000);
    const onFocus = () => { void refresh(true); };
    window.addEventListener("focus", onFocus);
    return () => { disposed = true; refreshRef.current = null; clearInterval(timer); window.removeEventListener("focus", onFocus); };
  }, [enabled, paused]);
  const refresh = useCallback(() => refreshRef.current?.(), []);
  const refreshQuiet = useCallback(() => refreshRef.current?.(true), []);
  return { sources, loading, error, refresh, refreshQuiet };
}
