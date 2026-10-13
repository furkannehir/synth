import { createContext, useContext, useState, useEffect, useCallback, useRef } from "react";
import { auth as authApi, presence, setToken, clearToken, getToken, desktopSession } from "../api/client";
import { SESSION_EXPIRED_EVENT } from "../api/session";
import { stopPresence } from "../api/presenceLifecycle";
import { usePresence } from "../hooks/usePresence";
import { TOKEN_CHANGED_EVENT } from "../api/tokenStore";
import { isTauriRuntime } from "../utils/runtime";
import { SessionChangedError } from "../api/desktopSession";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(() => isTauriRuntime() || Boolean(getToken()));
  const [startupError, setStartupError] = useState("");
  const [accessToken, setAccessToken] = useState(getToken);
  const operationRef = useRef(0);
  const retryAction = useRef("restore");
  usePresence(user, accessToken);

  const restoreSession = useCallback(async () => {
    const operation = ++operationRef.current;
    retryAction.current = "restore";
    setLoading(true);
    setStartupError("");
    try {
      const token = await desktopSession.restore();
      if (token) {
        const data = await authApi.me();
        if (operation === operationRef.current && (getToken() === token || (isTauriRuntime() && desktopSession.hasSession()))) setUser(data.user);
      }
    } catch (error) {
      if (operation === operationRef.current && error.status !== 401 && !(error instanceof SessionChangedError)) {
        setStartupError(typeof error === "string" ? error : error.message || "Unable to reconnect. Please retry.");
      }
    } finally {
      if (operation === operationRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    let disposed = false;
    const onExpired = () => { setUser(null); setStartupError(""); };
    const onTokenChanged = () => setAccessToken(getToken());
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    window.addEventListener(TOKEN_CHANGED_EVENT, onTokenChanged);
    Promise.resolve().then(() => { if (!disposed) restoreSession(); });
    return () => {
      disposed = true;
      window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
      window.removeEventListener(TOKEN_CHANGED_EVENT, onTokenChanged);
      operationRef.current += 1;
    };
  }, [restoreSession]);

  const login = useCallback(async (email, password) => {
    const operation = ++operationRef.current;
    const data = await authApi.login(email, password);
    if (operation !== operationRef.current) throw new SessionChangedError();
    setToken(data.access_token);
    const me = await authApi.me();
    if (operation !== operationRef.current || (getToken() !== data.access_token && !desktopSession.hasSession())) throw new SessionChangedError();
    setUser(me.user);
    return me;
  }, []);

  const register = useCallback(async (username, email, password) => {
    const operation = ++operationRef.current;
    await authApi.register(username, email, password);
    if (operation !== operationRef.current) throw new SessionChangedError();
    return login(email, password);
  }, [login]);

  const logout = useCallback(async () => {
    const operation = ++operationRef.current;
    retryAction.current = "logout";
    const token = getToken();
    if (token && !stopPresence(token)) presence.offline(token).catch(() => {});
    clearToken();
    setUser(null);
    setStartupError("");
    if (isTauriRuntime()) {
      setLoading(true);
      try { await desktopSession.logout(); }
      catch (error) {
        if (operation === operationRef.current) setStartupError(typeof error === "string" ? error : error.message || "Unable to finish signing out. Please retry.");
      } finally { if (operation === operationRef.current) setLoading(false); }
    }
  }, []);

  const retryStartup = useCallback(() => retryAction.current === "logout" ? logout() : restoreSession(), [logout, restoreSession]);

  return (
    <AuthContext.Provider value={{ user, loading, startupError, retryStartup, accessToken, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be inside AuthProvider");
  return ctx;
}
