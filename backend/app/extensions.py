from flask_pymongo import PyMongo
from flask_jwt_extended import JWTManager
import threading

# MongoDB instance — initialised in create_app()
mongo = PyMongo()

# JWT manager — initialised in create_app()
jwt = JWTManager()

# Media-server port — assigned during create_app()
# Will hold a concrete MediaServerPort implementation (e.g. LiveKitAdapter).
media_server = None


class PresenceCache:
    REFRESH_INTERVAL = 3  # seconds between DB refreshes

    def __init__(self):
        self._cache: dict[str, list] = {}          # server_id → members list
        self._watchers: dict[str, int] = {}         # server_id → watcher count
        self._conditions: dict[str, threading.Condition] = {}
        self._lock = threading.Lock()
        # Event that endpoints can set to request an immediate refresh cycle
        self._dirty = threading.Event()
        # Tombstones: identity -> expiry timestamp.
        # Prevents re-adding a leaving participant if LiveKit is slow to purge them.
        self._tombstones: dict[str, float] = {}

    # ── Watcher registration ─────────────────────────────────
    def register(self, server_id: str) -> None:
        with self._lock:
            self._watchers[server_id] = self._watchers.get(server_id, 0) + 1
            if server_id not in self._conditions:
                self._conditions[server_id] = threading.Condition()

    def unregister(self, server_id: str) -> None:
        with self._lock:
            count = self._watchers.get(server_id, 1) - 1
            if count <= 0:
                self._watchers.pop(server_id, None)
            else:
                self._watchers[server_id] = count

    def watched_server_ids(self) -> list[str]:
        with self._lock:
            return list(self._watchers.keys())

    # ── Cache update (called by background thread) ───────────
    def update(self, server_id: str, payload: dict) -> None:
        import time
        now = time.time()
        with self._lock:
            # Clear expired tombstones
            self._tombstones = {uid: exp for uid, exp in self._tombstones.items() if exp > now}
            
            # Filter participants
            voice_channels = payload.get("voice_channels", {})
            for ch_id, participants in voice_channels.items():
                voice_channels[ch_id] = [p for p in participants if p.get("identity") not in self._tombstones]
                
            self._cache[server_id] = payload
            cond = self._conditions.get(server_id)
            if cond:
                with cond:
                    cond.notify_all()

    def get(self, server_id: str):
        return self._cache.get(server_id)

    # ── SSE generator helper ─────────────────────────────────
    def wait_for_update(self, server_id: str, timeout: float = REFRESH_INTERVAL + 1):
        """Block until new data is available for server_id or timeout expires."""
        with self._lock:
            cond = self._conditions.get(server_id)
        if cond:
            with cond:
                cond.wait(timeout=timeout)

    # ── Immediate refresh trigger ─────────────────────────────
    def mark_dirty(self) -> None:
        """Signal the background thread to refresh immediately."""
        self._dirty.set()

    def wait_for_dirty(self, timeout: float = REFRESH_INTERVAL) -> bool:
        """Block until mark_dirty() is called or timeout expires. Returns True if dirty."""
        was_set = self._dirty.wait(timeout=timeout)
        self._dirty.clear()
        return was_set

    # ── Optimistic cache patching ─────────────────────────────
    def remove_voice_participant(self, server_id: str, channel_id: str, identity: str) -> None:
        """
        Immediately remove a participant from the cached voice_channels
        for a server, then wake SSE generators.  This avoids the race
        where LiveKit hasn't fully processed the removal yet when the
        background thread re-queries.
        """
        import time
        with self._lock:
            # Tombstone for 5s to prevent immediate re-add by the background polling thread
            self._tombstones[identity] = time.time() + 5.0
            
            cached = self._cache.get(server_id)
            if not isinstance(cached, dict):
                return
            vc = cached.get("voice_channels", {})
            participants = vc.get(channel_id)
            if participants is None:
                return
            vc[channel_id] = [p for p in participants if p.get("identity") != identity]
            
            # Wake SSE generators with the patched data
            cond = self._conditions.get(server_id)
            if cond:
                with cond:
                    cond.notify_all()


presence_cache = PresenceCache()


class ChannelEventBus:
    """
    Thread-safe pub/sub bus for text-channel SSE streams.

    When a message is sent (POST), the route calls `publish(channel_id, event)`.
    Each SSE generator for that channel is blocked on `wait_for_event()`.
    On publish, all waiters are woken with the new event payload.

    This means N SSE clients watching the same channel share zero polling —
    messages are pushed immediately as they arrive.
    """

    def __init__(self):
        self._conditions: dict[str, threading.Condition] = {}
        self._queues: dict[str, list] = {}          # channel_id → [pending events]
        self._lock = threading.Lock()

    # ── Subscription ─────────────────────────────────────────
    def subscribe(self, channel_id: str) -> None:
        with self._lock:
            if channel_id not in self._conditions:
                self._conditions[channel_id] = threading.Condition()
                self._queues[channel_id] = []

    def unsubscribe(self, channel_id: str) -> None:
        # Conditions are lightweight; we leave them alive to avoid races.
        pass

    # ── Publishing (called from HTTP request thread) ──────────
    def publish(self, channel_id: str, event: dict) -> None:
        with self._lock:
            cond = self._conditions.get(channel_id)
            if cond is None:
                return  # no active listeners — nothing to do
            self._queues[channel_id].append(event)

        with cond:
            cond.notify_all()

    # ── SSE generator helper ─────────────────────────────────
    def wait_for_event(self, channel_id: str, timeout: float = 30.0) -> list:
        """
        Block until at least one event is available for channel_id
        (or timeout expires).  Returns and drains the pending event list.
        """
        with self._lock:
            cond = self._conditions.get(channel_id)
        if cond is None:
            return []

        with cond:
            cond.wait(timeout=timeout)

        with self._lock:
            events = self._queues.get(channel_id, [])
            self._queues[channel_id] = []
            return events


channel_event_bus = ChannelEventBus()

