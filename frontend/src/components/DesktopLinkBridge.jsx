import { useCallback, useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { isTauriRuntime } from "../utils/runtime";
import { parseInviteLink } from "../utils/appLinks";
import { buildAuthLink, getLocationPath } from "../utils/authRedirect";

export default function DesktopLinkBridge() {
  const { user, loading, startupError } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const navigateRef = useRef(navigate);
  const locationRef = useRef(getLocationPath(location));
  const authRef = useRef({ user: null, loading: true });
  const pendingRef = useRef(null);
  const flush = useCallback(() => {
    const auth = authRef.current;
    if (auth.loading || auth.startupError || !pendingRef.current) return;
    const destination = pendingRef.current;
    const target = auth.user ? destination : buildAuthLink("/login", destination);
    // A route guard can also navigate as startup finishes. Retain this request
    // until the router confirms arrival so its generic login redirect cannot
    // discard the invite destination.
    if (locationRef.current === target) { pendingRef.current = null; return; }
    navigateRef.current(target, { replace: true });
  }, []);

  useEffect(() => {
    navigateRef.current = navigate;
    locationRef.current = getLocationPath(location);
    authRef.current = { user, loading, startupError };
    flush();
  }, [user, loading, startupError, navigate, location, flush]);

  useEffect(() => {
    if (!isTauriRuntime()) return;
    let disposed = false;
    let unlisten;
    let readingStartup = true;
    const received = new Set();
    const accept = (urls, startup = false) => {
      if (disposed) return;
      if (startup && received.size) return;
      for (const url of urls || []) {
        if (startup && received.has(url)) continue;
        const path = parseInviteLink(url);
        if (!path) continue;
        if (readingStartup) received.add(url);
        pendingRef.current = path;
      }
      flush();
    };
    (async () => {
      const { getCurrent, onOpenUrl } = await import("@tauri-apps/plugin-deep-link");
      if (disposed) return;
      const stop = await onOpenUrl((urls) => accept(urls));
      if (disposed) { Promise.resolve(stop()).catch(() => {}); return; }
      unlisten = stop;
      accept(await getCurrent(), true);
      readingStartup = false;
    })().catch(() => {});
    return () => { disposed = true; Promise.resolve(unlisten?.()).catch(() => {}); };
  }, [flush]);
  return null;
}
