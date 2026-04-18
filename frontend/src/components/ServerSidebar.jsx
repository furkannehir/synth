import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { servers as serversApi } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { useTheme } from "../context/ThemeContext";
import { isBrowserRuntime } from "../utils/runtime";
import { trackEvent } from "../utils/analytics";

export default function ServerSidebar({ activeServer, onSelect, globalUnreadCount }) {
  const { logout, user } = useAuth();
  const { theme, setTheme, availableThemes } = useTheme();
  const [showThemePicker, setShowThemePicker] = useState(false);
  const [serverList, setServerList] = useState([]);
  const [showCreateServer, setShowCreateServer] = useState(false);
  const [newServerName, setNewServerName] = useState("");
  const [createServerLoading, setCreateServerLoading] = useState(false);
  const [createServerError, setCreateServerError] = useState("");
  const showDesktopShortcut = isBrowserRuntime();

  const handleDesktopShortcutClick = () => {
    trackEvent("desktop_cta_clicked", {
      source: "sidebar",
      placement: "sidebar-shortcut",
    });
  };

  useEffect(() => {
    serversApi.list().then((data) => setServerList(data.servers || [])).catch(() => {});
  }, []);

  const resetCreateServerForm = () => {
    setNewServerName("");
    setCreateServerError("");
  };

  const openCreateServer = () => {
    resetCreateServerForm();
    setShowCreateServer(true);
  };

  const closeCreateServer = () => {
    resetCreateServerForm();
    setShowCreateServer(false);
  };

  const handleCreateServer = async (event) => {
    event.preventDefault();
    const name = newServerName.trim();
    if (!name) {
      return;
    }

    setCreateServerLoading(true);
    setCreateServerError("");
    try {
      const data = await serversApi.create(name);
      const createdServer = data.server;
      if (!createdServer) {
        throw new Error("Server could not be created");
      }

      setServerList((prev) => [...prev, createdServer]);
      onSelect(createdServer);
      closeCreateServer();
    } catch (error) {
      setCreateServerError(error.message || "Could not create server");
    } finally {
      setCreateServerLoading(false);
    }
  };

  return (
    <>
      <div className="w-[72px] bg-cyber-surface flex flex-col items-center py-3 gap-1.5 border-r border-cyber-border/60">
        {/* Logo */}
        <div className="tooltip-wrapper">
          <button
            onClick={() => onSelect(null)}
            className="w-12 h-12 rounded-2xl bg-gradient-to-br from-neon-cyan/20 to-neon-cyan/5
                     text-neon-cyan font-display font-bold
                     text-lg flex items-center justify-center hover:rounded-xl hover:from-neon-cyan/30 hover:to-neon-cyan/10
                     transition-all duration-300 cursor-pointer glow-cyan mb-1 relative"
          >
            S
            {globalUnreadCount > 0 && (
              <span className="absolute -top-1 -right-1 bg-neon-pink text-cyber-bg text-[10px] font-bold px-1.5 py-0.5 rounded-full border-2 border-cyber-surface">
                {globalUnreadCount > 99 ? "99+" : globalUnreadCount}
              </span>
            )}
          </button>
          <span className="tooltip">Home</span>
        </div>

        <div className="w-8 h-0.5 bg-gradient-to-r from-transparent via-cyber-border to-transparent rounded mb-0.5" />

        <div className="tooltip-wrapper">
          <button
            onClick={openCreateServer}
            className="w-12 h-12 rounded-2xl bg-cyber-panel text-neon-cyan/70 flex items-center justify-center
                     hover:rounded-xl hover:bg-neon-cyan/10 hover:text-neon-cyan hover:glow-cyan
                     transition-all duration-300 cursor-pointer text-2xl leading-none"
          >
            +
          </button>
          <span className="tooltip">Create Server</span>
        </div>

        {/* Server list */}
        <div className="flex-1 flex flex-col items-center gap-1.5 overflow-y-auto py-0.5">
          {serverList.map((s) => (
            <div key={s.id} className="tooltip-wrapper">
              <button
                onClick={() => onSelect(s)}
                className={`w-12 h-12 rounded-2xl flex items-center justify-center text-sm font-display
                          font-bold uppercase transition-all duration-300 cursor-pointer relative
                          ${
                            activeServer?.id === s.id
                              ? "rounded-xl bg-gradient-to-br from-neon-cyan/25 to-neon-cyan/10 text-neon-cyan glow-cyan"
                              : "bg-cyber-panel text-cyber-muted hover:rounded-xl hover:bg-cyber-hover hover:text-cyber-text"
                          }`}
              >
                {/* Active indicator bar */}
                {activeServer?.id === s.id && (
                  <span className="absolute left-[-10px] w-1 h-8 bg-neon-cyan rounded-r-full" />
                )}
                {s.icon ? (
                  <img src={s.icon} alt={s.name} className="w-8 h-8 rounded-full" />
                ) : (
                  s.name.slice(0, 2)
                )}
              </button>
              <span className="tooltip">{s.name}</span>
            </div>
          ))}
        </div>

        {/* Bottom section */}
        <div className="w-8 h-0.5 bg-gradient-to-r from-transparent via-cyber-border to-transparent rounded mb-1" />

        {/* User avatar */}
        <div className="tooltip-wrapper">
          <div className="w-10 h-10 rounded-full bg-neon-purple/15 border border-neon-purple/30
                        flex items-center justify-center text-xs font-display font-bold text-neon-purple
                        mb-1">
            {user?.username?.slice(0, 2)?.toUpperCase() || "??"}
          </div>
          <span className="tooltip">{user?.username || "User"}</span>
        </div>

        {/* Theme Picker */}
        <div className="tooltip-wrapper">
          <button
            onClick={() => setShowThemePicker(true)}
            className="mb-1 flex h-10 w-10 items-center justify-center rounded-xl bg-cyber-panel/60 text-neon-yellow/60 transition-all duration-300 hover:rounded-lg hover:bg-neon-yellow/10 hover:text-neon-yellow text-sm"
          >
            🎨
          </button>
          <span className="tooltip">Theme Picker</span>
        </div>

        {showDesktopShortcut && (
          <div className="tooltip-wrapper">
            <Link
              to="/download?src=sidebar"
              onClick={handleDesktopShortcutClick}
              className="mb-1 flex h-10 w-10 items-center justify-center rounded-xl bg-cyber-panel/60 text-neon-cyan/60 transition-all duration-300 hover:rounded-lg hover:bg-neon-cyan/10 hover:text-neon-cyan"
            >
              ⇩
            </Link>
            <span className="tooltip">Download Desktop</span>
          </div>
        )}

        {/* Logout */}
        <div className="tooltip-wrapper">
          <button
            onClick={logout}
            className="w-10 h-10 rounded-xl bg-cyber-panel/60 text-neon-red/50 flex items-center justify-center
                     hover:bg-neon-red/10 hover:text-neon-red hover:rounded-lg transition-all duration-300 cursor-pointer text-sm"
          >
            ⏻
          </button>
          <span className="tooltip">Logout</span>
        </div>
      </div>

      {showCreateServer && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-cyber-bg/70 px-4 backdrop-blur-sm">
          <div className="w-full max-w-sm rounded-xl border border-neon-cyan/30 bg-cyber-surface p-4 shadow-[0_0_30px_rgba(0,255,255,0.08)]">
            <h3 className="text-sm font-display font-bold uppercase tracking-[0.18em] text-neon-cyan">
              Create Server
            </h3>
            <p className="mt-1 text-xs text-cyber-muted">Start a new space and invite your team.</p>

            <form className="mt-3 space-y-3" onSubmit={handleCreateServer}>
              <input
                autoFocus
                value={newServerName}
                onChange={(event) => setNewServerName(event.target.value)}
                placeholder="Server name"
                maxLength={48}
                className="w-full rounded-lg border border-cyber-border/50 bg-cyber-panel/60 px-3 py-2 text-sm text-cyber-text outline-none transition focus:border-neon-cyan/60"
              />

              {createServerError && (
                <p className="text-[11px] text-neon-red/80">{createServerError}</p>
              )}

              <div className="flex items-center justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={closeCreateServer}
                  disabled={createServerLoading}
                  className="rounded-md border border-cyber-border px-3 py-1.5 text-[11px] font-display uppercase tracking-[0.16em] text-cyber-muted transition hover:border-cyber-muted/70 hover:text-cyber-text disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createServerLoading || !newServerName.trim()}
                  className="rounded-md border border-neon-cyan/40 bg-neon-cyan/10 px-3 py-1.5 text-[11px] font-display uppercase tracking-[0.16em] text-neon-cyan transition hover:bg-neon-cyan/20 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {createServerLoading ? "Creating..." : "Create"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showThemePicker && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-cyber-bg/70 px-4 backdrop-blur-sm">
          <div className="w-full max-w-sm rounded-xl border border-neon-cyan/30 bg-cyber-surface p-4 shadow-[0_0_30px_rgba(0,255,255,0.08)]">
            <h3 className="text-sm font-display font-bold uppercase tracking-[0.18em] text-neon-cyan mb-3">
              Appearance
            </h3>
            <div className="flex flex-col gap-2">
              {availableThemes.map((t) => (
                <button
                  key={t.id}
                  onClick={() => setTheme(t.id)}
                  className={`px-4 py-3 rounded-lg text-left text-sm font-display transition-all ${
                    theme === t.id
                      ? "bg-neon-cyan/20 border border-neon-cyan text-neon-cyan"
                      : "bg-cyber-panel border border-cyber-border/50 text-cyber-text hover:bg-cyber-hover hover:border-cyber-border"
                  }`}
                >
                  {t.name}
                </button>
              ))}
            </div>
            <div className="mt-4 flex justify-end">
               <button
                  type="button"
                  onClick={() => setShowThemePicker(false)}
                  className="rounded-md border border-cyber-border px-3 py-1.5 text-[11px] font-display uppercase tracking-[0.16em] text-cyber-muted transition hover:border-cyber-muted/70 hover:text-cyber-text"
                >
                  Done
                </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
