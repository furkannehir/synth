import { forwardRef, useState, useCallback, useEffect, useImperativeHandle, useRef } from "react";
import { AudioLines, LoaderCircle, Maximize2, Mic, MicOff, Monitor, PhoneOff, Video, VideoOff, Volume2, X } from "lucide-react";
import Avatar from "./Avatar";
import CameraPreviewModal from "./CameraPreviewModal";
import ScreenSharePreviewModal from "./ScreenSharePreviewModal";
import FullscreenVideo from "./FullscreenVideo";
import {
  LiveKitRoom,
  RoomAudioRenderer,
  useParticipants,
  useLocalParticipant,
  useTracks,
  VideoTrack,
} from "@livekit/components-react";
import { Track } from "livekit-client";
import { voice as voiceApi } from "../api/client";
import { useServerPresence } from "../context/ServerPresenceContext";
import { isTauriRuntime } from "../utils/runtime";

const VoicePanel = forwardRef(function VoicePanel({ activeChannel, onNavigate }, ref) {
  const [token, setToken] = useState(null);
  const [wsUrl, setWsUrl] = useState(null);
  const [joining, setJoining] = useState(false);
  const [error, setError] = useState("");
  const [connectedChannel, setConnectedChannel] = useState(null);
  const joiningRef = useRef(false);

  // Floating drag state
  const [panelPos, setPanelPos] = useState({ x: 0, y: 0 });
  const dragRef = useRef({ isDragging: false, startX: 0, startY: 0, iniX: 0, iniY: 0 });

  const { voiceChannels, members } = useServerPresence();

  // Participants for the channel we are looking at in the "Ready" screen
  const activeChannelParticipants = (activeChannel && voiceChannels[activeChannel.id]) || [];

  const joinChannel = useCallback(async (channel) => {
    if (!channel || channel.type !== "voice" || joiningRef.current) return;
    if (connectedChannel?.id === channel.id) { onNavigate(channel); return; }
    joiningRef.current = true;
    setJoining(true);
    setError("");
    try {
      const data = await voiceApi.join(channel.server_id, channel.id);
      setToken(data.token);
      setWsUrl(data.url);
      setConnectedChannel(channel);
      setPanelPos({ x: 0, y: 0 }); // reset position on join
    } catch (err) {
      setError(err.message);
    } finally {
      joiningRef.current = false;
      setJoining(false);
    }
  }, [connectedChannel, onNavigate]);
  useImperativeHandle(ref, () => ({ join: joinChannel }), [joinChannel]);
  const handleJoin = () => joinChannel(activeChannel);

  const handleLeave = useCallback(async () => {
    if (connectedChannel) {
      voiceApi.leave(connectedChannel.server_id, connectedChannel.id).catch(() => { });
    }
    setToken(null);
    setWsUrl(null);
    setConnectedChannel(null);
    setPanelPos({ x: 0, y: 0 });
  }, [connectedChannel]);

  const isConnected = !!token && !!connectedChannel;
  const isViewingText = activeChannel?.type === "text";
  const isFullViewConnected = isConnected && (!activeChannel || activeChannel.id === connectedChannel?.id) && !isViewingText;
  const isFloatingConnected = isConnected && !isFullViewConnected;

  useEffect(() => {
    if (!isFloatingConnected) {
       setPanelPos({ x: 0, y: 0 });
       return;
    }

    const handlePointerMove = (e) => {
      if (!dragRef.current.isDragging) return;
      e.preventDefault();
      const newX = dragRef.current.iniX + (e.clientX - dragRef.current.startX);
      const newY = dragRef.current.iniY + (e.clientY - dragRef.current.startY);
      setPanelPos({ x: newX, y: newY });
    };

    const handlePointerUp = () => {
      dragRef.current.isDragging = false;
      document.body.style.userSelect = '';
    };

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);

    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
      document.body.style.userSelect = '';
    };
  }, [isFloatingConnected]);

  const onDragStart = useCallback((e) => {
    dragRef.current.isDragging = true;
    dragRef.current.startX = e.clientX;
    dragRef.current.startY = e.clientY;
    dragRef.current.iniX = panelPos.x;
    dragRef.current.iniY = panelPos.y;
    document.body.style.userSelect = 'none';
  }, [panelPos]);

  return (
    <>
      {/* 1. Full Screen Not Connected: Show JOIN VOICE screen for active voice channel */}
      {!isFullViewConnected && activeChannel?.type === "voice" && (
        <div className="voice-ready">
          <div className="text-center voice-ready-info">
            <div className="voice-room-icon"><Volume2 /></div>
            <div className="inline-flex items-center gap-2 px-4 py-1.5 bg-neon-green/5 border border-neon-green/20 rounded-full mb-4">
              <span className="w-2 h-2 rounded-full bg-neon-green/60 animate-pulse" />
              <span className="text-neon-green/80 text-[10px] font-display uppercase tracking-[0.2em]">Ready</span>
            </div>
            <h3 className="text-2xl font-display font-bold text-neon-cyan text-glow-cyan uppercase tracking-[0.15em]">
              {activeChannel.name}
            </h3>
            <p className="text-cyber-muted/50 text-xs mt-2 font-display uppercase tracking-widest">
              voice channel {activeChannel.user_limit > 0 && `· ${activeChannel.user_limit} max`}
            </p>

            {activeChannelParticipants.length > 0 && (
              <div className="flex justify-center -space-x-2 mt-4">
                {activeChannelParticipants.map((p, i) => {
                  return (
                    <Avatar key={p.identity || i} username={p.name} avatar={members.find(({ id }) => id === p.identity)?.avatar} online />
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
            className="primary-button"
          >
            <AudioLines size={22} />{joining ? "Connecting…" : "Join voice"}
          </button>
        </div>
      )}

      {/* 2. Full Screen Not Connected & No channel selected */}
      {!activeChannel && !isConnected && (
        <div className="flex-1 flex flex-col items-center justify-center bg-cyber-bg noise-texture gap-4">
          <div className="w-16 h-16 rounded-2xl bg-cyber-surface border border-cyber-border/30
                          flex items-center justify-center text-cyber-muted/30 text-3xl">
            <AudioLines size={32} />
          </div>
          <div className="text-center">
            <p className="text-cyber-muted/50 text-sm font-display uppercase tracking-widest">No channel selected</p>
            <p className="text-cyber-muted/30 text-xs mt-1">Pick a voice or text channel</p>
          </div>
        </div>
      )}

      {error && isViewingText && <div className="voice-error" role="alert"><span>{error}</span><button aria-label="Dismiss voice error" onClick={() => setError("")}><X size={18} /></button></div>}

      {/* 3. Connected to LiveKit */}
      {isConnected && (
        <LiveKitRoom
          serverUrl={wsUrl}
          token={token}
          connect={true}
          audio={true}
          onDisconnected={handleLeave}
          className={
            isFloatingConnected
              ? "floating-voice-room"
              : "flex-1 flex flex-col bg-cyber-bg transition-colors duration-300"
          }
          style={isFloatingConnected ? { transform: `translate(${panelPos.x}px, ${panelPos.y}px)` } : undefined}
        >
          <RoomAudioRenderer />
          <VoiceConnected
            channel={connectedChannel}
            onLeave={handleLeave}
            isFloating={isFloatingConnected}
            onExpand={() => onNavigate(connectedChannel)}
            onDragStart={onDragStart}
          />
        </LiveKitRoom>
      )}
    </>
  );
});

export default VoicePanel;

function VoiceConnected({ channel, onLeave, isFloating, onExpand, onDragStart }) {
  const participants = useParticipants();
  const { localParticipant, isScreenShareEnabled } = useLocalParticipant();
  const [muted, setMuted] = useState(false);
  const [cameraOn, setCameraOn] = useState(false);
  const screenShareOn = !!isScreenShareEnabled;
  const [showCamPreview, setShowCamPreview] = useState(false);
  const [showScreenPreview, setShowScreenPreview] = useState(false);
  const [cameraError, setCameraError] = useState("");
  const [screenShareError, setScreenShareError] = useState("");
  const [screenSharePending, setScreenSharePending] = useState(false);
  const screenShareActionRef = useRef(null);

  useEffect(() => {
    const action = { pending: false, disposed: false };
    screenShareActionRef.current = action;
    return () => { action.disposed = true; };
  }, [localParticipant]);

  // Auto-enable mic on join and sync internal muted state
  useEffect(() => {
    let mounted = true;
    if (localParticipant) {
      if (!localParticipant.isMicrophoneEnabled) {
        localParticipant.setMicrophoneEnabled(true)
          .then(() => { if (mounted) setMuted(false); })
          .catch((err) => {
            console.error("Auto-unmute failed:", err);
            if (mounted) setMuted(true);
          });
      } else {
        if (mounted) setMuted(false);
      }
    }
    return () => { mounted = false; };
  }, [localParticipant]);

  const videoTracks = useTracks([Track.Source.Camera, Track.Source.ScreenShare]);

  // Sync to backend instantly when tracks change (e.g. camera turned on)
  useEffect(() => {
    // Fire and forget heartbeat to trigger backend mark_dirty()
    import("../api/client").then(({ presence }) => presence.heartbeat().catch(() => { }));
  }, [videoTracks.length]);

  const toggleMute = useCallback(async () => {
    if (!localParticipant) return;
    await localParticipant.setMicrophoneEnabled(muted);
    setMuted(!muted);
  }, [localParticipant, muted]);

  const toggleCamera = useCallback(async () => {
    if (!localParticipant) return;
    setCameraError("");
    try {
      if (cameraOn) {
        const cameraTrack = localParticipant.getTrackPublication(Track.Source.Camera)?.track;
        if (cameraTrack) await localParticipant.unpublishTrack(cameraTrack, true);
        else await localParticipant.setCameraEnabled(false);
        setCameraOn(false);
      } else {
        setShowCamPreview(true);
      }
    } catch (error) { setCameraError(error.message || "Could not turn the camera off. Please try again."); }
  }, [localParticipant, cameraOn]);

  const confirmCamera = useCallback(() => {
    setCameraOn(true);
    setShowCamPreview(false);
  }, []);

  const cancelCamera = useCallback(() => {
    setShowCamPreview(false);
  }, []);

  const toggleScreenShare = useCallback(async () => {
    const action = screenShareActionRef.current;
    if (!localParticipant || !action || action.pending || action.disposed) return;
    setScreenShareError("");
    if (!screenShareOn && isTauriRuntime()) {
      setShowScreenPreview(true);
      return;
    }
    const enable = !screenShareOn;
    action.pending = true;
    setScreenSharePending(true);
    try {
      // Call directly from this click so the browser can open its native picker.
      await localParticipant.setScreenShareEnabled(enable);
      if (action.disposed && enable) await localParticipant.setScreenShareEnabled(false);
    } catch (error) {
      const cancelled = enable && ["NotAllowedError", "AbortError"].includes(error.name);
      if (!action.disposed && !cancelled) setScreenShareError(error.message || (enable ? "Could not start screen sharing. Please try again." : "Could not stop screen sharing. Please try again."));
    } finally {
      action.pending = false;
      if (!action.disposed) setScreenSharePending(false);
    }
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
      <div
        className={`px-4 ${isFloating ? 'h-10 cursor-move hover:bg-cyber-surface/60 transition-colors' : 'h-14 px-5'} flex shrink-0 items-center border-b border-cyber-border/40 bg-cyber-surface/40 gap-3 z-10`}
        onPointerDown={isFloating ? (e) => {
          // If they click the expand button, don't initiate drag
          if (e.target.closest('button')) return;
          onDragStart(e);
        } : undefined}
        title={isFloating ? "Drag to move" : undefined}
      >
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-neon-green animate-pulse" />
          <h3 className={`font-display font-bold ${isFloating ? 'text-xs' : 'text-sm'} text-neon-cyan uppercase tracking-wider`}>
            {channel.name}
          </h3>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {!isFloating && (
            <div className="flex items-end gap-0.5 h-4 mr-2">
              <div className="waveform-bar" />
              <div className="waveform-bar" />
              <div className="waveform-bar" />
              <div className="waveform-bar" />
            </div>
          )}
          <span className={`text-cyber-muted ${isFloating ? 'text-[10px]' : 'text-xs'} font-display tabular-nums bg-cyber-bg/40 px-2.5 py-0.5 rounded-full`}>
            {participants.length} online
          </span>
          {isFloating && (
            <button
              onClick={(e) => { e.stopPropagation(); onExpand(); }}
              className="ml-1 text-neon-cyan/70 hover:text-neon-cyan hover:bg-neon-cyan/10 p-1 rounded transition-colors cursor-pointer"
              title="Expand to full screen"
            >
              <Maximize2 size={17} />
            </button>
          )}
        </div>
      </div>

      {/* Main Content Area */}
      {cameraError && <p className="voice-camera-error" role="alert">{cameraError}</p>}
      {screenShareError && <p className="voice-camera-error" role="alert">{screenShareError}</p>}
      <div className={`flex-1 overflow-y-auto flex flex-col ${isFloating ? 'p-2 gap-2 h-full' : 'p-4 gap-4'}`}>
        {/* Video Grid */}
        {activeVideoTracks.length > 0 && (
          <div
            className={`w-full grid ${isFloating ? 'gap-2' : 'gap-4'} shrink-0 transition-all ${activeVideoTracks.length === 1 && !hasScreenShare
              ? "grid-cols-1 " + (!isFloating ? "max-w-4xl mx-auto" : "")
              : activeVideoTracks.length === 2 && !hasScreenShare
                ? "grid-cols-2"
                : hasScreenShare
                  ? (isFloating ? "grid-cols-2" : "grid-cols-3")
                  : (isFloating ? "grid-cols-2" : "grid-cols-[repeat(auto-fit,minmax(280px,1fr))]")
              }`}
          >
            {activeVideoTracks.map((trackRef) => {
              const isScreenShare = trackRef.source === Track.Source.ScreenShare;
              const isSpeaking = trackRef.participant.isSpeaking;
              const isLocalCamera = trackRef.participant.isLocal && !isScreenShare;

              return (
                <FullscreenVideo
                  key={trackRef.publication.trackSid}
                  label={isScreenShare ? "screen share" : "camera"}
                  className={`video-tile ${isScreenShare && hasScreenShare
                    ? "col-span-full aspect-video"
                    : "aspect-video"
                    } ${isSpeaking
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
                </FullscreenVideo>
              );
            })}
          </div>
        )}

        {/* Audio-only participants strip */}
        <div className={`flex flex-wrap content-start ${isFloating ? 'gap-2 mt-auto pt-2' : 'gap-4 mt-auto pt-4'} border-t border-cyber-border/20`}>
          {audioOnlyParticipants.map((p) => (
            <ParticipantTile
              key={p.identity}
              participant={p}
              isLocal={p.identity === localParticipant?.identity}
              isFloating={isFloating}
            />
          ))}
        </div>
      </div>

      {/* Controls bar */}
      <div className={`voice-controls ${isFloating ? 'h-14 px-3 gap-2' : 'h-[72px] px-6 gap-4'} shrink-0 flex items-center justify-center border-t border-cyber-border/40 bg-cyber-surface/60 z-10`}>
        <button
          onClick={toggleMute}
          className={`px-4 py-2 rounded-xl ${isFloating ? 'text-[10px] min-w-0 flex-1 px-2 py-1.5' : 'text-sm py-2.5 min-w-[120px]'} font-display font-bold uppercase tracking-wider
                      transition-all duration-300 cursor-pointer 
                      ${muted
              ? "bg-neon-red/10 border border-neon-red/60 text-neon-red hover:bg-neon-red/20 hover:border-neon-red"
              : "bg-neon-green/10 border border-neon-green/60 text-neon-green hover:bg-neon-green/20 hover:border-neon-green hover:glow-green"
            }`}
          title={muted ? "Unmute" : "Mute"}
          aria-label={muted ? "Unmute microphone" : "Mute microphone"}
        >
          {muted ? <MicOff size={20} /> : <Mic size={20} />}{!isFloating && <span>{muted ? "Unmute" : "Mute"}</span>}
        </button>

        <button
          onClick={toggleCamera}
          className={`px-4 py-2 rounded-xl ${isFloating ? 'text-[10px] min-w-0 flex-1 px-2 py-1.5' : 'text-sm py-2.5 min-w-[120px]'} font-display font-bold uppercase tracking-wider
                      transition-all duration-300 cursor-pointer 
                      ${cameraOn
              ? "bg-neon-cyan/10 border border-neon-cyan text-neon-cyan glow-cyan hover:bg-neon-cyan/20"
              : "bg-neon-cyan/5 border border-neon-cyan/40 text-neon-cyan/60 hover:border-neon-cyan/80 hover:text-neon-cyan"
            }`}
          title={cameraOn ? "Turn camera off" : "Turn camera on"}
          aria-label={cameraOn ? "Turn camera off" : "Turn camera on"}
        >
          {cameraOn ? <Video size={20} /> : <VideoOff size={20} />}{!isFloating && <span>Camera</span>}
        </button>

        <button
          onClick={toggleScreenShare}
          disabled={screenSharePending}
          aria-busy={screenSharePending}
          className={`px-4 py-2 rounded-xl ${isFloating ? 'text-[10px] min-w-0 flex-1 px-2 py-1.5' : 'text-sm py-2.5 min-w-[120px]'} font-display font-bold uppercase tracking-wider
                      transition-all duration-300 cursor-pointer 
                      ${screenShareOn
              ? "bg-neon-purple/10 border border-neon-purple text-neon-purple glow-purple hover:bg-neon-purple/20"
              : "bg-neon-purple/5 border border-neon-purple/40 text-neon-purple/60 hover:border-neon-purple/80 hover:text-neon-purple"
            }`}
          title={screenShareOn ? "Stop screen share" : "Share screen"}
          aria-label={screenShareOn ? "Stop screen share" : "Share screen"}
        >
          {screenSharePending ? <LoaderCircle size={20} className="animate-spin" /> : <Monitor size={20} />}{!isFloating && <span>{screenSharePending ? (screenShareOn ? "Stopping…" : "Starting…") : screenShareOn ? "Stop sharing" : "Share screen"}</span>}
        </button>

        <button
          onClick={onLeave}
          className={`rounded-xl ${isFloating ? 'text-[14px] min-w-0 w-8 h-8 flex items-center justify-center p-0' : 'text-sm py-2.5 px-4 min-w-[120px]'} font-display font-bold uppercase tracking-wider
                     bg-neon-red/10 border border-neon-red/60 text-neon-red
                     hover:bg-neon-red/20 hover:border-neon-red transition-all duration-300 cursor-pointer`}
          title="Disconnect"
        >
          <PhoneOff size={20} />{!isFloating && <span>Leave</span>}
        </button>
      </div>

      {showCamPreview && (
        <CameraPreviewModal onPublished={confirmCamera} onCancel={cancelCamera} />
      )}
      {showScreenPreview && (
        <ScreenSharePreviewModal onPublished={() => setShowScreenPreview(false)} onCancel={() => setShowScreenPreview(false)} />
      )}
    </div>
  );
}

function ParticipantTile({ participant, isLocal, isFloating }) {
  const isSpeaking = participant.isSpeaking;
  const { members } = useServerPresence();

  return (
    <div
      className={`${isFloating ? 'w-16 h-16 rounded-xl' : 'w-28 h-28 rounded-2xl'} shrink-0 flex flex-col items-center justify-center gap-1.5
                  bg-cyber-surface/40 backdrop-blur-sm border transition-all duration-300
                  ${isSpeaking
          ? "border-neon-green/60 glow-green speaking-pulse"
          : "border-cyber-border/30 hover:border-cyber-border/60"
        }`}
    >
      {/* Avatar circle */}
      <div className="relative">
        <Avatar username={participant.name || participant.identity} avatar={members.find(({ id }) => id === participant.identity)?.avatar} size={isFloating ? "voice-avatar-small" : ""} />
        <div className={`absolute -bottom-1 -right-1 ${isFloating ? 'w-3 h-3 text-[6px]' : 'w-4 h-4 text-[8px]'} rounded-full bg-cyber-bg border border-cyber-border/50 flex items-center justify-center`}>
          {participant.isMicrophoneEnabled ? (
            <Mic size={isFloating ? 8 : 11} className="text-neon-green" />
          ) : (
            <MicOff size={isFloating ? 8 : 11} className="text-neon-red" />
          )}
        </div>
      </div>
      <div className="text-center px-1 w-full">
        <span className={`text-[8px] ${isFloating ? 'max-w-[50px] mx-auto' : 'sm:text-[10px] max-w-[90px] mx-auto'} text-cyber-text/80 truncate block font-display font-medium`}>
          {participant.name || participant.identity}
        </span>
        {isLocal && !isFloating && (
          <span className="text-[8px] text-neon-cyan/60 uppercase tracking-widest block">you</span>
        )}
      </div>
    </div>
  );
}
