import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { usePresence } from "../hooks/usePresence";
import ServerSidebar from "../components/ServerSidebar";
import ChannelList from "../components/ChannelList";
import VoicePanel from "../components/VoicePanel";
import MembersPanel from "../components/MembersPanel";

export default function HomePage() {
  const { user } = useAuth();
  const [activeServer, setActiveServer] = useState(null);
  const [activeChannel, setActiveChannel] = useState(null);

  usePresence(!!user);

  const handleServerSelect = (server) => {
    setActiveServer(server);
    setActiveChannel(null);
  };

  return (
    <div className="h-screen flex overflow-hidden noise-texture">
      <ServerSidebar activeServer={activeServer} onSelect={handleServerSelect} />
      <ChannelList
        server={activeServer}
        activeChannel={activeChannel}
        onSelect={setActiveChannel}
      />
      <VoicePanel channel={activeChannel} />
      <MembersPanel server={activeServer} />
    </div>
  );
}
