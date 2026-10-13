import { useState, useEffect } from "react";
import { Video, Monitor, Hash, Volume2, Plus, Copy, RefreshCw, X, Play, UserPlus } from "lucide-react";
import Avatar from "./Avatar";
import { channels as channelsApi, invites as invitesApi } from "../api/client";
import { useServerPresence } from "../context/ServerPresenceContext";
import { getInviteCacheTtlHours, getInviteCacheTtlMs } from "../utils/runtime";
import { buildInviteLink } from "../utils/inviteLink";

const INVITE_CACHE_PREFIX = "synth:invite-cache";
const INVITE_EXPIRES_IN_HOURS = getInviteCacheTtlHours();
const INVITE_CACHE_TTL_MS = getInviteCacheTtlMs();

const getInviteCacheKey = (serverId) => `${INVITE_CACHE_PREFIX}:${serverId}`;

const readCachedInvite = (serverId) => {
  if (!serverId || typeof window === "undefined") {
    return null;
  }

  const cacheKey = getInviteCacheKey(serverId);
  try {
    const raw = window.localStorage.getItem(cacheKey);
    if (!raw) {
      return null;
    }

    const parsed = JSON.parse(raw);
    if (!parsed?.code || !parsed?.cachedAt) {
      window.localStorage.removeItem(cacheKey);
      return null;
    }

    return parsed;
  } catch {
    window.localStorage.removeItem(cacheKey);
    return null;
  }
};

const writeCachedInvite = (serverId, invite) => {
  if (!serverId || !invite?.code || typeof window === "undefined") {
    return;
  }

  const payload = {
    code: invite.code,
    cachedAt: Date.now(),
    expiresAt: invite.expires_at || null,
  };

  try {
    window.localStorage.setItem(getInviteCacheKey(serverId), JSON.stringify(payload));
  } catch {
    // Ignore localStorage write failures.
  }
};

const clearCachedInvite = (serverId) => {
  if (!serverId || typeof window === "undefined") {
    return;
  }

  try {
    window.localStorage.removeItem(getInviteCacheKey(serverId));
  } catch {
    // Ignore localStorage remove failures.
  }
};

const isCachedInviteExpired = (cachedInvite) => {
  if (!cachedInvite?.code) {
    return true;
  }

  const cachedAtMs = Number(cachedInvite.cachedAt || 0);
  if (!Number.isFinite(cachedAtMs) || cachedAtMs <= 0) {
    return true;
  }

  const now = Date.now();
  if (now - cachedAtMs >= INVITE_CACHE_TTL_MS) {
    return true;
  }

  const expiresAtMs = Date.parse(cachedInvite.expiresAt || "");
  if (Number.isFinite(expiresAtMs) && expiresAtMs <= now) {
    return true;
  }

  return false;
};

export default function ChannelList({ server, activeChannel, onSelect, onChannelsLoaded }) {
  const { voiceChannels } = useServerPresence();

  const [channelList, setChannelList] = useState([]);
  const [inviteLink, setInviteLink] = useState(null);
  const [inviteError, setInviteError] = useState("");
  const [inviteLoading, setInviteLoading] = useState(false);
  const [showCreateChannel, setShowCreateChannel] = useState(false);
  const [newChannelName, setNewChannelName] = useState("");
  const [newChannelType, setNewChannelType] = useState("text");
  const [createChannelLoading, setCreateChannelLoading] = useState(false);
  const [createChannelError, setCreateChannelError] = useState("");

  useEffect(() => {
    let active = true;
    setInviteLink(null);
    setInviteError("");
    setShowCreateChannel(false);
    setCreateChannelError("");
    setNewChannelName("");
    setNewChannelType("text");
    if (!server) {
      setChannelList([]);
      return;
    }

    channelsApi
      .list(server.id)
      .then((data) => {
        if (!active) return;
        setChannelList(data.channels || []);
        onChannelsLoaded?.(data.channels || [], server.id);
      })
      .catch(() => { });
    return () => { active = false; };
  }, [server, onChannelsLoaded]);

  if (!server) {
    return (
      <div className="w-60 bg-cyber-panel/50 border-r border-cyber-border/40 flex flex-col items-center justify-center gap-3">
        <div className="w-12 h-12 rounded-xl bg-cyber-border/20 flex items-center justify-center text-cyber-muted/40 text-2xl">
          <Hash size={26} aria-hidden="true" />
        </div>
        <p className="text-cyber-muted/60 text-xs font-display uppercase tracking-widest">Select a server</p>
      </div>
    );
  }

  const createFreshInvite = async () => {
    const data = await invitesApi.create(server.id, {
      max_uses: 0,
      expires_in_hours: INVITE_EXPIRES_IN_HOURS,
    });
    if (!data?.invite?.code) {
      return null;
    }

    writeCachedInvite(server.id, data.invite);
    return data.invite.code;
  };

  const handleCreateInvite = async () => {
    setInviteLoading(true);
    setInviteError("");
    try {
      const cachedInvite = readCachedInvite(server.id);
      if (cachedInvite && !isCachedInviteExpired(cachedInvite)) {
        setInviteLink(buildInviteLink(cachedInvite.code));
        return;
      }

      if (cachedInvite) {
        clearCachedInvite(server.id);
      }

      const code = await createFreshInvite();
      if (code) {
        setInviteLink(buildInviteLink(code));
      }
    } catch (error) {
      setInviteError(error.message);
    } finally {
      setInviteLoading(false);
    }
  };

  const handleGenerateFreshInvite = async () => {
    setInviteLoading(true);
    setInviteError("");
    try {
      const code = await createFreshInvite();
      if (code) {
        setInviteLink(buildInviteLink(code));
      }
    } catch (error) {
      setInviteError(error.message);
    } finally {
      setInviteLoading(false);
    }
  };

  const copyInviteLink = async () => {
    try {
      await navigator.clipboard.writeText(inviteLink);
      setInviteError("");
    } catch {
      setInviteError("Could not copy the invite. Select and copy the link above.");
    }
  };

  const closeInvite = () => {
    setInviteLink(null);
    setInviteError("");
  };

  const openCreateChannel = (channelType = "text") => {
    setNewChannelType(channelType);
    setNewChannelName("");
    setCreateChannelError("");
    setShowCreateChannel(true);
  };

  const closeCreateChannel = () => {
    setNewChannelName("");
    setNewChannelType("text");
    setCreateChannelError("");
    setShowCreateChannel(false);
  };

  const handleCreateChannel = async (event) => {
    event.preventDefault();
    const name = newChannelName.trim();
    if (!name || createChannelLoading) {
      return;
    }

    setCreateChannelLoading(true);
    setCreateChannelError("");
    try {
      const data = await channelsApi.create(server.id, name, newChannelType);
      const rawChannel = data.channel;
      if (!rawChannel) {
        throw new Error("Channel could not be created");
      }

      const createdChannel = {
        ...rawChannel,
        type: rawChannel.type || rawChannel.channel_type || newChannelType,
      };

      setChannelList((prev) => [...prev, createdChannel]);
      onChannelsLoaded?.([...channelList, createdChannel], server.id);
      onSelect(createdChannel);
      closeCreateChannel();
    } catch (error) {
      setCreateChannelError(error.message || "Could not create channel");
    } finally {
      setCreateChannelLoading(false);
    }
  };

  const voiceChannelsList = channelList.filter((c) => c.type === "voice");
  const textChannels = channelList.filter((c) => c.type === "text");

  return (
    <>
      <div className="channel-navigation">
        <div className="channel-navigation-actions">
          <button className="server-action" onClick={handleCreateInvite} disabled={inviteLoading}><UserPlus size={18} aria-hidden="true" />{inviteLoading ? "Creating…" : "Create invite"}</button>
          <button className="server-action" aria-expanded={showCreateChannel} disabled={createChannelLoading} onClick={() => (showCreateChannel ? closeCreateChannel() : openCreateChannel("text"))}><Plus size={18} aria-hidden="true" />Create channel</button>
        </div>

        {showCreateChannel && (
          <section className="channel-create-panel" aria-label="Create a channel">
            <form className="channel-create-form" onSubmit={handleCreateChannel}>
              <fieldset className="channel-type-picker">
                <legend className="sr-only">Channel type</legend>
                <button
                  type="button"
                  onClick={() => setNewChannelType("text")}
                  aria-pressed={newChannelType === "text"}
                  disabled={createChannelLoading}
                >
                  <Hash size={18} aria-hidden="true" />Text
                </button>
                <button
                  type="button"
                  onClick={() => setNewChannelType("voice")}
                  aria-pressed={newChannelType === "voice"}
                  disabled={createChannelLoading}
                >
                  <Volume2 size={18} aria-hidden="true" />Voice
                </button>
              </fieldset>

              <label className="channel-name-field">
                {newChannelType === "text" ? <Hash size={18} aria-hidden="true" /> : <Volume2 size={18} aria-hidden="true" />}
                <input
                  autoFocus
                  aria-label="Channel name"
                  disabled={createChannelLoading}
                  value={newChannelName}
                  onChange={(event) => setNewChannelName(event.target.value)}
                  placeholder="Channel name"
                  maxLength={48}
                />
              </label>

              {createChannelError && (
                <p role="alert" className="form-error">{createChannelError}</p>
              )}

              <div className="channel-form-actions">
                <button
                  type="button"
                  onClick={closeCreateChannel}
                  disabled={createChannelLoading}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createChannelLoading || !newChannelName.trim()}
                >
                  {createChannelLoading ? "Creating..." : "Create"}
                </button>
              </div>
            </form>
          </section>
        )}

        {/* Invite section */}
        {(inviteLink || inviteError) && <section className="invite-tools" aria-label="Server invite">
          {inviteLink && <>
            <label htmlFor="server-invite-link" className="invite-link-label">Invite link</label>
            <div className="invite-link-row">
              <input
                id="server-invite-link"
                readOnly
                value={inviteLink}
                className="flex-1 text-[10px] bg-cyber-bg/60 text-neon-cyan border border-cyber-border/30
                         rounded px-2 py-1.5 font-mono truncate outline-none"
              />
              <button
                type="button"
                onClick={copyInviteLink}
                aria-label="Copy invite link"
                title="Copy invite link"
                className="inline-flex h-7 w-7 items-center justify-center rounded bg-neon-cyan/10 text-[12px]
                         leading-none text-neon-cyan transition hover:bg-neon-cyan/20"
              >
                <Copy size={16} />
              </button>
              <button
                type="button"
                onClick={handleGenerateFreshInvite}
                disabled={inviteLoading}
                aria-label="Generate fresh invite link"
                title="Generate fresh invite link"
                className="inline-flex h-7 w-7 items-center justify-center rounded bg-neon-cyan/5 text-[12px]
                         leading-none text-neon-cyan/80 transition hover:bg-neon-cyan/15 hover:text-neon-cyan
                         disabled:cursor-not-allowed disabled:opacity-40"
              >
                <RefreshCw size={16} />
              </button>
              <button
                type="button"
                onClick={closeInvite}
                aria-label="Close invite link"
                title="Close invite link"
                className="inline-flex h-7 w-7 items-center justify-center rounded bg-cyber-border/20 text-[11px]
                         leading-none text-cyber-muted transition hover:bg-cyber-border/35 hover:text-cyber-text"
              >
                <X size={16} />
              </button>
            </div>
          </>}
          {inviteError && <p role="alert" className="mt-2 text-xs text-neon-red">{inviteError}</p>}
        </section>}

        <div className="flex-1 overflow-y-auto py-3">
          {/* Text channels */}
            <section className="mb-4">
              <div className="sidebar-section-title">
                <p className="text-[10px] text-cyber-muted/70 uppercase tracking-[0.2em] font-display font-semibold">
                  Text channels
                </p>
              </div>
              {textChannels.length === 0 && <p className="channel-empty">No text channels yet.</p>}
              {textChannels.map((ch) => (
                <ChannelItem
                  key={ch.id}
                  channel={ch}
                  active={activeChannel?.id === ch.id}
                  onSelect={onSelect}
                />
              ))}
            </section>

          {/* Voice channels */}
            <section>
              <div className="sidebar-section-title">
                <p className="text-[10px] text-cyber-muted/70 uppercase tracking-[0.2em] font-display font-semibold">
                  Voice channels
                </p>
              </div>
              {voiceChannelsList.length === 0 && <p className="channel-empty">No voice channels yet.</p>}
              {voiceChannelsList.map((ch) => (
                <ChannelItem
                  key={ch.id}
                  channel={ch}
                  active={activeChannel?.id === ch.id}
                  onSelect={onSelect}
                  participants={voiceChannels[ch.id] || []}
                />
              ))}
            </section>
        </div>
      </div>
    </>
  );
}

function ChannelItem({ channel, active, onSelect, participants = [] }) {
  const { members } = useServerPresence();
  const isVoice = channel.type === "voice";

  return (
    <div className="flex flex-col">
      <div
        className={`channel-nav-row group ${active ? "is-active" : ""}`}
      >
        <button
          onClick={() => onSelect(channel)}
          className="flex items-center gap-2.5 flex-1 min-w-0 cursor-pointer"
        >
          {isVoice ? <Volume2 size={23} /> : <Hash size={25} />}
          <span className="truncate">{channel.name}</span>
        </button>

        <div className="flex items-center gap-1.5 ml-auto">
          {channel.user_limit > 0 && (
            <span className="text-[9px] text-cyber-muted/50 tabular-nums">{channel.user_limit}</span>
          )}
          {isVoice && !active && (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); onSelect(channel); }}
              title="Join voice channel"
              className="opacity-0 group-hover:opacity-100 w-5 h-5 rounded flex items-center justify-center
                         text-[10px] text-neon-green/70 bg-neon-green/10 border border-neon-green/20
                         hover:bg-neon-green/20 hover:text-neon-green hover:border-neon-green/40
                         transition-all cursor-pointer"
            >
              <Play size={13} />
            </button>
          )}
        </div>
      </div>

      {participants.length > 0 && (
        <div className="channel-participants">
          {participants.slice(0, 3).map((p) => {
            const isCamOn = p.tracks?.some(t => t.source === "camera" && !t.muted);
            const isScreenOn = p.tracks?.some(t => t.source === "screen_share" && !t.muted);

            return (
              <div key={p.identity} className="flex items-center gap-2 group cursor-default">
                <Avatar username={p.name} avatar={members.find(({ id }) => id === p.identity)?.avatar} />
                <div className="flex items-center gap-1.5 text-[10px]">
                  {isCamOn && (
                    <Video size={10} className="text-neon-cyan/70 drop-shadow-[0_0_2px_rgba(0,255,255,0.4)]" />
                  )}
                  {isScreenOn && (
                    <Monitor size={10} className="text-neon-purple/70 drop-shadow-[0_0_2px_rgba(188,19,254,0.4)]" />
                  )}
                </div>
              </div>
            );
          })}
          <span>{participants.length} in voice</span>
        </div>
      )}
    </div>
  );
}
