import { useEffect, useRef, useState } from "react";
import { Maximize2, Minimize2 } from "lucide-react";
import { exitMediaFullscreen, toggleMediaFullscreen } from "../utils/mediaFullscreen";

export default function FullscreenVideo({ children, className = "", label = "video", disabled = false }) {
  const ref = useRef(null);
  const pending = useRef(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    const element = ref.current;
    const onChange = () => setFullscreen(document.fullscreenElement === element);
    const onKey = (event) => {
      if (event.key !== "Escape" || document.fullscreenElement !== element) return;
      event.preventDefault();
      event.stopPropagation();
      void exitMediaFullscreen(element).catch(() => {});
    };
    document.addEventListener("fullscreenchange", onChange);
    document.addEventListener("keydown", onKey, true);
    return () => { document.removeEventListener("fullscreenchange", onChange); document.removeEventListener("keydown", onKey, true); void exitMediaFullscreen(element).catch(() => {}); };
  }, []);
  const toggle = async () => {
    if (pending.current) return;
    pending.current = true;
    setError("");
    try { await toggleMediaFullscreen(ref.current); }
    catch (value) { setError(value.message || "Could not open fullscreen video. Please try again."); }
    finally { pending.current = false; }
  };
  return <div ref={ref} className={`fullscreen-video ${className}`}>
    {children}
    <button className="video-fullscreen-button" disabled={disabled} onClick={toggle} aria-label={fullscreen ? "Exit fullscreen" : `Expand ${label} to fullscreen`} title={fullscreen ? "Exit fullscreen" : "Fullscreen"}>
      {fullscreen ? <Minimize2 size={19} /> : <Maximize2 size={19} />}
    </button>
    {error && <p role="alert" className="video-fullscreen-error">{error}</p>}
  </div>;
}
