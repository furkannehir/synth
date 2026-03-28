import { useState, useEffect, useRef, useCallback } from "react";
import { messages as messagesApi } from "../api/client";
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

// ── Avatar component ──────────────────────────────────────

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
      {/* Avatar */}
      <div className="mt-0.5">
        <Avatar username={msg.author_username} avatar={msg.author_avatar} />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        {/* Header row */}
        <div className="flex items-baseline gap-2 mb-0.5">
          <span
            className={`text-xs font-display font-bold tracking-wide
                        ${isOwn ? "text-neon-cyan" : "text-neon-pink"}`}
          >
            {msg.author_username || "Unknown"}
          </span>
          <span className="text-[10px] text-cyber-muted/50 font-mono tabular-nums">
            {formatTime(msg.created_at)}
          </span>
          {msg.edited_at && (
            <span className="text-[9px] text-cyber-muted/35 font-mono italic">(edited)</span>
          )}
        </div>

        {/* Body */}
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

      {/* Action buttons — appear on hover */}
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
          {(isOwn) && (
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

function EmptyState({ channelName }) {
  return (
    <div className="flex flex-col items-center justify-center flex-1 gap-4 p-8">
      <div className="w-16 h-16 rounded-2xl bg-cyber-surface border border-cyber-border/40
                      flex items-center justify-center text-neon-cyan/30 text-3xl font-display">
        #
      </div>
      <div className="text-center">
        <p className="text-neon-cyan font-display font-bold text-lg uppercase tracking-wider">
          Welcome to #{channelName}
        </p>
        <p className="text-cyber-muted/50 text-xs mt-1 font-mono">
          This is the start of this channel. Say something!
        </p>
      </div>
    </div>
  );
}

// ── Main TextPanel component ───────────────────────────────

export default function TextPanel({ channel }) {
  const { user } = useAuth();
  const [msgList, setMsgList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [error, setError] = useState("");

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
    if (!channel) return;
    setMsgList([]);
    setLoading(true);
    setHasMore(true);
    setError("");
    setEditingId(null);
    setInput("");

    messagesApi
      .list(channel.id)
      .then((data) => {
        const fetched = data.messages || [];
        setMsgList(fetched);
        setHasMore(fetched.length === 50);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [channel?.id]);

  // ── Scroll to bottom on initial load ───────────────────
  useEffect(() => {
    if (!loading) scrollToBottom("instant");
  }, [loading]);

  // ── SSE — live updates ──────────────────────────────────
  useEffect(() => {
    if (!channel) return;

    // Clean up previous connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    const es = new EventSource(messagesApi.eventsUrl(channel.id));
    eventSourceRef.current = es;

    es.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data);
        if (event.type === "message") {
          setMsgList((prev) => {
            // Deduplicate (in case we get an echo from our own send)
            if (prev.some((m) => m.id === event.data.id)) return prev;
            return [...prev, event.data];
          });
          // Auto-scroll only if the user is near the bottom
          const el = scrollRef.current;
          if (el) {
            const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
            if (nearBottom) setTimeout(() => scrollToBottom("smooth"), 50);
          }
        } else if (event.type === "message_edit") {
          setMsgList((prev) =>
            prev.map((m) => (m.id === event.data.id ? { ...m, ...event.data } : m))
          );
        } else if (event.type === "message_delete") {
          setMsgList((prev) => prev.filter((m) => m.id !== event.data.id));
        }
      } catch {
        // malformed SSE data — silently ignore
      }
    };

    es.onerror = () => {
      // EventSource auto-reconnects; no action needed
    };

    return () => {
      es.close();
      eventSourceRef.current = null;
    };
  }, [channel?.id]);

  // ── Load older messages (infinite scroll up) ────────────
  const handleScroll = useCallback(async () => {
    const el = scrollRef.current;
    if (!el || loadingMore || !hasMore || el.scrollTop > 80) return;

    const oldest = msgList[0];
    if (!oldest) return;

    setLoadingMore(true);
    const prevHeight = el.scrollHeight;

    try {
      const data = await messagesApi.list(channel.id, oldest.id);
      const older = data.messages || [];
      setMsgList((prev) => [...older, ...prev]);
      setHasMore(older.length === 50);
      // Maintain scroll position after prepending
      requestAnimationFrame(() => {
        el.scrollTop = el.scrollHeight - prevHeight;
      });
    } catch {
      // silently fail
    } finally {
      setLoadingMore(false);
    }
  }, [channel?.id, msgList, loadingMore, hasMore]);

  // ── Send message ────────────────────────────────────────
  const handleSend = useCallback(async () => {
    const content = input.trim();
    if (!content || sending) return;

    setSending(true);
    setInput("");
    setError("");

    try {
      const data = await messagesApi.send(channel.id, content);
      // SSE will deliver the message; but add it optimistically too for instant feedback
      setMsgList((prev) => {
        if (prev.some((m) => m.id === data.message.id)) return prev;
        return [...prev, data.message];
      });
      setTimeout(() => scrollToBottom("smooth"), 50);
    } catch (e) {
      setError(e.message);
      setInput(content); // restore
    } finally {
      setSending(false);
      textareaRef.current?.focus();
    }
  }, [input, sending, channel?.id]);

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // ── Edit ────────────────────────────────────────────────
  const startEdit = (msg) => {
    setEditingId(msg.id);
  };

  const cancelEdit = () => setEditingId(null);

  const submitEdit = useCallback(async (messageId, content) => {
    const trimmed = content.trim();
    if (!trimmed) return;
    try {
      const data = await messagesApi.edit(channel.id, messageId, trimmed);
      setMsgList((prev) =>
        prev.map((m) => (m.id === messageId ? { ...m, ...data.message } : m))
      );
    } catch (e) {
      setError(e.message);
    } finally {
      setEditingId(null);
    }
  }, [channel?.id]);

  // ── Delete ──────────────────────────────────────────────
  const handleDelete = useCallback(async (messageId) => {
    try {
      await messagesApi.delete(channel.id, messageId);
      setMsgList((prev) => prev.filter((m) => m.id !== messageId));
    } catch (e) {
      setError(e.message);
    }
  }, [channel?.id]);

  // ── No channel ──────────────────────────────────────────
  if (!channel || channel.type !== "text") {
    return (
      <div className="flex-1 flex flex-col items-center justify-center bg-cyber-bg noise-texture gap-4">
        <div className="w-16 h-16 rounded-2xl bg-cyber-surface border border-cyber-border/30
                        flex items-center justify-center text-cyber-muted/30 text-3xl font-display">
          #
        </div>
        <div className="text-center">
          <p className="text-cyber-muted/50 text-sm font-display uppercase tracking-widest">
            No channel selected
          </p>
          <p className="text-cyber-muted/30 text-xs mt-1">Pick a text channel to start chatting</p>
        </div>
      </div>
    );
  }

  const items = groupByDate(msgList);

  return (
    <div className="flex-1 flex flex-col bg-cyber-bg noise-texture overflow-hidden">
      {/* ── Header ── */}
      <div className="px-5 h-14 flex items-center border-b border-cyber-border/40
                      bg-cyber-surface/40 gap-3 flex-shrink-0">
        <span className="text-neon-cyan/60 font-display font-bold text-lg">#</span>
        <h3 className="font-display font-bold text-sm text-cyber-text uppercase tracking-wider">
          {channel.name}
        </h3>
        <div className="ml-auto flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-neon-green animate-pulse" />
          <span className="text-[10px] text-neon-green/70 font-display uppercase tracking-widest">
            Live
          </span>
        </div>
      </div>

      {/* ── Message list ── */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto py-2 flex flex-col"
      >
        {/* Load more indicator */}
        {loadingMore && (
          <div className="text-center py-2">
            <span className="text-[10px] text-cyber-muted/40 font-display animate-pulse">
              Loading older messages…
            </span>
          </div>
        )}

        {/* Top reached */}
        {!hasMore && msgList.length > 0 && (
          <p className="text-center text-[10px] text-cyber-muted/30 font-mono py-4">
            — Beginning of #{channel.name} —
          </p>
        )}

        {/* Loading skeleton */}
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

        {/* Empty state */}
        {!loading && msgList.length === 0 && (
          <EmptyState channelName={channel.name} />
        )}

        {/* Messages */}
        {!loading && items.map((item, idx) =>
          item.type === "separator" ? (
            <DateSeparator key={`sep-${idx}`} label={item.label} />
          ) : (
            <MessageBubble
              key={item.id}
              msg={item}
              isOwn={item.author_id === currentUserId}
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
              // Auto-grow (max 5 rows)
              e.target.style.height = "auto";
              e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
            }}
            onKeyDown={handleKeyDown}
            placeholder={`Message #${channel.name}`}
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
