import { createContext, useContext, useEffect, useRef, useState } from "react";
import { servers as serversApi } from "../api/client";
import { useAuth } from "./AuthContext";

const ServerPresenceContext = createContext({ members: [], voiceChannels: {}, connected: false });

export function ServerPresenceProvider({ server, children }) {
  const { accessToken } = useAuth();
  const serverId = server?.id || null;
  const [snapshot, setSnapshot] = useState({ serverId: null, token: null, members: [], voiceChannels: {}, connected: false });
  const esRef = useRef(null);
  const ownsSnapshot = snapshot.serverId === serverId && snapshot.token === accessToken;

  useEffect(() => {
    if (!serverId) return;
    let active = true;
    const es = new EventSource(serversApi.membersStreamUrl(serverId));
    esRef.current = es;
    es.onopen = () => {
      if (!active) return;
      setSnapshot((previous) => ({
        serverId, token: accessToken,
        members: previous.serverId === serverId ? previous.members : [],
        voiceChannels: previous.serverId === serverId ? previous.voiceChannels : {},
        connected: true,
      }));
    };
    es.onmessage = (event) => {
      if (!active) return;
      try {
        const data = JSON.parse(event.data);
        setSnapshot((previous) => ({
          serverId, token: accessToken,
          members: Array.isArray(data.members) ? data.members : previous.serverId === serverId ? previous.members : [],
          voiceChannels: data.voice_channels || {},
          connected: true,
        }));
      } catch { /* Ignore malformed stream events. */ }
    };
    es.onerror = () => {
      if (active) setSnapshot((previous) => ({ ...previous, connected: false }));
    };
    return () => { active = false; es.close(); esRef.current = null; };
  }, [serverId, accessToken]);

  return <ServerPresenceContext.Provider value={{
    members: ownsSnapshot ? snapshot.members : [],
    voiceChannels: ownsSnapshot ? snapshot.voiceChannels : {},
    connected: ownsSnapshot && snapshot.connected,
  }}>{children}</ServerPresenceContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useServerPresence() { return useContext(ServerPresenceContext); }
