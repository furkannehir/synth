import { useEffect } from "react";
import { getToken, presence } from "../api/client";
import { startPresence } from "../api/presenceLifecycle";

export function usePresence(active, accessToken) {
  useEffect(() => {
    if (!active) return;
    const token = getToken();
    if (!token) return;
    return startPresence({ token, heartbeat: presence.heartbeat, offline: presence.offline });
  }, [active, accessToken]);
}
