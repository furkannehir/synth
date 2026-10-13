import { AudioLines, Volume2 } from "lucide-react";
import { useServerPresence } from "../context/ServerPresenceContext";
import Avatar from "./Avatar";
import { useState } from "react";

export default function VoiceRoomBanner({ channels, onJoin }) {
  const [joining, setJoining] = useState(false);
  const { voiceChannels, members } = useServerPresence();
  const rooms = channels.filter(({ type }) => type === "voice");
  const room = rooms.find(({ id }) => voiceChannels[id]?.length) || rooms[0];
  if (!room) return null;
  const participants = voiceChannels[room.id] || [];
  const names = participants.slice(0, 3).map(({ name }) => name).filter(Boolean);
  const description = names.length ? `${names.join(", ")}${participants.length > 3 ? " and others" : ""} are hanging out` : "A little company is one click away";
  return (
    <section className="voice-room-banner" aria-label={`Voice room: ${room.name}`}>
      <span className="voice-room-icon"><Volume2 aria-hidden="true" /></span>
      <div className="voice-room-info"><h2>{room.name}</h2><p>{description}</p></div>
      {participants.length > 0 && <div className="voice-room-avatars" aria-label={`${participants.length} in voice`}>
        {participants.slice(0, 3).map((participant) => <Avatar key={participant.identity} username={participant.name} avatar={members.find(({ id }) => id === participant.identity)?.avatar} online />)}
      </div>}
      <button className="primary-button" disabled={joining} onClick={async () => { setJoining(true); try { await onJoin(room); } finally { setJoining(false); } }}><AudioLines size={23} />{joining ? "Connecting…" : "Join voice"}</button>
    </section>
  );
}
