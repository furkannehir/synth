import { createContext, useContext, useState, useEffect, useCallback } from "react";
import { auth as authApi, presence, setToken, clearToken, getToken } from "../api/client";
import { SESSION_EXPIRED_EVENT } from "../api/session";
import { stopPresence } from "../api/presenceLifecycle";
import { usePresence } from "../hooks/usePresence";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(() => Boolean(getToken()));
  usePresence(user);

  useEffect(() => {
    let disposed = false;
    const onExpired = () => setUser(null);
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    const token = getToken();
    if (token) {
      authApi
        .me()
        .then((data) => {
          if (!disposed && getToken() === token) setUser(data.user);
        })
        .catch(() => {})
        .finally(() => { if (!disposed) setLoading(false); });
    }
    return () => {
      disposed = true;
      window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
    };
  }, []);

  const login = useCallback(async (email, password) => {
    const data = await authApi.login(email, password);
    setToken(data.access_token);
    const me = await authApi.me();
    if (getToken() === data.access_token) setUser(me.user);
    return me;
  }, []);

  const register = useCallback(async (username, email, password) => {
    await authApi.register(username, email, password);
    return login(email, password);
  }, [login]);

  const logout = useCallback(() => {
    const token = getToken();
    if (token && !stopPresence(token)) presence.offline(token).catch(() => {});
    clearToken();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be inside AuthProvider");
  return ctx;
}
