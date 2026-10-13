import { connectChatStream } from "../api/chatStream";
import { applyDMEvent, mergeDMMessages } from "../api/dmMessages";
import { useState, useEffect, useRef, useCallback } from "react";
import { dms as dmsApi, friends as friendsApi } from "../api/client";
import { useAuth } from "../context/AuthContext";
import MessageBubble, { DateSeparator } from "./ChatMessage";
import ConversationHeader from "./ConversationHeader";
import { groupByDate } from "../utils/chatPresentation";
import { MessageCircle, Send, UserMinus, X } from "lucide-react";


// ── Empty state ────────────────────────────────────────────

function EmptyState({ friendName }) {
  return (
    <div className="flex flex-col items-center justify-center flex-1 gap-4 p-8">
      <div className="w-16 h-16 rounded-2xl bg-cyber-surface border border-cyber-border/40
                      flex items-center justify-center text-neon-pink/30 text-3xl font-display">
        <MessageCircle size={36} />
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
        <MessageCircle size={36} />
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
  const [query, setQuery] = useState("");
  const [sending, setSending] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [error, setError] = useState("");
  const [removingFriend, setRemovingFriend] = useState(false);

  const bottomRef = useRef(null);
  const scrollRef = useRef(null);
  const textareaRef = useRef(null);
  const messageVersionRef = useRef(0);
  const deletedMessageIdsRef = useRef(new Set());

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
  }, [friend?.id]);

  // ── Scroll to bottom on initial load ───────────────────
  useEffect(() => {
    if (!loading) scrollToBottom("instant");
  }, [loading]);

  // ── SSE — live updates ──────────────────────────────────
  useEffect(() => {
    if (!friend) return;

    const disconnect = connectChatStream({
      url: () => dmsApi.eventsUrl(friend.id),
      loadHistory: () => dmsApi.list(friend.id),
      onHistory: (data) => {
        const fetched = data.messages || [];
        messageVersionRef.current += 1;
        setMsgList(fetched);
        setHasMore(fetched.length === 50);
        setLoading(false);
        setError("");
        // Reconnecting may load incoming messages missed while offline.
        dmsApi.markRead(friend.id).catch(() => {});
      },
      onError: (error) => {
        setError(error.message);
        setLoading(false);
      },
      onEvent: (event) => {
        messageVersionRef.current += 1;
        if (event.type === "dm_delete") deletedMessageIdsRef.current.add(event.data.id);
        setMsgList((prev) => applyDMEvent(prev, event, currentUserId));
        if (event.type === "dm") {
          
          if (event.data.sender_id !== currentUserId) {
            dmsApi.markRead(friend.id).catch(() => {});
          }
          
          const el = scrollRef.current;
          if (el) {
            const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
            if (nearBottom) setTimeout(() => scrollToBottom("smooth"), 50);
          }
        }
      },
    });

    return disconnect;
  }, [friend?.id]);

  // ── Load older messages ─────────────────────────────────
  const handleScroll = useCallback(async () => {
    const el = scrollRef.current;
    if (!el || loadingMore || !hasMore || el.scrollTop > 80) return;

    const oldest = msgList[0];
    if (!oldest) return;

    setLoadingMore(true);
    const prevHeight = el.scrollHeight;
    const messageVersion = messageVersionRef.current;

    try {
      const data = await dmsApi.list(friend.id, oldest.id);
      // A newer snapshot or streamed update makes this page's snapshot stale.
      if (messageVersionRef.current !== messageVersion) return;
      const older = data.messages || [];
      setMsgList((prev) => mergeDMMessages(prev, older));
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
      if (deletedMessageIdsRef.current.has(data.message.id)) return;
      messageVersionRef.current += 1;
      setMsgList((prev) => mergeDMMessages(prev, [data.message]));
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
      messageVersionRef.current += 1;
      setMsgList((prev) => applyDMEvent(prev, { type: "dm_edit", data: data.message }, currentUserId));
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
      deletedMessageIdsRef.current.add(messageId);
      messageVersionRef.current += 1;
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

  const items = groupByDate(msgList.filter((message) => !query || message.content.toLocaleLowerCase().includes(query.toLocaleLowerCase())));

  return (
    <div className="conversation-panel">
      <ConversationHeader title={friend.username} friend={friend} query={query} onQueryChange={setQuery}>
        <button className="icon-button" onClick={handleRemoveFriend} disabled={removingFriend} title="Remove friend" aria-label="Remove friend"><UserMinus size={22} /></button>
      </ConversationHeader>

      {/* ── Message list ── */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="message-scroll"
      >
        {loadingMore && (
          <div className="text-center py-2">
            <span className="text-[10px] text-cyber-muted/40 font-display animate-pulse">
              Loading older messages…
            </span>
          </div>
        )}

        {query && hasMore && <button className="search-load-more" disabled={loadingMore} onClick={() => { scrollRef.current.scrollTop = 0; handleScroll(); }}>Search earlier messages</button>}
        {query && !loading && items.length === 0 && <p className="search-empty">No matching messages.</p>}

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
              e.target.style.height = "auto";
              e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
            }}
            onKeyDown={handleKeyDown}
            placeholder={`Message @${friend.username}`}
            rows={1}
            disabled={sending}
            aria-label={`Message @${friend.username}`}
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
