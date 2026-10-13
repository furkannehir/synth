import { connectChatStream } from "../api/chatStream";
import { createChannelState } from "../api/channelMessages";
import { useState, useEffect, useRef, useCallback } from "react";
import { messages as messagesApi } from "../api/client";
import { useAuth } from "../context/AuthContext";
import MessageBubble, { DateSeparator } from "./ChatMessage";
import ConversationHeader from "./ConversationHeader";
import { groupByDate } from "../utils/chatPresentation";
import { Hash, Send, X } from "lucide-react";


// ── Empty state ────────────────────────────────────────────

function EmptyState({ channelName }) {
  return (
    <div className="flex flex-col items-center justify-center flex-1 gap-4 p-8">
      <div className="w-16 h-16 rounded-2xl bg-cyber-surface border border-cyber-border/40
                      flex items-center justify-center text-neon-cyan/30 text-3xl font-display">
        <Hash size={36} />
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

export default function TextPanel({ channel, onToggleMembers, membersOpen, children }) {
  const { user } = useAuth();
  return <TextChannelPanel key={`${user?.id || user?._id}:${channel?.id || "none"}`} channel={channel} user={user} onToggleMembers={onToggleMembers} membersOpen={membersOpen}>{children}</TextChannelPanel>;
}

function TextChannelPanel({ channel, user, onToggleMembers, membersOpen, children }) {
  const channelId = channel?.id;
  const [msgList, setMsgList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [input, setInput] = useState("");
  const [query, setQuery] = useState("");
  const [sending, setSending] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [error, setError] = useState("");

  const bottomRef = useRef(null);
  const scrollRef = useRef(null);
  const textareaRef = useRef(null);
  const scopeRef = useRef(null);
  const loadingMoreRef = useRef(false);
  const sendingRef = useRef(false);

  const currentUserId = user?.id || user?._id;

  // ── Scroll to bottom ────────────────────────────────────
  const scrollToBottom = useCallback((behavior = "smooth") => {
    bottomRef.current?.scrollIntoView({ behavior });
  }, []);

  // ── Scroll to bottom on initial load ───────────────────
  useEffect(() => {
    if (!loading) scrollToBottom("instant");
  }, [loading, scrollToBottom]);

  // ── SSE — live updates ──────────────────────────────────
  useEffect(() => {
    if (!channelId) return;

    const scope = createChannelState(channelId);
    scopeRef.current = scope;

    const disconnect = connectChatStream({
      url: () => messagesApi.eventsUrl(channelId),
      loadHistory: async () => {
        const localVersion = scope.mutationVersion;
        const data = await messagesApi.list(channelId);
        return { ...data, localVersion };
      },
      onHistory: (data) => {
        const fetched = data.messages || [];
        setMsgList(scope.replaceHistory(fetched, data.localVersion));
        setHasMore(fetched.length === 50);
        setLoading(false);
        setError("");
      },
      onError: (error) => {
        setError(error.message);
        setLoading(false);
      },
      onEvent: (event) => {
        setMsgList(scope.applyEvent(event));
        if (event.type === "message") {
          // Auto-scroll only if the user is near the bottom
          const el = scrollRef.current;
          if (el) {
            const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
            if (nearBottom) setTimeout(() => { if (scope.active) scrollToBottom("smooth"); }, 50);
          }
        }
      },
    });

    return () => {
      scope.close();
      disconnect();
    };
  }, [channelId, scrollToBottom]);

  // ── Load older messages (infinite scroll up) ────────────
  const handleScroll = useCallback(async () => {
    const el = scrollRef.current;
    const scope = scopeRef.current;
    if (!scope?.active || !el || loading || loadingMoreRef.current || !hasMore || el.scrollTop > 80) return;

    const oldest = msgList[0];
    if (!oldest) return;

    loadingMoreRef.current = true;
    setLoadingMore(true);
    const prevHeight = el.scrollHeight;
    const historyVersion = scope.historyVersion;

    try {
      const data = await messagesApi.list(channelId, oldest.id);
      const older = data.messages || [];
      const merged = scope.prependPage(older, historyVersion);
      if (merged === null) return;
      setMsgList(merged);
      setHasMore(older.length === 50);
      setError("");
      // Maintain scroll position after prepending
      requestAnimationFrame(() => {
        if (scope.active && scope.historyVersion === historyVersion) el.scrollTop += el.scrollHeight - prevHeight;
      });
    } catch (error) {
      if (scope.active && scope.historyVersion === historyVersion) setError(error.message);
    } finally {
      if (scope.active) {
        loadingMoreRef.current = false;
        setLoadingMore(false);
      }
    }
  }, [channelId, msgList, loading, hasMore]);

  // ── Send message ────────────────────────────────────────
  const handleSend = useCallback(async () => {
    const content = input.trim();
    const scope = scopeRef.current;
    if (!content || !scope?.active || sendingRef.current) return;

    sendingRef.current = true;
    setSending(true);
    setInput("");
    setError("");

    try {
      const data = await messagesApi.send(channelId, content);
      if (!scope.active) return;
      setMsgList(scope.merge([data.message]));
      setTimeout(() => { if (scope.active) scrollToBottom("smooth"); }, 50);
    } catch (e) {
      if (scope.active) {
        setError(e.message);
        setInput((current) => current || content);
      }
    } finally {
      if (scope.active) {
        sendingRef.current = false;
        setSending(false);
        textareaRef.current?.focus();
      }
    }
  }, [input, channelId, scrollToBottom]);

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
    const scope = scopeRef.current;
    if (!trimmed || !scope?.active) return;
    try {
      const data = await messagesApi.edit(channelId, messageId, trimmed);
      if (scope.active) setMsgList(scope.applyEvent({ type: "message_edit", data: data.message }));
    } catch (e) {
      if (scope.active) setError(e.message);
    } finally {
      if (scope.active) setEditingId((current) => current === messageId ? null : current);
    }
  }, [channelId]);

  // ── Delete ──────────────────────────────────────────────
  const handleDelete = useCallback(async (messageId) => {
    const scope = scopeRef.current;
    if (!scope?.active) return;
    try {
      await messagesApi.delete(channelId, messageId);
      if (scope.active) setMsgList(scope.applyEvent({ type: "message_delete", data: { id: messageId } }));
    } catch (e) {
      if (scope.active) setError(e.message);
    }
  }, [channelId]);

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

  const items = groupByDate(msgList.filter((message) => !query || message.content.toLocaleLowerCase().includes(query.toLocaleLowerCase())));

  return (
    <div className="conversation-panel">
      {/* ── Header ── */}
      <ConversationHeader title={channel.name} query={query} onQueryChange={setQuery} onToggleMembers={onToggleMembers} membersOpen={membersOpen} />
      {children}

      {/* ── Message list ── */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="message-scroll"
      >
        {/* Load more indicator */}
        {loadingMore && (
          <div className="text-center py-2">
            <span className="text-[10px] text-cyber-muted/40 font-display animate-pulse">
              Loading older messages…
            </span>
          </div>
        )}

        {query && hasMore && <button className="search-load-more" disabled={loadingMore} onClick={() => { scrollRef.current.scrollTop = 0; handleScroll(); }}>Search earlier messages</button>}
        {query && !loading && items.length === 0 && <p className="search-empty">No matching messages.</p>}

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
            <X size={18} />
          </button>
        </div>
      )}

      {/* ── Composer ── */}
      <div className="conversation-composer">
        <div className="composer-field">
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
            aria-label={`Message #${channel.name}`}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || sending}
            title="Send (Enter)"
            className="send-button"
            aria-label="Send message"
          >
            <Send size={23} />
          </button>
        </div>
        <p className="composer-hint">
          Enter to send · Shift+Enter for new line
        </p>
      </div>
    </div>
  );
}
