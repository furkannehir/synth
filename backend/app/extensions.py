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
    """
    Thread-safe in-memory cache of server member lists.

    One background thread refreshes watched servers every REFRESH_INTERVAL
    seconds.  SSE generator coroutines call `wait_for_update()` which blocks
    until new data arrives (or the timeout expires), so they never busy-spin.

    This means N clients watching the same server share O(1) DB queries per
    refresh cycle instead of O(N) with client-side polling.
    """

    REFRESH_INTERVAL = 5  # seconds between DB refreshes

    def __init__(self):
        self._cache: dict[str, list] = {}          # server_id → members list
        self._watchers: dict[str, int] = {}         # server_id → watcher count
        self._conditions: dict[str, threading.Condition] = {}
        self._lock = threading.Lock()

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
    def update(self, server_id: str, members: list) -> None:
        with self._lock:
            cond = self._conditions.get(server_id)
        self._cache[server_id] = members
        if cond:
            with cond:
                cond.notify_all()  # wake up all waiting SSE generators

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


presence_cache = PresenceCache()

