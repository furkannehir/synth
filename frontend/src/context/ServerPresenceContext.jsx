import { createContext, useContext, useState, useEffect, useRef } from "react";
import { servers as serversApi } from "../api/client";

const ServerPresenceContext = createContext({
  members: [],
  voiceChannels: {},
  connected: false,
});

export function ServerPresenceProvider({ server, children }) {
  const [members, setMembers] = useState([]);
  const [voiceChannels, setVoiceChannels] = useState({});
  const [connected, setConnected] = useState(false);
  const esRef = useRef(null);

  useEffect(() => {
    // Avoid double events by closing preexisting ref
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }

    if (!server) return;

    const url = serversApi.membersStreamUrl(server.id);
    const es = new EventSource(url);
    esRef.current = es;

    es.onopen = () => setConnected(true);

    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (Array.isArray(data.members)) {
          setMembers(data.members);
          // If the old payload format is sent, we just get members
        } else if (data.members) {
          setMembers(data.members);
        }
        
        if (data.voice_channels) {
          setVoiceChannels(data.voice_channels);
        } else {
          setVoiceChannels({});
        }

        setConnected(true);
      } catch {
        // ignore malformed
      }
    };

    es.onerror = () => {
      setConnected(false);
    };

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [server]);

  return (
    <ServerPresenceContext.Provider value={{ members, voiceChannels, connected }}>
      {children}
    </ServerPresenceContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useServerPresence() {
  return useContext(ServerPresenceContext);
}
