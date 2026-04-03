import { useState, useEffect } from "react";
import { channels as channelsApi, invites as invitesApi } from "../api/client";
import { getInviteCacheTtlHours, getInviteCacheTtlMs } from "../utils/runtime";

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

export default function ChannelList({ server, activeChannel, onSelect }) {
  const [channelList, setChannelList] = useState([]);
  const [inviteCode, setInviteCode] = useState(null);
  const [inviteLoading, setInviteLoading] = useState(false);
  const [showCreateChannel, setShowCreateChannel] = useState(false);
  const [newChannelName, setNewChannelName] = useState("");
  const [newChannelType, setNewChannelType] = useState("text");
  const [createChannelLoading, setCreateChannelLoading] = useState(false);
  const [createChannelError, setCreateChannelError] = useState("");

  useEffect(() => {
    setInviteCode(null);
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
      .then((data) => setChannelList(data.channels || []))
      .catch(() => {});
  }, [server]);

  if (!server) {
    return (
      <div className="w-60 bg-cyber-panel/50 border-r border-cyber-border/40 flex flex-col items-center justify-center gap-3">
        <div className="w-12 h-12 rounded-xl bg-cyber-border/20 flex items-center justify-center text-cyber-muted/40 text-2xl">
          ◇
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
    try {
      const cachedInvite = readCachedInvite(server.id);
      if (cachedInvite && !isCachedInviteExpired(cachedInvite)) {
        setInviteCode(cachedInvite.code);
        return;
      }

      if (cachedInvite) {
        clearCachedInvite(server.id);
      }

      const code = await createFreshInvite();
      if (code) {
        setInviteCode(code);
      }
    } catch {
      // silently fail if no permission
    } finally {
      setInviteLoading(false);
    }
  };

  const handleGenerateFreshInvite = async () => {
    setInviteLoading(true);
    try {
      const code = await createFreshInvite();
      if (code) {
        setInviteCode(code);
      }
    } catch {
      // silently fail if no permission
    } finally {
      setInviteLoading(false);
    }
  };

  const copyInviteLink = () => {
    const link = `${window.location.origin}/invite/${inviteCode}`;
    navigator.clipboard.writeText(link);
  };

  const closeInvite = () => {
    setInviteCode(null);
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
    if (!name) {
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
      onSelect(createdChannel);
      closeCreateChannel();
    } catch (error) {
      setCreateChannelError(error.message || "Could not create channel");
    } finally {
      setCreateChannelLoading(false);
    }
  };

  const voiceChannels = channelList.filter((c) => c.type === "voice");
  const textChannels = channelList.filter((c) => c.type === "text");

  return (
    <>
      <div className="w-60 bg-cyber-panel/50 border-r border-cyber-border/40 flex flex-col">
        {/* Server name header */}
        <div className="px-4 h-12 flex items-center border-b border-cyber-border/40 bg-cyber-surface/30">
          <h2 className="text-sm font-display font-bold text-cyber-text uppercase tracking-wider truncate">
            {server.name}
          </h2>
          <div className="ml-auto flex items-center gap-1.5">
            <span className="text-[10px] text-cyber-muted bg-cyber-bg/40 px-2 py-0.5 rounded-full">
              {channelList.length}
            </span>
            <button
              onClick={() => (showCreateChannel ? closeCreateChannel() : openCreateChannel("text"))}
              className="rounded border border-neon-cyan/20 bg-neon-cyan/5 px-2 py-1 text-[10px] font-display font-semibold uppercase tracking-[0.16em] text-neon-cyan/75 transition hover:border-neon-cyan/40 hover:bg-neon-cyan/15 hover:text-neon-cyan"
            >
              {showCreateChannel ? "Close" : "+ Channel"}
            </button>
          </div>
        </div>

        {showCreateChannel && (
          <div className="border-b border-cyber-border/20 bg-cyber-surface/10 px-3 py-2.5">
            <form className="space-y-2.5" onSubmit={handleCreateChannel}>
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => setNewChannelType("text")}
                  className={`flex-1 rounded border px-2 py-1 text-[10px] font-display font-semibold uppercase tracking-[0.16em] transition
                              ${
                                newChannelType === "text"
                                  ? "border-neon-cyan/45 bg-neon-cyan/15 text-neon-cyan"
                                  : "border-cyber-border/50 bg-cyber-panel/50 text-cyber-muted hover:border-cyber-muted/60 hover:text-cyber-text"
                              }`}
                >
                  # Text
                </button>
                <button
                  type="button"
                  onClick={() => setNewChannelType("voice")}
                  className={`flex-1 rounded border px-2 py-1 text-[10px] font-display font-semibold uppercase tracking-[0.16em] transition
                              ${
                                newChannelType === "voice"
                                  ? "border-neon-cyan/45 bg-neon-cyan/15 text-neon-cyan"
                                  : "border-cyber-border/50 bg-cyber-panel/50 text-cyber-muted hover:border-cyber-muted/60 hover:text-cyber-text"
                              }`}
                >
                  O Voice
                </button>
              </div>

              <div className="flex items-center rounded border border-cyber-border/50 bg-cyber-panel/60">
                <span className="pl-2 text-[11px] text-neon-cyan/65">
                  {newChannelType === "text" ? "#" : "O"}
                </span>
                <input
                  autoFocus
                  value={newChannelName}
                  onChange={(event) => setNewChannelName(event.target.value)}
                  placeholder="Channel name"
                  maxLength={48}
                  className="w-full bg-transparent px-2.5 py-2 text-sm text-cyber-text outline-none"
                />
              </div>

              {createChannelError && (
                <p className="text-[11px] text-neon-red/80">{createChannelError}</p>
              )}

              <div className="flex items-center justify-end gap-1.5">
                <button
                  type="button"
                  onClick={closeCreateChannel}
                  disabled={createChannelLoading}
                  className="rounded border border-cyber-border px-2.5 py-1 text-[10px] font-display uppercase tracking-[0.16em] text-cyber-muted transition hover:border-cyber-muted/70 hover:text-cyber-text disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createChannelLoading || !newChannelName.trim()}
                  className="rounded border border-neon-cyan/40 bg-neon-cyan/10 px-2.5 py-1 text-[10px] font-display uppercase tracking-[0.16em] text-neon-cyan transition hover:bg-neon-cyan/20 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {createChannelLoading ? "Creating..." : "Create"}
                </button>
              </div>
            </form>
          </div>
        )}

        {/* Invite section */}
        <div className="px-3 py-2 border-b border-cyber-border/20">
          {inviteCode ? (
            <div className="flex items-center gap-1.5">
              <input
                readOnly
                value={`${window.location.origin}/invite/${inviteCode}`}
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
                ⧉
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
                ↻
              </button>
              <button
                type="button"
                onClick={closeInvite}
                aria-label="Close invite link"
                title="Close invite link"
                className="inline-flex h-7 w-7 items-center justify-center rounded bg-cyber-border/20 text-[11px]
                         leading-none text-cyber-muted transition hover:bg-cyber-border/35 hover:text-cyber-text"
              >
                ✕
              </button>
            </div>
          ) : (
            <button
              onClick={handleCreateInvite}
              disabled={inviteLoading}
              className="w-full py-1.5 text-[11px] font-display font-semibold uppercase tracking-wider
                       text-neon-cyan/70 hover:text-neon-cyan bg-neon-cyan/5 hover:bg-neon-cyan/10
                       border border-neon-cyan/15 hover:border-neon-cyan/30
                       rounded transition cursor-pointer disabled:opacity-40"
            >
              {inviteLoading ? "Creating..." : "+ Create Invite"}
            </button>
          )}
        </div>

        <div className="flex-1 overflow-y-auto py-3">
          {channelList.length === 0 && (
            <div className="px-4 py-6 text-center">
              <p className="text-[11px] font-display uppercase tracking-[0.2em] text-cyber-muted/60">
                No channels yet
              </p>
              <button
                type="button"
                onClick={() => openCreateChannel("text")}
                className="mt-3 rounded border border-neon-cyan/20 bg-neon-cyan/5 px-2.5 py-1 text-[10px] font-display font-semibold uppercase tracking-[0.16em] text-neon-cyan/75 transition hover:border-neon-cyan/40 hover:bg-neon-cyan/15 hover:text-neon-cyan"
              >
                + Create First Channel
              </button>
            </div>
          )}

          {/* Text channels */}
          {textChannels.length > 0 && (
            <div className="mb-4">
              <div className="px-4 mb-2 flex items-center gap-2">
                <span className="h-px flex-1 bg-cyber-border/30" />
                <p className="text-[10px] text-cyber-muted/70 uppercase tracking-[0.2em] font-display font-semibold">
                  Text
                </p>
                <button
                  type="button"
                  onClick={() => openCreateChannel("text")}
                  className="rounded border border-cyber-border/40 px-1.5 py-0.5 text-[10px] text-cyber-muted transition hover:border-neon-cyan/40 hover:text-neon-cyan"
                >
                  +
                </button>
                <span className="h-px flex-1 bg-cyber-border/30" />
              </div>
              {textChannels.map((ch) => (
                <ChannelItem
                  key={ch.id}
                  channel={ch}
                  active={activeChannel?.id === ch.id}
                  onSelect={onSelect}
                  icon="#"
                />
              ))}
            </div>
          )}

          {/* Voice channels */}
          {voiceChannels.length > 0 && (
            <div>
              <div className="px-4 mb-2 flex items-center gap-2">
                <span className="h-px flex-1 bg-cyber-border/30" />
                <p className="text-[10px] text-cyber-muted/70 uppercase tracking-[0.2em] font-display font-semibold">
                  Voice
                </p>
                <button
                  type="button"
                  onClick={() => openCreateChannel("voice")}
                  className="rounded border border-cyber-border/40 px-1.5 py-0.5 text-[10px] text-cyber-muted transition hover:border-neon-cyan/40 hover:text-neon-cyan"
                >
                  +
                </button>
                <span className="h-px flex-1 bg-cyber-border/30" />
              </div>
              {voiceChannels.map((ch) => (
                <ChannelItem
                  key={ch.id}
                  channel={ch}
                  active={activeChannel?.id === ch.id}
                  onSelect={onSelect}
                  icon="◈"
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

function ChannelItem({ channel, active, onSelect, icon }) {
  return (
    <button
      onClick={() => onSelect(channel)}
      className={`w-full px-3 py-1.5 mx-0 flex items-center gap-2.5 text-sm transition-all duration-200 cursor-pointer
                  group rounded-none
                  ${
                    active
                      ? "bg-neon-cyan/8 text-neon-cyan border-l-2 border-neon-cyan pl-[10px]"
                      : "text-cyber-muted hover:text-cyber-text hover:bg-cyber-hover/50 border-l-2 border-transparent pl-[10px]"
                  }`}
    >
      <span className={`text-xs ${active ? "text-neon-cyan/80" : "text-cyber-muted/40 group-hover:text-cyber-muted/70"} transition-colors`}>
        {icon}
      </span>
      <span className="truncate font-display font-medium text-[13px]">{channel.name}</span>
      {channel.user_limit > 0 && (
        <span className="ml-auto text-[9px] text-cyber-muted/50 tabular-nums">{channel.user_limit}</span>
      )}
    </button>
  );
}
