import { useState, useEffect, useRef, useCallback } from "react";
import { dms as dmsApi, friends as friendsApi } from "../api/client";
import { useAuth } from "../context/AuthContext";

// ── Helpers ───────────────────────────────────────────────

function formatTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);

  if (d.toDateString() === today.toDateString()) return "Today";
  if (d.toDateString() === yesterday.toDateString()) return "Yesterday";
  return d.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
}

function groupByDate(msgs) {
  const groups = [];
  let currentDate = null;
  for (const msg of msgs) {
    const date = msg.created_at ? new Date(msg.created_at).toDateString() : "Unknown";
    if (date !== currentDate) {
      currentDate = date;
      groups.push({ type: "separator", label: formatDate(msg.created_at) });
    }
    groups.push({ type: "message", ...msg });
  }
  return groups;
}

function getInitials(name) {
  return (name || "?").slice(0, 2).toUpperCase();
}

// ── Avatar ────────────────────────────────────────────────

function Avatar({ username, avatar, size = "w-8 h-8" }) {
  return avatar ? (
    <img
      src={avatar}
      alt={username}
      className={`${size} rounded-full object-cover flex-shrink-0`}
    />
  ) : (
    <div
      className={`${size} rounded-full flex items-center justify-center flex-shrink-0
                  bg-gradient-to-br from-neon-cyan/20 to-neon-purple/20
                  border border-neon-cyan/20 text-neon-cyan font-display font-bold text-xs`}
    >
      {getInitials(username)}
    </div>
  );
}

// ── Message bubble ─────────────────────────────────────────

function MessageBubble({ msg, isOwn, onEdit, onDelete, editingId, onCancelEdit, onSubmitEdit }) {
  const [hovered, setHovered] = useState(false);
  const [editContent, setEditContent] = useState(msg.content);
  const isEditing = editingId === msg.id;

  const handleEditKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSubmitEdit(msg.id, editContent);
    }
    if (e.key === "Escape") onCancelEdit();
  };

  return (
    <div
      className="flex gap-3 px-4 py-1 group relative"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div className="mt-0.5">
        <Avatar username={msg.sender_username} avatar={msg.sender_avatar} />
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-2 mb-0.5">
          <span
            className={`text-xs font-display font-bold tracking-wide
                        ${isOwn ? "text-neon-cyan" : "text-neon-pink"}`}
          >
            {msg.sender_username || "Unknown"}
          </span>
          <span className="text-[10px] text-cyber-muted/50 font-mono tabular-nums">
            {formatTime(msg.created_at)}
          </span>
          {msg.edited_at && (
            <span className="text-[9px] text-cyber-muted/35 font-mono italic">(edited)</span>
          )}
          {isOwn && msg.is_read && (
             <span className="text-[10px] text-neon-cyan/70 font-mono italic ml-1" title="Seen">✓✓</span>
          )}
        </div>

        {isEditing ? (
          <div className="mt-1">
            <textarea
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
              onKeyDown={handleEditKeyDown}
              rows={2}
              autoFocus
              className="w-full bg-cyber-surface border border-neon-cyan/40 rounded-lg
                         px-3 py-2 text-sm text-cyber-text font-mono resize-none
                         focus:outline-none focus:border-neon-cyan/70
                         focus:shadow-[0_0_0_2px_rgba(0,240,255,0.08)]
                         transition-all"
            />
            <div className="flex gap-2 mt-1.5">
              <button
                onClick={() => onSubmitEdit(msg.id, editContent)}
                className="px-3 py-1 text-[11px] font-display font-bold uppercase tracking-wider
                           bg-neon-cyan/10 border border-neon-cyan/40 text-neon-cyan
                           rounded hover:bg-neon-cyan/20 hover:border-neon-cyan/70 transition cursor-pointer"
              >
                Save
              </button>
              <button
                onClick={onCancelEdit}
                className="px-3 py-1 text-[11px] font-display font-bold uppercase tracking-wider
                           text-cyber-muted/60 hover:text-cyber-muted rounded transition cursor-pointer"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <p className="text-sm text-cyber-text/85 leading-relaxed whitespace-pre-wrap break-words font-mono">
            {msg.content}
          </p>
        )}
      </div>

      {hovered && !isEditing && (
        <div className="absolute right-4 top-1 flex items-center gap-1
                        bg-cyber-surface border border-cyber-border/60 rounded-lg shadow-xl
                        px-1.5 py-1 opacity-0 group-hover:opacity-100 transition-opacity">
          {isOwn && (
            <button
              onClick={() => onEdit(msg)}
              title="Edit"
              className="w-6 h-6 flex items-center justify-center rounded text-cyber-muted
                         hover:text-neon-cyan hover:bg-neon-cyan/10 transition text-xs cursor-pointer"
            >
              ✎
            </button>
          )}
          {isOwn && (
            <button
              onClick={() => onDelete(msg.id)}
              title="Delete"
              className="w-6 h-6 flex items-center justify-center rounded text-cyber-muted
                         hover:text-neon-red hover:bg-neon-red/10 transition text-xs cursor-pointer"
            >
              ✕
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ── Date separator ─────────────────────────────────────────

function DateSeparator({ label }) {
  return (
    <div className="flex items-center gap-3 px-4 py-2">
      <div className="flex-1 h-px bg-cyber-border/30" />
      <span className="text-[10px] text-cyber-muted/50 font-display uppercase tracking-[0.2em] px-2">
        {label}
      </span>
      <div className="flex-1 h-px bg-cyber-border/30" />
    </div>
  );
}

// ── Empty state ────────────────────────────────────────────

function EmptyState({ friendName }) {
  return (
    <div className="flex flex-col items-center justify-center flex-1 gap-4 p-8">
      <div className="w-16 h-16 rounded-2xl bg-cyber-surface border border-cyber-border/40
                      flex items-center justify-center text-neon-pink/30 text-3xl font-display">
        @
      </div>
      <div className="text-center">
        <p className="text-neon-pink font-display font-bold text-lg uppercase tracking-wider">
          {friendName}
        </p>
        <p className="text-cyber-muted/50 text-xs mt-1 font-mono">
          This is the beginning of your conversation. Say something!
        </p>
      </div>
    </div>
  );
}

// ── No friend selected ─────────────────────────────────────

function NoFriendSelected() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center bg-cyber-bg noise-texture gap-4">
      <div className="w-16 h-16 rounded-2xl bg-cyber-surface border border-cyber-border/30
                      flex items-center justify-center text-cyber-muted/30 text-3xl font-display">
        @
      </div>
      <div className="text-center">
        <p className="text-cyber-muted/50 text-sm font-display uppercase tracking-widest">
          Select a friend
        </p>
        <p className="text-cyber-muted/30 text-xs mt-1">
          Choose a friend from the panel to start chatting
        </p>
      </div>
    </div>
  );
}

// ── Main DMPanel ───────────────────────────────────────────

export default function DMPanel({ friend, onFriendRemoved }) {
  const { user } = useAuth();
  const [msgList, setMsgList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [error, setError] = useState("");
  const [removingFriend, setRemovingFriend] = useState(false);

  const bottomRef = useRef(null);
  const scrollRef = useRef(null);
  const textareaRef = useRef(null);
  const eventSourceRef = useRef(null);

  const currentUserId = user?.id || user?._id;

  // ── Scroll to bottom ────────────────────────────────────
  const scrollToBottom = useCallback((behavior = "smooth") => {
    bottomRef.current?.scrollIntoView({ behavior });
  }, []);

  // ── Load initial history ────────────────────────────────
  useEffect(() => {
    if (!friend) return;
    setMsgList([]);
    setLoading(true);
    setHasMore(true);
    setError("");
    setEditingId(null);
    setInput("");

    dmsApi
      .list(friend.id)
      .then((data) => {
        const fetched = data.messages || [];
        setMsgList(fetched);
        setHasMore(fetched.length === 50);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));

    // Mark messages as read when opening DM
    dmsApi.markRead(friend.id).catch(() => {});
  }, [friend?.id]);

  // ── Scroll to bottom on initial load ───────────────────
  useEffect(() => {
    if (!loading) scrollToBottom("instant");
  }, [loading]);

  // ── SSE — live updates ──────────────────────────────────
  useEffect(() => {
    if (!friend) return;

    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    const es = new EventSource(dmsApi.eventsUrl(friend.id));
    eventSourceRef.current = es;

    es.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data);
        if (event.type === "dm") {
          setMsgList((prev) => {
            if (prev.some((m) => m.id === event.data.id)) return prev;
            return [...prev, event.data];
          });
          
          if (event.data.sender_id !== currentUserId) {
            dmsApi.markRead(friend.id).catch(() => {});
          }
          
          const el = scrollRef.current;
          if (el) {
            const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
            if (nearBottom) setTimeout(() => scrollToBottom("smooth"), 50);
          }
        } else if (event.type === "dm_edit") {
          setMsgList((prev) =>
            prev.map((m) => (m.id === event.data.id ? { ...m, ...event.data } : m))
          );
        } else if (event.type === "dm_delete") {
          setMsgList((prev) => prev.filter((m) => m.id !== event.data.id));
        } else if (event.type === "dm_read") {
          if (event.data.by !== currentUserId) {
            setMsgList((prev) =>
              prev.map((m) => (m.sender_id === currentUserId ? { ...m, is_read: true } : m))
            );
          }
        }
      } catch {
        // malformed SSE data
      }
    };

    es.onerror = () => {};

    return () => {
      es.close();
      eventSourceRef.current = null;
    };
  }, [friend?.id]);

  // ── Load older messages ─────────────────────────────────
  const handleScroll = useCallback(async () => {
    const el = scrollRef.current;
    if (!el || loadingMore || !hasMore || el.scrollTop > 80) return;

    const oldest = msgList[0];
    if (!oldest) return;

    setLoadingMore(true);
    const prevHeight = el.scrollHeight;

    try {
      const data = await dmsApi.list(friend.id, oldest.id);
      const older = data.messages || [];
      setMsgList((prev) => [...older, ...prev]);
      setHasMore(older.length === 50);
      requestAnimationFrame(() => {
        el.scrollTop = el.scrollHeight - prevHeight;
      });
    } catch {
      // silently fail
    } finally {
      setLoadingMore(false);
    }
  }, [friend?.id, msgList, loadingMore, hasMore]);

  // ── Send message ────────────────────────────────────────
  const handleSend = useCallback(async () => {
    const content = input.trim();
    if (!content || sending) return;

    setSending(true);
    setInput("");
    setError("");

    try {
      const data = await dmsApi.send(friend.id, content);
      setMsgList((prev) => {
        if (prev.some((m) => m.id === data.message.id)) return prev;
        return [...prev, data.message];
      });
      setTimeout(() => scrollToBottom("smooth"), 50);
    } catch (e) {
      setError(e.message);
      setInput(content);
    } finally {
      setSending(false);
      textareaRef.current?.focus();
    }
  }, [input, sending, friend?.id]);

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // ── Edit ────────────────────────────────────────────────
  const startEdit = (msg) => setEditingId(msg.id);
  const cancelEdit = () => setEditingId(null);

  const submitEdit = useCallback(async (messageId, content) => {
    const trimmed = content.trim();
    if (!trimmed) return;
    try {
      const data = await dmsApi.edit(friend.id, messageId, trimmed);
      setMsgList((prev) =>
        prev.map((m) => (m.id === messageId ? { ...m, ...data.message } : m))
      );
    } catch (e) {
      setError(e.message);
    } finally {
      setEditingId(null);
    }
  }, [friend?.id]);

  // ── Delete ──────────────────────────────────────────────
  const handleDelete = useCallback(async (messageId) => {
    try {
      await dmsApi.delete(friend.id, messageId);
      setMsgList((prev) => prev.filter((m) => m.id !== messageId));
    } catch (e) {
      setError(e.message);
    }
  }, [friend?.id]);

  // ── Remove friend ──────────────────────────────────────
  const handleRemoveFriend = async () => {
    if (!window.confirm(`Remove ${friend.username} from your friends?`)) return;
    setRemovingFriend(true);
    try {
      await friendsApi.remove(friend.id);
      onFriendRemoved?.(friend.id);
    } catch (e) {
      setError(e.message);
    } finally {
      setRemovingFriend(false);
    }
  };

  // ── Guard: no friend selected (AFTER all hooks) ────────
  if (!friend) {
    return <NoFriendSelected />;
  }

  const items = groupByDate(msgList);

  return (
    <div className="flex-1 flex flex-col bg-cyber-bg noise-texture overflow-hidden">
      {/* ── Header ── */}
      <div className="px-5 h-14 flex items-center border-b border-cyber-border/40
                      bg-cyber-surface/40 gap-3 flex-shrink-0">
        <span className="text-neon-pink/60 font-display font-bold text-lg">@</span>
        <h3 className="font-display font-bold text-sm text-cyber-text uppercase tracking-wider">
          {friend.username}
        </h3>
        <span
          className={`w-2 h-2 rounded-full ${
            friend.is_online ? "bg-neon-green online-pulse" : "bg-cyber-muted/40"
          }`}
        />
        <span className="text-[10px] text-cyber-muted/50 font-mono">
          {friend.is_online ? "Online" : "Offline"}
        </span>

        <div className="ml-auto">
          <button
            onClick={handleRemoveFriend}
            disabled={removingFriend}
            title="Remove friend"
            className="px-2.5 py-1 text-[10px] font-display font-bold uppercase tracking-wider
                       text-cyber-muted/50 border border-cyber-border/40 rounded-md
                       hover:text-neon-red hover:border-neon-red/40 hover:bg-neon-red/10
                       disabled:opacity-40 transition cursor-pointer"
          >
            {removingFriend ? "..." : "Remove Friend"}
          </button>
        </div>
      </div>

      {/* ── Message list ── */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto py-2 flex flex-col"
      >
        {loadingMore && (
          <div className="text-center py-2">
            <span className="text-[10px] text-cyber-muted/40 font-display animate-pulse">
              Loading older messages…
            </span>
          </div>
        )}

        {!hasMore && msgList.length > 0 && (
          <p className="text-center text-[10px] text-cyber-muted/30 font-mono py-4">
            — Beginning of conversation with {friend.username} —
          </p>
        )}

        {loading && (
          <div className="flex-1 flex items-center justify-center">
            <div className="flex flex-col items-center gap-3">
              <div className="w-8 h-8 border-2 border-neon-cyan/30 border-t-neon-cyan
                              rounded-full animate-spin" />
              <span className="text-cyber-muted/40 text-xs font-display uppercase tracking-widest">
                Loading…
              </span>
            </div>
          </div>
        )}

        {!loading && msgList.length === 0 && (
          <EmptyState friendName={friend.username} />
        )}

        {!loading && items.map((item, idx) =>
          item.type === "separator" ? (
            <DateSeparator key={`sep-${idx}`} label={item.label} />
          ) : (
            <MessageBubble
              key={item.id}
              msg={item}
              isOwn={item.sender_id === currentUserId}
              onEdit={startEdit}
              onDelete={handleDelete}
              editingId={editingId}
              onCancelEdit={cancelEdit}
              onSubmitEdit={submitEdit}
            />
          )
        )}

        <div ref={bottomRef} />
      </div>

      {/* ── Error banner ── */}
      {error && (
        <div className="mx-4 mb-2 px-3 py-2 bg-neon-red/10 border border-neon-red/30 rounded-lg flex items-center justify-between">
          <span className="text-neon-red text-xs font-mono">{error}</span>
          <button
            onClick={() => setError("")}
            className="text-neon-red/60 hover:text-neon-red text-sm ml-3 cursor-pointer"
          >
            ✕
          </button>
        </div>
      )}

      {/* ── Composer ── */}
      <div className="px-4 pb-4 flex-shrink-0">
        <div className="flex items-end gap-3 bg-cyber-surface border border-cyber-border/60
                        rounded-xl px-3 py-2.5
                        focus-within:border-neon-cyan/40
                        focus-within:shadow-[0_0_0_2px_rgba(0,240,255,0.06)]
                        transition-all duration-200">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              e.target.style.height = "auto";
              e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
            }}
            onKeyDown={handleKeyDown}
            placeholder={`Message @${friend.username}`}
            rows={1}
            disabled={sending}
            className="flex-1 bg-transparent text-sm text-cyber-text font-mono
                       resize-none outline-none leading-relaxed
                       placeholder:text-cyber-muted/35
                       disabled:opacity-50 max-h-[120px] overflow-y-auto"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || sending}
            title="Send (Enter)"
            className="w-8 h-8 flex items-center justify-center rounded-lg flex-shrink-0
                       bg-neon-cyan/10 border border-neon-cyan/30 text-neon-cyan
                       hover:bg-neon-cyan/20 hover:border-neon-cyan/60 hover:glow-cyan
                       disabled:opacity-30 disabled:cursor-not-allowed
                       transition-all duration-200 cursor-pointer text-base"
          >
            ➤
          </button>
        </div>
        <p className="text-[10px] text-cyber-muted/30 font-mono mt-1.5 px-1">
          Enter to send · Shift+Enter for new line
        </p>
      </div>
    </div>
  );
}
