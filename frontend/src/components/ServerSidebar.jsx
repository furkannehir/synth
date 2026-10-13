import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Check, ChevronDown, ChevronRight, Download, LogOut, MessageCircle, Plus, Settings2, X } from "lucide-react";
import { servers as serversApi, friends as friendsApi } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { useTheme } from "../context/ThemeContext";
import { isBrowserRuntime } from "../utils/runtime";
import { trackEvent } from "../utils/analytics";
import Avatar from "./Avatar";
import Modal from "./Modal";

export default function ServerSidebar({ activeServer, onSelect, onSelectFriend, globalUnreadCount, mobileOpen, onClose, children }) {
  const { logout, user } = useAuth();
  const { theme, setTheme, availableThemes } = useTheme();
  const [serverList, setServerList] = useState([]);
  const [friends, setFriends] = useState([]);
  const [serverError, setServerError] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const [showThemePicker, setShowThemePicker] = useState(false);
  const [showCreateServer, setShowCreateServer] = useState(false);
  const [newServerName, setNewServerName] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  const switcherRef = useRef(null);

  useEffect(() => {
    let active = true;
    serversApi.list().then(({ servers }) => { if (active) setServerList(servers || []); })
      .catch((error) => { if (active) setServerError(error.message); });
    const loadFriends = () => friendsApi.list().then(({ friends }) => { if (active) setFriends(friends || []); }).catch(() => {});
    loadFriends();
    const timer = setInterval(loadFriends, 15000);
    return () => { active = false; clearInterval(timer); };
  }, []);

  useEffect(() => {
    if (!menuOpen) return;
    const closeOutside = (event) => { if (!switcherRef.current?.contains(event.target)) setMenuOpen(false); };
    const onKey = (event) => { if (event.key === "Escape") { setMenuOpen(false); switcherRef.current?.querySelector("button")?.focus(); } };
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("pointerdown", closeOutside); document.removeEventListener("keydown", onKey); };
  }, [menuOpen]);

  const chooseServer = (server) => { onSelect(server); setMenuOpen(false); onClose(); };
  const closeCreate = useCallback(() => { setShowCreateServer(false); setCreateError(""); setNewServerName(""); }, []);
  const closeAppearance = useCallback(() => setShowThemePicker(false), []);
  const createServer = async (event) => {
    event.preventDefault();
    const name = newServerName.trim();
    if (!name || creating) return;
    setCreating(true); setCreateError("");
    try {
      const { server } = await serversApi.create(name);
      if (!server) throw new Error("Server could not be created");
      setServerList((previous) => [...previous, server]);
      chooseServer(server); closeCreate();
    } catch (error) { setCreateError(error.message); }
    finally { setCreating(false); }
  };

  return (
    <>
      {mobileOpen && <button className="sidebar-backdrop" aria-label="Close navigation" onClick={onClose} />}
      <aside className={"app-sidebar " + (mobileOpen ? "is-open" : "")} aria-label="Navigation">
        <div className="sidebar-brand">
          <button onClick={() => chooseServer(null)} aria-label="Synth home"><img src="/synth-icon.png" alt="" /><span>Synth</span>{globalUnreadCount > 0 && <small className="unread-count" aria-label={`${globalUnreadCount} unread direct messages`}>{globalUnreadCount > 99 ? "99+" : globalUnreadCount}</small>}</button>
          <button className="icon-button mobile-nav-close" aria-label="Close navigation" onClick={onClose}><X size={23} /></button>
        </div>
        <div className="server-switcher" ref={switcherRef}>
          <button className="server-switch-button" aria-expanded={menuOpen} aria-label="Switch server" onClick={() => setMenuOpen((open) => !open)}>
            {activeServer ? <Avatar username={activeServer.name} avatar={activeServer.icon} /> : <span className="server-home-icon"><MessageCircle /></span>}
            <span>{activeServer?.name || "Direct messages"}</span><ChevronDown size={22} />
          </button>
          {menuOpen && <div className="server-menu">
            <button onClick={() => chooseServer(null)}><MessageCircle size={20} />Direct messages{!activeServer && <Check size={18} />}</button>
            {serverList.map((server) => <button key={server.id} onClick={() => chooseServer(server)}><Avatar username={server.name} avatar={server.icon} /><span>{server.name}</span>{server.id === activeServer?.id && <Check size={18} />}</button>)}
            {serverError && <p role="alert">{serverError}</p>}
            <button onClick={() => { setMenuOpen(false); setShowCreateServer(true); }}><Plus size={20} />Create a server</button>
          </div>}
        </div>
        <div className="sidebar-scroll">
          {activeServer && <section className="direct-nav">
            <div className="sidebar-section-title"><button onClick={() => chooseServer(null)}>Direct messages{globalUnreadCount > 0 && <span className="unread-count">{globalUnreadCount}</span>}</button><button className="icon-button" aria-label="Open friends" onClick={() => chooseServer(null)}><Plus size={21} /></button></div>
            {friends.slice(0, 3).map((friend) => <button className="direct-nav-row" key={friend.id} onClick={() => { onSelectFriend(friend); onClose(); }}><Avatar username={friend.username} avatar={friend.avatar} online={friend.is_online} /><span>{friend.username}</span><ChevronRight size={19} /></button>)}
            {friends.length === 0 && <button className="sidebar-muted-link" onClick={() => chooseServer(null)}>Find your friends</button>}
          </section>}
          {children}
        </div>
        <footer className="sidebar-profile">
          <Avatar username={user?.username} avatar={user?.avatar} online />
          <div><strong>{user?.username}</strong><span>Your account</span></div>
          <button className="icon-button" aria-label="Appearance" title="Appearance" onClick={() => setShowThemePicker(true)}><Settings2 size={23} /></button>
          <button className="icon-button" aria-label="Log out" title="Log out" onClick={logout}><LogOut size={21} /></button>
        </footer>
        {isBrowserRuntime() && <Link className="desktop-download-link" to="/download?src=sidebar" onClick={() => trackEvent("desktop_cta_clicked", { source: "sidebar", placement: "sidebar-shortcut" })}><Download size={16} />Get Synth for desktop</Link>}
      </aside>
      {showCreateServer && <Modal title="Create a server" id="create-server-title" onClose={closeCreate}>
        <p className="modal-description">A place for your people and conversations.</p>
        <form onSubmit={createServer} className="app-form"><label>Server name<input autoFocus required value={newServerName} onChange={(event) => setNewServerName(event.target.value)} maxLength={64} placeholder="Your community" /></label>
          {createError && <p role="alert" className="form-error">{createError}</p>}
          <button className="primary-button" disabled={creating || !newServerName.trim()}>{creating ? "Creating…" : "Create server"}</button>
        </form>
      </Modal>}
      {showThemePicker && <Modal title="Appearance" id="appearance-title" onClose={closeAppearance}>
        <p className="modal-description">Make yourself at home. Your choice is saved on this device.</p>
        <fieldset className="theme-options"><legend className="sr-only">Color theme</legend>
          {availableThemes.map((option) => <label className={"theme-option " + (theme === option.id ? "is-selected" : "")} key={option.id}>
            <input type="radio" name="appearance" value={option.id} checked={theme === option.id} onChange={() => setTheme(option.id)} />
            <span className="theme-swatches" aria-hidden="true">{option.swatches.map((color) => <span key={color} style={{ backgroundColor: color }} />)}</span>
            <span><strong>{option.name}</strong><small>{option.description}</small></span>
            {theme === option.id && <Check size={20} aria-hidden="true" />}
          </label>)}
        </fieldset>
        <button className="primary-button modal-done" onClick={closeAppearance}>Done</button>
      </Modal>}
    </>
  );
}
