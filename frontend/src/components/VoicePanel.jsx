import { useState, useCallback, useEffect, useRef } from "react";
import {
  LiveKitRoom,
  RoomAudioRenderer,
  useParticipants,
  useLocalParticipant,
  useTracks,
  VideoTrack,
} from "@livekit/components-react";
import { Track, createLocalVideoTrack } from "livekit-client";
import { voice as voiceApi } from "../api/client";
import { useServerPresence } from "../context/ServerPresenceContext";

export default function VoicePanel({ channel }) {
  const [token, setToken] = useState(null);
  const [wsUrl, setWsUrl] = useState(null);
  const [joining, setJoining] = useState(false);
  const [error, setError] = useState("");

  const { voiceChannels } = useServerPresence();
  const channelParticipants = (channel && voiceChannels[channel.id]) || [];

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

          {channelParticipants.length > 0 && (
            <div className="flex justify-center -space-x-2 mt-4">
              {channelParticipants.map((p, i) => {
                const initials = (p.name || "?").slice(0, 2).toUpperCase();
                return (
                  <div
                    key={p.identity || i}
                    title={p.name}
                    className="w-8 h-8 rounded-full bg-cyber-surface border-2 border-neon-cyan/40
                               flex items-center justify-center text-[10px] font-display font-bold text-neon-cyan/80
                               shadow-md shadow-neon-cyan/10 z-10 hover:z-20 hover:-translate-y-1 hover:border-neon-cyan transition-all"
                    style={{ zIndex: channelParticipants.length - i }}
                  >
                    {initials}
                  </div>
                );
              })}
            </div>
          )}
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
        audio={true}
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
  const [cameraOn, setCameraOn] = useState(false);
  const [screenShareOn, setScreenShareOn] = useState(false);
  const [showCamPreview, setShowCamPreview] = useState(false);

  const videoTracks = useTracks([Track.Source.Camera, Track.Source.ScreenShare]);

  // Sync to backend instantly when tracks change (e.g. camera turned on)
  useEffect(() => {
    // Fire and forget heartbeat to trigger backend mark_dirty()
    import("../api/client").then(({ presence }) => presence.heartbeat().catch(() => {}));
  }, [videoTracks.length]);

  const toggleMute = useCallback(async () => {
    if (!localParticipant) return;
    await localParticipant.setMicrophoneEnabled(!muted);
    setMuted(!muted);
  }, [localParticipant, muted]);

  const toggleCamera = useCallback(async () => {
    if (!localParticipant) return;
    if (cameraOn) {
      await localParticipant.setCameraEnabled(false);
      setCameraOn(false);
    } else {
      setShowCamPreview(true);
    }
  }, [localParticipant, cameraOn]);

  const confirmCamera = useCallback(async () => {
    if (!localParticipant) return;
    await localParticipant.setCameraEnabled(true);
    setCameraOn(true);
    setShowCamPreview(false);
  }, [localParticipant]);

  const cancelCamera = useCallback(() => {
    setShowCamPreview(false);
  }, []);

  const toggleScreenShare = useCallback(async () => {
    if (!localParticipant) return;
    await localParticipant.setScreenShareEnabled(!screenShareOn);
    setScreenShareOn(!screenShareOn);
  }, [localParticipant, screenShareOn]);

  // Filter out tracks that are disabled (muted or unpublished)
  const activeVideoTracks = videoTracks.filter((t) => {
    if (t.publication && t.publication.isMuted) return false;
    if (t.participant.isLocal) {
      if (t.source === Track.Source.Camera && !cameraOn) return false;
      if (t.source === Track.Source.ScreenShare && !screenShareOn) return false;
    }
    return true;
  });

  // Determine grid layout based on tracks
  const hasScreenShare = activeVideoTracks.some((t) => t.source === Track.Source.ScreenShare);
  
  // Find participants without any video tracks
  const participantsWithVideo = new Set(activeVideoTracks.map((t) => t.participant.identity));
  const audioOnlyParticipants = participants.filter((p) => !participantsWithVideo.has(p.identity));

  return (
    <div className="flex-1 flex flex-col noise-texture overflow-hidden">
      {/* Header */}
      <div className="px-5 h-14 flex shrink-0 items-center border-b border-cyber-border/40 bg-cyber-surface/40 gap-3 z-10">
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

      {/* Main Content Area */}
      <div className="flex-1 overflow-y-auto flex flex-col p-4 gap-4">
        {/* Video Grid */}
        {activeVideoTracks.length > 0 && (
          <div
            className={`w-full grid gap-4 shrink-0 transition-all ${
              activeVideoTracks.length === 1 && !hasScreenShare
                ? "grid-cols-1 max-w-4xl mx-auto"
                : activeVideoTracks.length === 2 && !hasScreenShare
                ? "grid-cols-2"
                : hasScreenShare
                ? "grid-cols-3"
                : "grid-cols-[repeat(auto-fit,minmax(280px,1fr))]"
            }`}
          >
            {activeVideoTracks.map((trackRef) => {
              const isScreenShare = trackRef.source === Track.Source.ScreenShare;
              const isSpeaking = trackRef.participant.isSpeaking;
              const isLocalCamera = trackRef.participant.isLocal && !isScreenShare;

              return (
                <div
                  key={trackRef.publication.trackSid}
                  className={`video-tile ${
                    isScreenShare && hasScreenShare
                      ? "col-span-full aspect-video"
                      : "aspect-video"
                  } ${
                    isSpeaking
                      ? isScreenShare
                        ? "border-neon-purple/60 glow-purple screen-share-pulse"
                        : "border-neon-green/60 glow-green speaking-pulse"
                      : "border-cyber-border/30"
                  }`}
                >
                  <VideoTrack 
                    trackRef={trackRef} 
                    className={`w-full h-full object-contain bg-black ${isLocalCamera ? "-scale-x-100" : ""}`} 
                  />
                  
                  {isScreenShare ? (
                    <div className="screen-share-badge glow-purple border-neon-purple text-neon-purple">
                      SCREEN
                    </div>
                  ) : (
                    <div className="camera-badge glow-cyan border-neon-cyan text-neon-cyan">
                      CAM
                    </div>
                  )}

                  <div className="participant-name-badge shadow-md">
                    {trackRef.participant.name || trackRef.participant.identity}
                    {trackRef.participant.identity === localParticipant?.identity && " (You)"}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Audio-only participants strip */}
        <div className="flex flex-wrap content-start gap-4 mt-auto pt-4 border-t border-cyber-border/20">
          {audioOnlyParticipants.map((p) => (
            <ParticipantTile
              key={p.identity}
              participant={p}
              isLocal={p.identity === localParticipant?.identity}
            />
          ))}
        </div>
      </div>

      {/* Controls bar */}
      <div className="h-[72px] shrink-0 px-6 flex items-center justify-center gap-4 border-t border-cyber-border/40 bg-cyber-surface/60 z-10">
        <button
          onClick={toggleMute}
          className={`px-4 py-2.5 rounded-xl text-sm font-display font-bold uppercase tracking-wider
                      transition-all duration-300 cursor-pointer min-w-[120px]
                      ${
                        muted
                          ? "bg-neon-red/10 border border-neon-red/60 text-neon-red hover:bg-neon-red/20 hover:border-neon-red"
                          : "bg-neon-green/10 border border-neon-green/60 text-neon-green hover:bg-neon-green/20 hover:border-neon-green hover:glow-green"
                      }`}
        >
          {muted ? "⊘ UNMUTE" : "◉ MUTE"}
        </button>

        <button
          onClick={toggleCamera}
          className={`px-4 py-2.5 rounded-xl text-sm font-display font-bold uppercase tracking-wider
                      transition-all duration-300 cursor-pointer min-w-[120px]
                      ${
                        cameraOn
                          ? "bg-neon-cyan/10 border border-neon-cyan text-neon-cyan glow-cyan hover:bg-neon-cyan/20"
                          : "bg-neon-cyan/5 border border-neon-cyan/40 text-neon-cyan/60 hover:border-neon-cyan/80 hover:text-neon-cyan"
                      }`}
        >
          📷 CAM {cameraOn ? "ON" : "OFF"}
        </button>

        <button
          onClick={toggleScreenShare}
          className={`px-4 py-2.5 rounded-xl text-sm font-display font-bold uppercase tracking-wider
                      transition-all duration-300 cursor-pointer min-w-[120px]
                      ${
                        screenShareOn
                          ? "bg-neon-purple/10 border border-neon-purple text-neon-purple glow-purple hover:bg-neon-purple/20"
                          : "bg-neon-purple/5 border border-neon-purple/40 text-neon-purple/60 hover:border-neon-purple/80 hover:text-neon-purple"
                      }`}
        >
          🖥 SCREEN {screenShareOn ? "ON" : "OFF"}
        </button>

        <button
          onClick={onLeave}
          className="px-4 py-2.5 rounded-xl text-sm font-display font-bold uppercase tracking-wider
                     bg-neon-red/10 border border-neon-red/60 text-neon-red
                     hover:bg-neon-red/20 hover:border-neon-red transition-all duration-300 cursor-pointer min-w-[120px]"
        >
          ⏻ DISCONNECT
        </button>
      </div>

      {showCamPreview && (
        <CameraPreviewModal onConfirm={confirmCamera} onCancel={cancelCamera} />
      )}
    </div>
  );
}

function ParticipantTile({ participant, isLocal }) {
  const isSpeaking = participant.isSpeaking;

  return (
    <div
      className={`w-28 h-28 shrink-0 rounded-2xl flex flex-col items-center justify-center gap-2.5
                  bg-cyber-surface/40 backdrop-blur-sm border transition-all duration-300
                  ${
                    isSpeaking
                      ? "border-neon-green/60 glow-green speaking-pulse"
                      : "border-cyber-border/30 hover:border-cyber-border/60"
                  }`}
    >
      {/* Avatar circle */}
      <div
        className={`relative w-11 h-11 rounded-full flex items-center justify-center text-sm font-display
                    font-bold uppercase transition-all duration-300
                    ${
                      isLocal
                        ? "bg-gradient-to-br from-neon-cyan/25 to-neon-cyan/10 text-neon-cyan border border-neon-cyan/20"
                        : "bg-gradient-to-br from-neon-pink/25 to-neon-pink/10 text-neon-pink border border-neon-pink/20"
                    }`}
      >
        {(participant.name || participant.identity)?.slice(0, 2)}
        <div className="absolute -bottom-1 -right-1 w-4 h-4 rounded-full bg-cyber-bg border border-cyber-border/50 flex items-center justify-center text-[8px]">
          {participant.isMicrophoneEnabled ? (
            <span className="text-neon-green">🎤</span>
          ) : (
             <span className="text-neon-red">⊘</span>
          )}
        </div>
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

function CameraPreviewModal({ onConfirm, onCancel }) {
  const videoRef = useRef(null);
  const trackRef = useRef(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let mounted = true;

    async function initCamera() {
      try {
        const track = await createLocalVideoTrack({
          facingMode: "user",
          resolution: { width: 1280, height: 720 },
        });
        
        if (!mounted) {
          track.stop();
          return;
        }
        
        trackRef.current = track;
        if (videoRef.current) {
          track.attach(videoRef.current);
        }
      } catch (err) {
        if (mounted) {
          setError(err.message || "Could not access camera");
        }
      }
    }

    initCamera();

    return () => {
      mounted = false;
      if (trackRef.current) {
        trackRef.current.stop();
      }
    };
  }, []);

  return (
    <div className="absolute inset-0 z-[100] flex items-center justify-center bg-cyber-bg/80 backdrop-blur-sm p-6">
      <div className="w-full max-w-3xl bg-cyber-surface border border-neon-cyan/40 rounded-2xl overflow-hidden glass-card flex flex-col shadow-2xl">
        <div className="px-6 py-4 border-b border-cyber-border/40 bg-cyber-panel/50">
          <h2 className="text-lg font-display font-bold text-neon-cyan uppercase tracking-[0.1em]">
            Camera Preview
          </h2>
          <p className="text-xs text-cyber-muted tracking-wide mt-1">
            Check your appearance before publishing to the room
          </p>
        </div>
        
        <div className="p-6 flex flex-col items-center justify-center bg-black aspect-video relative">
          {error ? (
            <div className="text-neon-red text-sm bg-neon-red/10 px-4 py-2 rounded border border-neon-red/30">
              {error}
            </div>
          ) : (
            <video
              ref={videoRef}
              className="w-full h-full object-contain rounded-xl -scale-x-100"
              data-lk-local-video="true"
            />
          )}
        </div>

        <div className="px-6 py-4 border-t border-cyber-border/40 bg-cyber-panel/50 flex items-center justify-end gap-3">
          <button
            onClick={onCancel}
            className="px-5 py-2.5 rounded-xl text-sm font-display uppercase tracking-wider
                       border border-cyber-border/80 text-cyber-muted hover:text-cyber-text
                       hover:border-cyber-muted transition-all duration-300 cursor-pointer"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={!!error}
            className="px-6 py-2.5 rounded-xl text-sm font-display font-bold uppercase tracking-wider
                       bg-neon-cyan/10 border border-neon-cyan/60 text-neon-cyan cursor-pointer
                       hover:bg-neon-cyan/20 hover:border-neon-cyan focus:glow-cyan
                       disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-300"
          >
            Publish Camera
          </button>
        </div>
      </div>
    </div>
  );
}
