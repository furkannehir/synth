import { useState, useCallback } from "react";
import {
  LiveKitRoom,
  RoomAudioRenderer,
  useParticipants,
  useLocalParticipant,
} from "@livekit/components-react";
import { voice as voiceApi } from "../api/client";

export default function VoicePanel({ channel }) {
  const [token, setToken] = useState(null);
  const [wsUrl, setWsUrl] = useState(null);
  const [joining, setJoining] = useState(false);
  const [error, setError] = useState("");

  const handleJoin = useCallback(async () => {
    if (!channel) return;
    setJoining(true);
    setError("");
    try {
      const data = await voiceApi.join(channel.server_id, channel.id);
      setToken(data.token);
      setWsUrl(data.url);
    } catch (err) {
      setError(err.message);
    } finally {
      setJoining(false);
    }
  }, [channel]);

  const handleLeave = useCallback(async () => {
    if (channel) {
      voiceApi.leave(channel.server_id, channel.id).catch(() => {});
    }
    setToken(null);
    setWsUrl(null);
  }, [channel]);

  if (!channel || channel.type !== "voice") {
    return (
      <div className="flex-1 flex flex-col items-center justify-center bg-cyber-bg noise-texture gap-4">
        <div className="w-16 h-16 rounded-2xl bg-cyber-surface border border-cyber-border/30
                        flex items-center justify-center text-cyber-muted/30 text-3xl">
          ◈
        </div>
        <div className="text-center">
          <p className="text-cyber-muted/50 text-sm font-display uppercase tracking-widest">No channel selected</p>
          <p className="text-cyber-muted/30 text-xs mt-1">Pick a voice channel to connect</p>
        </div>
      </div>
    );
  }

  // Not connected yet
  if (!token) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center bg-cyber-bg noise-texture gap-6">
        <div className="text-center">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 bg-neon-green/5 border border-neon-green/20 rounded-full mb-4">
            <span className="w-2 h-2 rounded-full bg-neon-green/60 animate-pulse" />
            <span className="text-neon-green/80 text-[10px] font-display uppercase tracking-[0.2em]">Ready</span>
          </div>
          <h3 className="text-2xl font-display font-bold text-neon-cyan text-glow-cyan uppercase tracking-[0.15em]">
            {channel.name}
          </h3>
          <p className="text-cyber-muted/50 text-xs mt-2 font-display uppercase tracking-widest">
            voice channel {channel.user_limit > 0 && `· ${channel.user_limit} max`}
          </p>
        </div>

        {error && (
          <div className="px-4 py-2 bg-neon-red/10 border border-neon-red/30 rounded-lg">
            <p className="text-neon-red text-sm">{error}</p>
          </div>
        )}

        <button
          onClick={handleJoin}
          disabled={joining}
          className="px-8 py-3 bg-gradient-to-r from-neon-green/15 to-neon-green/5
                     border border-neon-green/60 text-neon-green
                     rounded-xl font-display font-bold uppercase tracking-[0.2em] text-sm
                     hover:from-neon-green/25 hover:to-neon-green/10 hover:glow-green hover:border-neon-green
                     disabled:opacity-40 disabled:cursor-not-allowed
                     transition-all duration-300 cursor-pointer"
        >
          {joining ? "CONNECTING..." : "JOIN VOICE"}
        </button>
      </div>
    );
  }

  // Connected to LiveKit
  return (
    <div className="flex-1 flex flex-col bg-cyber-bg">
      <LiveKitRoom
        serverUrl={wsUrl}
        token={token}
        connect={true}
        onDisconnected={handleLeave}
        className="flex-1 flex flex-col"
      >
        <RoomAudioRenderer />
        <VoiceConnected channel={channel} onLeave={handleLeave} />
      </LiveKitRoom>
    </div>
  );
}

function VoiceConnected({ channel, onLeave }) {
  const participants = useParticipants();
  const { localParticipant } = useLocalParticipant();
  const [muted, setMuted] = useState(false);

  const toggleMute = useCallback(async () => {
    if (!localParticipant) return;
    await localParticipant.setMicrophoneEnabled(muted);
    setMuted(!muted);
  }, [localParticipant, muted]);

  return (
    <div className="flex-1 flex flex-col noise-texture">
      {/* Header */}
      <div className="px-5 h-14 flex items-center border-b border-cyber-border/40 bg-cyber-surface/40 gap-3">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-neon-green animate-pulse" />
          <h3 className="font-display font-bold text-sm text-neon-cyan uppercase tracking-wider">
            {channel.name}
          </h3>
        </div>
        <div className="ml-auto flex items-center gap-3">
          {/* Waveform indicator */}
          <div className="flex items-end gap-0.5 h-4">
            <div className="waveform-bar" />
            <div className="waveform-bar" />
            <div className="waveform-bar" />
            <div className="waveform-bar" />
          </div>
          <span className="text-cyber-muted text-xs font-display tabular-nums bg-cyber-bg/40 px-2.5 py-1 rounded-full">
            {participants.length} online
          </span>
        </div>
      </div>

      {/* Participants grid */}
      <div className="flex-1 flex flex-wrap content-start gap-5 p-6">
        {participants.map((p) => (
          <ParticipantTile
            key={p.identity}
            participant={p}
            isLocal={p.identity === localParticipant?.identity}
          />
        ))}
      </div>

      {/* Controls bar */}
      <div className="h-[72px] px-6 flex items-center justify-center gap-4 border-t border-cyber-border/40 bg-cyber-surface/60">
        <button
          onClick={toggleMute}
          className={`px-5 py-2.5 rounded-xl text-sm font-display font-bold uppercase tracking-wider
                      transition-all duration-300 cursor-pointer
                      ${
                        muted
                          ? "bg-neon-red/10 border border-neon-red/60 text-neon-red hover:bg-neon-red/20 hover:border-neon-red"
                          : "bg-neon-green/10 border border-neon-green/60 text-neon-green hover:bg-neon-green/20 hover:border-neon-green hover:glow-green"
                      }`}
        >
          {muted ? "⊘ UNMUTE" : "◉ MUTE"}
        </button>

        <button
          onClick={onLeave}
          className="px-5 py-2.5 rounded-xl text-sm font-display font-bold uppercase tracking-wider
                     bg-neon-red/10 border border-neon-red/60 text-neon-red
                     hover:bg-neon-red/20 hover:border-neon-red transition-all duration-300 cursor-pointer"
        >
          ⏻ DISCONNECT
        </button>
      </div>
    </div>
  );
}

function ParticipantTile({ participant, isLocal }) {
  const isSpeaking = participant.isSpeaking;

  return (
    <div
      className={`w-28 h-28 rounded-2xl flex flex-col items-center justify-center gap-2.5
                  bg-cyber-surface/80 border transition-all duration-300
                  ${
                    isSpeaking
                      ? "border-neon-green/60 glow-green speaking-pulse"
                      : "border-cyber-border/30 hover:border-cyber-border/60"
                  }`}
    >
      {/* Avatar circle */}
      <div
        className={`w-11 h-11 rounded-full flex items-center justify-center text-sm font-display
                    font-bold uppercase transition-all duration-300
                    ${
                      isLocal
                        ? "bg-gradient-to-br from-neon-cyan/25 to-neon-cyan/10 text-neon-cyan border border-neon-cyan/20"
                        : "bg-gradient-to-br from-neon-pink/25 to-neon-pink/10 text-neon-pink border border-neon-pink/20"
                    }`}
      >
        {(participant.name || participant.identity)?.slice(0, 2)}
      </div>
      <div className="text-center px-2">
        <span className="text-[10px] text-cyber-text/80 truncate block max-w-[90px] font-display font-medium">
          {participant.name || participant.identity}
        </span>
        {isLocal && (
          <span className="text-[8px] text-neon-cyan/60 uppercase tracking-widest">you</span>
        )}
      </div>
    </div>
  );
}
