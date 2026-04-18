import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { usePresence } from "../hooks/usePresence";
import ServerSidebar from "../components/ServerSidebar";
import ChannelList from "../components/ChannelList";
import VoicePanel from "../components/VoicePanel";
import TextPanel from "../components/TextPanel";
import MembersPanel from "../components/MembersPanel";
import FriendsPanel from "../components/FriendsPanel";
import DMPanel from "../components/DMPanel";
import { ServerPresenceProvider } from "../context/ServerPresenceContext";
import { isBrowserRuntime } from "../utils/runtime";
import { trackEvent } from "../utils/analytics";
import { dms as dmsApi } from "../api/client";

const DESKTOP_PROMPT_DISMISSED_KEY = "synthDesktopPromptDismissed";

export default function HomePage() {
  const { user } = useAuth();
  const [activeServer, setActiveServer] = useState(null);
  const [activeChannel, setActiveChannel] = useState(null);
  const [activeFriend, setActiveFriend] = useState(null);
  const [globalUnreadCount, setGlobalUnreadCount] = useState(0);
  const [showDesktopPrompt, setShowDesktopPrompt] = useState(() => {
    if (!isBrowserRuntime() || typeof window === "undefined") {
      return false;
    }

    return window.localStorage.getItem(DESKTOP_PROMPT_DISMISSED_KEY) !== "1";
  });

  usePresence(!!user);

  const handleServerSelect = (server) => {
    setActiveServer(server);
    setActiveChannel(null);
    // Clear friend selection when entering a server
    if (server) {
      setActiveFriend(null);
    }
  };

  useEffect(() => {
    if (!user) return;
    const fetchUnread = () => {
      dmsApi.unreadCount()
        .then((res) => setGlobalUnreadCount(res.unread_count || 0))
        .catch(() => {});
    };
    fetchUnread();
    const interval = setInterval(fetchUnread, 15000);
    return () => clearInterval(interval);
  }, [user]);

  useEffect(() => {
    if (!showDesktopPrompt) {
      return;
    }

    trackEvent("desktop_cta_impression", {
      source: "home-banner",
      placement: "home-banner",
    });
  }, [showDesktopPrompt]);

  const dismissDesktopPrompt = () => {
    trackEvent("desktop_cta_dismissed", {
      source: "home-banner",
      placement: "home-banner",
    });

    setShowDesktopPrompt(false);

    if (typeof window !== "undefined") {
      window.localStorage.setItem(DESKTOP_PROMPT_DISMISSED_KEY, "1");
    }
  };

  const handleBannerCtaClick = () => {
    trackEvent("desktop_cta_clicked", {
      source: "home-banner",
      placement: "home-banner",
    });
  };

  const handleFriendRemoved = (friendId) => {
    if (activeFriend?.id === friendId) {
      setActiveFriend(null);
    }
  };

  // Home mode: no server selected — show friends & DMs
  const isHomeMode = activeServer === null;

  return (
    <div className="relative h-screen flex overflow-hidden noise-texture">
      {showDesktopPrompt && (
        <div className="absolute left-1/2 top-3 z-30 w-[calc(100%-1.5rem)] max-w-3xl -translate-x-1/2 rounded-xl border border-neon-cyan/40 bg-cyber-surface/90 px-4 py-3 backdrop-blur-md">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-[10px] uppercase tracking-[0.24em] text-cyber-muted">Web Session Active</p>
              <p className="text-sm text-cyber-text">
                We also have a desktop app if you'd like to download. You can click the download button or find it on bottom left corner anytime.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Link
                to="/download?src=home-banner"
                onClick={handleBannerCtaClick}
                className="rounded-lg border border-neon-cyan/50 px-3 py-2 text-[11px] font-display font-semibold uppercase tracking-[0.2em] text-neon-cyan transition hover:bg-neon-cyan/10 hover:glow-cyan"
              >
                Download Desktop
              </Link>
              <button
                type="button"
                onClick={dismissDesktopPrompt}
                className="rounded-lg border border-cyber-border px-3 py-2 text-[11px] font-display uppercase tracking-[0.2em] text-cyber-muted transition hover:border-cyber-muted/60 hover:text-cyber-text"
              >
                Not now
              </button>
            </div>
          </div>
        </div>
      )}
      <ServerSidebar activeServer={activeServer} onSelect={handleServerSelect} globalUnreadCount={globalUnreadCount} />

      {isHomeMode ? (
        /* ── Home / Friends & DMs mode ── */
        <>
          <FriendsPanel
            onSelectFriend={setActiveFriend}
            activeFriend={activeFriend}
          />
          <div className="flex-1 overflow-hidden relative flex">
            <DMPanel
              friend={activeFriend}
              onFriendRemoved={handleFriendRemoved}
            />
          </div>
        </>
      ) : (
        /* ── Server mode (existing layout) ── */
        <ServerPresenceProvider server={activeServer}>
          <ChannelList
            server={activeServer}
            activeChannel={activeChannel}
            onSelect={setActiveChannel}
          />
          <div className="flex-1 overflow-hidden relative flex">
            {activeChannel?.type === "text" && (
              <TextPanel channel={activeChannel} />
            )}
            <VoicePanel
              activeChannel={activeChannel}
              onNavigate={(channel) => setActiveChannel(channel)}
            />
          </div>
          <MembersPanel server={activeServer} />
        </ServerPresenceProvider>
      )}
    </div>
  );
}
