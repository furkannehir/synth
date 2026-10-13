import { useCallback, useEffect, useRef, useState } from "react";
import { Menu } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import ServerSidebar from "../components/ServerSidebar";
import ChannelList from "../components/ChannelList";
import VoicePanel from "../components/VoicePanel";
import VoiceRoomBanner from "../components/VoiceRoomBanner";
import TextPanel from "../components/TextPanel";
import MembersPanel from "../components/MembersPanel";
import FriendsPanel from "../components/FriendsPanel";
import DMPanel from "../components/DMPanel";
import { ServerPresenceProvider } from "../context/ServerPresenceContext";
import { dms as dmsApi } from "../api/client";

export default function HomePage() {
  const { user } = useAuth();
  const [activeServer, setActiveServer] = useState(null);
  const [activeChannel, setActiveChannel] = useState(null);
  const [activeFriend, setActiveFriend] = useState(null);
  const [channels, setChannels] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [membersOpen, setMembersOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const voiceRef = useRef(null);
  const serverIdRef = useRef(null);

  const selectServer = (server) => {
    serverIdRef.current = server?.id || null;
    setActiveServer(server); setActiveChannel(null); setChannels([]); setMembersOpen(false);
    if (server) setActiveFriend(null);
  };
  const selectFriend = (friend) => { selectServer(null); setActiveFriend(friend); setMobileOpen(false); };
  const selectChannel = (channel) => { if (channel.server_id !== serverIdRef.current) return; setActiveChannel(channel); setMobileOpen(false); };
  const onChannelsLoaded = useCallback((next, serverId) => {
    if (serverId !== serverIdRef.current) return;
    setChannels(next);
    setActiveChannel((current) => current || next.find(({ type }) => type === "text") || null);
  }, []);

  useEffect(() => {
    let active = true;
    const refresh = () => dmsApi.unreadCount().then(({ unread_count }) => { if (active) setUnreadCount(unread_count || 0); }).catch(() => {});
    refresh();
    const timer = setInterval(refresh, 15000);
    return () => { active = false; clearInterval(timer); };
  }, [user]);

  useEffect(() => {
    const onKey = (event) => { if (event.key === "Escape") { setMobileOpen(false); setMembersOpen(false); } };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <ServerPresenceProvider server={activeServer}>
      <div className="app-shell">
        <ServerSidebar activeServer={activeServer} onSelect={selectServer} onSelectFriend={selectFriend} globalUnreadCount={unreadCount} mobileOpen={mobileOpen} onClose={() => setMobileOpen(false)}>
          {activeServer ? <ChannelList key={activeServer.id} server={activeServer} activeChannel={activeChannel} onSelect={selectChannel} onChannelsLoaded={onChannelsLoaded} /> : <FriendsPanel onSelectFriend={selectFriend} activeFriend={activeFriend} />}
        </ServerSidebar>
        <main className="app-workspace">
          <div className="mobile-workspace-bar"><button className="icon-button" aria-label="Open navigation" aria-expanded={mobileOpen} onClick={() => setMobileOpen(true)}><Menu size={24} /></button><strong>{activeServer?.name || "Direct messages"}</strong></div>
          {!activeServer ? <DMPanel key={user?.id + ":" + (activeFriend?.id || "none")} friend={activeFriend} onFriendRemoved={(id) => setActiveFriend((selected) => selected?.id === id ? null : selected)} /> : <>
            {activeChannel?.type === "text" && <TextPanel channel={activeChannel} onToggleMembers={() => setMembersOpen((open) => !open)} membersOpen={membersOpen}>
              <VoiceRoomBanner channels={channels} onJoin={(room) => voiceRef.current?.join(room)} />
            </TextPanel>}
            <VoicePanel ref={voiceRef} activeChannel={activeChannel} onNavigate={setActiveChannel} />
          </>}
        </main>
        {activeServer && membersOpen && <div className="members-drawer"><MembersPanel server={activeServer} onClose={() => setMembersOpen(false)} /></div>}
      </div>
    </ServerPresenceProvider>
  );
}
