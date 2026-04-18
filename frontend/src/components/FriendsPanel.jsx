import { useState, useEffect, useCallback, useRef } from "react";
import { friends as friendsApi, dms as dmsApi } from "../api/client";

const TABS = ["messages", "all", "pending", "add"];

function TabBar({ active, onChange, pendingCount }) {
  const labels = {
    messages: "Messages",
    all: "All",
    pending: `Pending${pendingCount > 0 ? ` (${pendingCount})` : ""}`,
    add: "+ Add",
  };
  return (
    <div className="flex border-b border-cyber-border/40">
      {TABS.map((tab) => (
        <button
          key={tab}
          onClick={() => onChange(tab)}
          className={`flex-1 py-2.5 text-[11px] font-display font-bold uppercase tracking-[0.16em]
                      transition-all duration-200 cursor-pointer
                      ${
                        active === tab
                          ? "text-neon-cyan border-b-2 border-neon-cyan text-glow-cyan"
                          : "text-cyber-muted hover:text-cyber-text hover:bg-cyber-hover/30"
                      }`}
        >
          {labels[tab]}
        </button>
      ))}
    </div>
  );
}

function FriendRow({ friend, onClick }) {
  return (
    <button
      onClick={() => onClick(friend)}
      className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-cyber-hover/40
                 transition-all duration-200 group cursor-pointer"
    >
      {/* Avatar */}
      <div className="relative flex-shrink-0">
        <div
          className="w-9 h-9 rounded-full flex items-center justify-center
                      bg-gradient-to-br from-neon-cyan/20 to-neon-purple/20
                      border border-neon-cyan/20 text-neon-cyan font-display font-bold text-xs"
        >
          {friend.avatar ? (
            <img
              src={friend.avatar}
              alt={friend.username}
              className="w-9 h-9 rounded-full object-cover"
            />
          ) : (
            (friend.username || "?").slice(0, 2).toUpperCase()
          )}
        </div>
        {/* Online indicator */}
        <span
          className={`absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full border-2 border-cyber-surface
                      ${friend.is_online ? "bg-neon-green online-pulse" : "bg-cyber-muted/40"}`}
        />
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0 text-left">
        <p className="text-sm font-display font-semibold text-cyber-text truncate group-hover:text-neon-cyan transition-colors">
          {friend.username}
        </p>
        <p className="text-[10px] text-cyber-muted/60 font-mono">
          {friend.is_online ? "Online" : "Offline"}
        </p>
      </div>

      {/* DM icon */}
      <span
        className="text-cyber-muted/30 group-hover:text-neon-cyan/60 transition-colors text-sm"
        title="Open DM"
      >
        💬
      </span>
    </button>
  );
}

function ConversationRow({ conversation, onClick }) {
  const friend = conversation.friend;
  const msg = conversation.last_message;
  return (
    <button
      onClick={() => onClick(friend)}
      className="w-full flex items-center gap-3 px-4 py-3 hover:bg-cyber-hover/40
                 transition-all duration-200 group cursor-pointer relative"
    >
      <div className="relative flex-shrink-0">
        <div
          className="w-10 h-10 rounded-full flex items-center justify-center
                      bg-gradient-to-br from-neon-cyan/20 to-neon-purple/20
                      border border-neon-cyan/20 text-neon-cyan font-display font-bold text-sm"
        >
          {friend.avatar ? (
            <img
              src={friend.avatar}
              alt={friend.username}
              className="w-10 h-10 rounded-full object-cover"
            />
          ) : (
            (friend.username || "?").slice(0, 2).toUpperCase()
          )}
        </div>
        <span
          className={`absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full border-2 border-cyber-surface
                      ${friend.is_online ? "bg-neon-green online-pulse" : "bg-cyber-muted/40"}`}
        />
      </div>

      <div className="flex-1 min-w-0 text-left">
        <div className="flex justify-between items-baseline mb-0.5">
          <p className="text-sm font-display font-semibold text-cyber-text truncate group-hover:text-neon-cyan transition-colors">
            {friend.username}
          </p>
        </div>
        <p className={`text-xs truncate font-mono ${conversation.unread_count > 0 ? "text-neon-cyan" : "text-cyber-muted/70"}`}>
          {msg.sender_id === friend.id ? "" : "You: "}{msg.content}
        </p>
      </div>

      {conversation.unread_count > 0 && (
        <span className="flex-shrink-0 bg-neon-pink text-cyber-bg text-[10px] font-bold px-1.5 py-0.5 rounded-full ml-2">
          {conversation.unread_count > 99 ? "99+" : conversation.unread_count}
        </span>
      )}
    </button>
  );
}

function PendingRequestRow({ req, type, onAccept, onReject, onCancel }) {
  const [loading, setLoading] = useState(false);

  const handleAction = async (action) => {
    setLoading(true);
    try {
      await action(req.id);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center gap-3 px-4 py-2.5">
      {/* Avatar */}
      <div
        className="w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0
                    bg-gradient-to-br from-neon-pink/20 to-neon-purple/20
                    border border-neon-pink/20 text-neon-pink font-display font-bold text-xs"
      >
        {req.user?.avatar ? (
          <img
            src={req.user.avatar}
            alt={req.user?.username}
            className="w-9 h-9 rounded-full object-cover"
          />
        ) : (
          (req.user?.username || "?").slice(0, 2).toUpperCase()
        )}
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-display font-semibold text-cyber-text truncate">
          {req.user?.username || "Unknown"}
        </p>
        <p className="text-[10px] text-cyber-muted/60 font-mono">
          {type === "incoming" ? "Incoming request" : "Outgoing request"}
        </p>
      </div>

      {/* Actions */}
      <div className="flex gap-1.5">
        {type === "incoming" ? (
          <>
            <button
              onClick={() => handleAction(onAccept)}
              disabled={loading}
              className="px-2.5 py-1 text-[10px] font-display font-bold uppercase tracking-wider
                         bg-neon-green/10 border border-neon-green/30 text-neon-green rounded-md
                         hover:bg-neon-green/20 hover:border-neon-green/60
                         disabled:opacity-40 disabled:cursor-not-allowed transition cursor-pointer"
            >
              Accept
            </button>
            <button
              onClick={() => handleAction(onReject)}
              disabled={loading}
              className="px-2.5 py-1 text-[10px] font-display font-bold uppercase tracking-wider
                         bg-neon-red/10 border border-neon-red/30 text-neon-red rounded-md
                         hover:bg-neon-red/20 hover:border-neon-red/60
                         disabled:opacity-40 disabled:cursor-not-allowed transition cursor-pointer"
            >
              Reject
            </button>
          </>
        ) : (
          <button
            onClick={() => handleAction(onCancel)}
            disabled={loading}
            className="px-2.5 py-1 text-[10px] font-display font-bold uppercase tracking-wider
                       text-cyber-muted border border-cyber-border rounded-md
                       hover:text-neon-red hover:border-neon-red/40 hover:bg-neon-red/10
                       disabled:opacity-40 disabled:cursor-not-allowed transition cursor-pointer"
          >
            Cancel
          </button>
        )}
      </div>
    </div>
  );
}

function AddFriendTab() {
  const [username, setUsername] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null); // { type: "success"|"error", message }

  const handleSubmit = async (e) => {
    e.preventDefault();
    const trimmed = username.trim();
    if (!trimmed) return;

    setLoading(true);
    setResult(null);
    try {
      const data = await friendsApi.sendRequest(trimmed);
      if (data.auto_accepted) {
        setResult({ type: "success", message: `You are now friends with ${trimmed}!` });
      } else {
        setResult({ type: "success", message: `Friend request sent to ${trimmed}.` });
      }
      setUsername("");
    } catch (error) {
      setResult({ type: "error", message: error.message });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-4">
      <p className="text-xs text-cyber-muted mb-3 font-mono">
        Add a friend by their username.
      </p>
      <form onSubmit={handleSubmit} className="flex flex-col gap-2">
        <input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="Enter a username"
          autoFocus
          className="w-full rounded-lg border border-cyber-border/50 bg-cyber-panel/60 px-3 py-2
                     text-sm text-cyber-text font-mono outline-none transition
                     focus:border-neon-cyan/60 placeholder:text-cyber-muted/35"
        />
        <button
          type="submit"
          disabled={loading || !username.trim()}
          className="w-full rounded-lg border border-neon-cyan/40 bg-neon-cyan/10 px-4 py-2
                     text-[11px] font-display font-bold uppercase tracking-[0.16em] text-neon-cyan
                     hover:bg-neon-cyan/20 hover:border-neon-cyan/60 hover:glow-cyan
                     disabled:opacity-40 disabled:cursor-not-allowed transition cursor-pointer"
        >
          {loading ? "Sending..." : "Send Request"}
        </button>
      </form>

      {result && (
        <div
          className={`mt-3 px-3 py-2 rounded-lg border text-xs font-mono ${
            result.type === "success"
              ? "bg-neon-green/10 border-neon-green/30 text-neon-green"
              : "bg-neon-red/10 border-neon-red/30 text-neon-red"
          }`}
        >
          {result.message}
        </div>
      )}
    </div>
  );
}

export default function FriendsPanel({ onSelectFriend, activeFriend }) {
  const [activeTab, setActiveTab] = useState("messages");
  const [friendList, setFriendList] = useState([]);
  const [pending, setPending] = useState({ incoming: [], outgoing: [] });
  const [loading, setLoading] = useState(true);

  const [conversations, setConversations] = useState([]);
  const [convOffset, setConvOffset] = useState(0);
  const [hasMoreConv, setHasMoreConv] = useState(true);
  const [loadingConv, setLoadingConv] = useState(false);

  const pendingCount = pending.incoming.length;

  const fetchFriends = useCallback(async () => {
    try {
      const data = await friendsApi.list();
      setFriendList(data.friends || []);
    } catch {
      // silently fail
    }
  }, []);

  const fetchPending = useCallback(async () => {
    try {
      const data = await friendsApi.pending();
      setPending({
        incoming: data.incoming || [],
        outgoing: data.outgoing || [],
      });
    } catch {
      // silently fail
    }
  }, []);

  const fetchConversations = useCallback(async (isLoadMore = false) => {
    try {
      const offset = isLoadMore ? convOffset : 0;
      setLoadingConv(true);
      const data = await dmsApi.conversations(offset, 20);
      if (isLoadMore) {
        setConversations(prev => [...prev, ...(data.conversations || [])]);
      } else {
        setConversations(data.conversations || []);
      }
      setConvOffset(offset + (data.conversations?.length || 0));
      setHasMoreConv((data.conversations?.length || 0) === 20);
    } catch {
      // silently fail
    } finally {
      setLoadingConv(false);
    }
  }, [convOffset]);

  // Initial load
  useEffect(() => {
    const load = async () => {
      setLoading(true);
      await Promise.all([fetchFriends(), fetchPending(), fetchConversations()]);
      setLoading(false);
    };
    load();
  }, []);

  // Poll friends every 15s for online status and fetch top 20 conversations
  useEffect(() => {
    const interval = setInterval(() => {
      fetchFriends();
      fetchPending();
      fetchConversations(false);
    }, 15000);
    return () => clearInterval(interval);
  }, [fetchFriends, fetchPending, fetchConversations]);

  const handleAccept = async (requestId) => {
    await friendsApi.accept(requestId);
    fetchPending();
    fetchFriends();
  };

  const handleReject = async (requestId) => {
    await friendsApi.reject(requestId);
    fetchPending();
  };

  const handleCancel = async (requestId) => {
    await friendsApi.cancel(requestId);
    fetchPending();
  };

  const onlineFriends = friendList.filter((f) => f.is_online);
  const displayFriends = activeTab === "online" ? onlineFriends : friendList;

  return (
    <div className="w-60 bg-cyber-panel/80 border-r border-cyber-border/40 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="px-4 h-14 flex items-center border-b border-cyber-border/40 flex-shrink-0">
        <h2 className="font-display font-bold text-sm text-cyber-text uppercase tracking-wider">
          Friends
        </h2>
      </div>

      {/* Tabs */}
      <TabBar active={activeTab} onChange={setActiveTab} pendingCount={pendingCount} />

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {activeTab === "add" && <AddFriendTab />}

        {activeTab === "pending" && (
          <div className="py-1">
            {pending.incoming.length === 0 && pending.outgoing.length === 0 && (
              <p className="text-xs text-cyber-muted/40 text-center py-8 font-mono">
                No pending requests
              </p>
            )}
            {pending.incoming.length > 0 && (
              <div>
                <p className="px-4 pt-3 pb-1 text-[10px] text-cyber-muted/50 font-display uppercase tracking-[0.2em]">
                  Incoming — {pending.incoming.length}
                </p>
                {pending.incoming.map((req) => (
                  <PendingRequestRow
                    key={req.id}
                    req={req}
                    type="incoming"
                    onAccept={handleAccept}
                    onReject={handleReject}
                    onCancel={handleCancel}
                  />
                ))}
              </div>
            )}
            {pending.outgoing.length > 0 && (
              <div>
                <p className="px-4 pt-3 pb-1 text-[10px] text-cyber-muted/50 font-display uppercase tracking-[0.2em]">
                  Outgoing — {pending.outgoing.length}
                </p>
                {pending.outgoing.map((req) => (
                  <PendingRequestRow
                    key={req.id}
                    req={req}
                    type="outgoing"
                    onAccept={handleAccept}
                    onReject={handleReject}
                    onCancel={handleCancel}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === "all" && (
          <div className="py-1">
            {loading && (
              <div className="flex items-center justify-center py-8">
                <div className="w-6 h-6 border-2 border-neon-cyan/30 border-t-neon-cyan rounded-full animate-spin" />
              </div>
            )}

            {!loading && friendList.length === 0 && (
              <div className="text-center py-8 px-4">
                <p className="text-cyber-muted/40 text-xs font-mono">
                  No friends yet — add some!
                </p>
              </div>
            )}

            {!loading && friendList.length > 0 && (
              <>
                <p className="px-4 pt-3 pb-1 text-[10px] text-cyber-muted/50 font-display uppercase tracking-[0.2em]">
                  All Friends — {friendList.length}
                </p>
                {[...friendList]
                  .sort((a, b) => (a.is_online === b.is_online ? 0 : a.is_online ? -1 : 1))
                  .map((friend) => (
                  <FriendRow
                    key={friend.id}
                    friend={friend}
                    onClick={onSelectFriend}
                  />
                ))}
              </>
            )}
          </div>
        )}

        {activeTab === "messages" && (
          <div className="py-1">
            {loading && (
              <div className="flex items-center justify-center py-8">
                <div className="w-6 h-6 border-2 border-neon-cyan/30 border-t-neon-cyan rounded-full animate-spin" />
              </div>
            )}

            {!loading && conversations.length === 0 && (
              <div className="text-center py-8 px-4">
                <p className="text-cyber-muted/40 text-xs font-mono">
                  No direct messages yet.
                </p>
              </div>
            )}

            {!loading && conversations.length > 0 && (
              <>
                <p className="px-4 pt-3 pb-1 text-[10px] text-cyber-muted/50 font-display uppercase tracking-[0.2em]">
                  Direct Messages
                </p>
                {conversations.map((conv) => (
                  <ConversationRow
                    key={conv.friend.id}
                    conversation={conv}
                    onClick={onSelectFriend}
                  />
                ))}
                
                {hasMoreConv && (
                  <div className="px-4 py-3">
                    <button
                      onClick={() => fetchConversations(true)}
                      disabled={loadingConv}
                      className="w-full py-1.5 text-[10px] font-display font-bold uppercase tracking-widest text-cyber-muted border border-cyber-border/60 hover:text-neon-cyan hover:border-neon-cyan/40 rounded transition"
                    >
                      {loadingConv ? "Loading..." : "Load More"}
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
