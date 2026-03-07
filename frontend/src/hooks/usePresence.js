import { useEffect, useRef } from "react";
import { presence } from "../api/client";

const HEARTBEAT_MS = 30_000;

export function usePresence(active) {
  const timer = useRef(null);

  useEffect(() => {
    if (!active) return;

    const beat = () => presence.heartbeat().catch(() => {});
    beat();
    timer.current = setInterval(beat, HEARTBEAT_MS);

    return () => {
      clearInterval(timer.current);
      presence.offline().catch(() => {});
    };
  }, [active]);
}
