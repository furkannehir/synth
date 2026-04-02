import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { servers as serversApi } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { isBrowserRuntime } from "../utils/runtime";
import { trackEvent } from "../utils/analytics";

export default function ServerSidebar({ activeServer, onSelect }) {
  const { logout, user } = useAuth();
  const [serverList, setServerList] = useState([]);
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

  return (
    <div className="w-[72px] bg-cyber-surface flex flex-col items-center py-3 gap-1.5 border-r border-cyber-border/60">
      {/* Logo */}
      <div className="tooltip-wrapper">
        <button
          onClick={() => onSelect(null)}
          className="w-12 h-12 rounded-2xl bg-gradient-to-br from-neon-cyan/20 to-neon-cyan/5
                     text-neon-cyan font-display font-bold
                     text-lg flex items-center justify-center hover:rounded-xl hover:from-neon-cyan/30 hover:to-neon-cyan/10
                     transition-all duration-300 cursor-pointer glow-cyan mb-1"
        >
          S
        </button>
        <span className="tooltip">Home</span>
      </div>

      <div className="w-8 h-0.5 bg-gradient-to-r from-transparent via-cyber-border to-transparent rounded mb-0.5" />

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
  );
}
