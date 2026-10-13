"""MongoDB-backed fan-out shared by every application worker."""
import json
import queue
import threading
from dataclasses import dataclass
from datetime import datetime, timezone

from bson import BSON
from pymongo.errors import DuplicateKeyError


@dataclass(frozen=True)
class Delivery:
    revision: int
    event: dict

    def sse(self, event: dict | None = None) -> str:
        payload = self.event if event is None else event
        return f"id: {self.revision}\ndata: {json.dumps(payload)}\n\n"


class Subscription:
    def __init__(self, revision: int, capacity: int):
        self.revision = revision
        self.initial_revision = revision
        self.queue = queue.Queue(maxsize=capacity)

    def get(self, timeout: float):
        return self.queue.get(timeout=timeout)


class MongoEventBus:
    # A single atomic document update appends an event and advances its revision.
    # Separate sequence allocation/insertion would lose late, out-of-order writes.
    HISTORY_SIZE = 128
    MAX_EVENT_BYTES = 32 * 1024  # keep each bounded history below Mongo's BSON limit
    POLL_INTERVAL = 0.5

    def __init__(self, namespace: str):
        self.namespace = namespace
        self._listeners: dict[str, list[Subscription]] = {}
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = None

    @staticmethod
    def _collection():
        # Resolve after extensions/app initialization, including inside a worker.
        from app.extensions import mongo
        return mongo.db["realtime_streams"]

    def _key(self, topic: str) -> str:
        return f"{self.namespace}:{topic}"

    @staticmethod
    def _resume_revision(value: str | None) -> int | None:
        if value is None or len(value) > 19 or not value.isascii() or not value.isdecimal():
            return None
        return int(value)

    def subscribe(self, topic: str, last_event_id: str | None = None) -> Subscription:
        # Hold the local lock across the snapshot and registration. Remote writes
        # after this snapshot are picked up by the next poll; none fall in a gap.
        with self._lock:
            snapshot = self._collection().find_one({"_id": self._key(topic)}) or {
                "revision": 0, "events": [],
            }
            resume = self._resume_revision(last_event_id)
            revision = snapshot["revision"] if resume is None else resume
            subscription = Subscription(revision, self.HISTORY_SIZE * 2)
            subscription.connected_revision = snapshot["revision"]
            self._listeners.setdefault(topic, []).append(subscription)
            self._deliver(subscription, snapshot)
        self._wake.set()
        return subscription

    def unsubscribe(self, topic: str, subscription: Subscription):
        with self._lock:
            listeners = self._listeners.get(topic, [])
            if subscription in listeners:
                listeners.remove(subscription)
            if not listeners:
                self._listeners.pop(topic, None)

    def publish(self, topic: str, event: dict):
        if event.get("type") in {"message", "message_edit", "dm", "dm_edit"} and "id" in event.get("data", {}):
            # Store notifications, never copies of private or deleted text.
            # Authorized stream handlers resolve the current message at delivery.
            event = {"type": event["type"], "data": {"id": event["data"]["id"]}}
        if len(BSON.encode(event)) > self.MAX_EVENT_BYTES:
            # Oversized profile fields must not overflow the shared history.
            # The client can still retrieve the committed message over HTTP.
            event = {"type": "resync", "data": {}}
        update = {
            "$inc": {"revision": 1},
            "$push": {"events": {"$each": [event], "$slice": -self.HISTORY_SIZE}},
            "$set": {"updated_at": datetime.now(timezone.utc)},
        }
        try:
            self._collection().update_one({"_id": self._key(topic)}, update, upsert=True)
        except DuplicateKeyError:
            # Concurrent first publishers may race on the stream's _id index.
            self._collection().update_one({"_id": self._key(topic)}, update)
        self._wake.set()

    @staticmethod
    def _resync(subscription: Subscription, revision: int):
        while True:
            try:
                subscription.queue.get_nowait()
            except queue.Empty:
                break
        subscription.queue.put_nowait(Delivery(revision, {"type": "resync", "data": {}}))
        subscription.revision = revision

    def _deliver(self, subscription: Subscription, snapshot: dict):
        revision = snapshot["revision"]
        events = snapshot.get("events", [])
        first_revision = revision - len(events) + 1
        if subscription.revision == revision:
            return
        if subscription.revision > revision or subscription.revision < first_revision - 1:
            self._resync(subscription, revision)
            return
        for offset, event in enumerate(events):
            event_revision = first_revision + offset
            if event_revision <= subscription.revision:
                continue
            try:
                subscription.queue.put_nowait(Delivery(event_revision, event))
            except queue.Full:
                self._resync(subscription, revision)
                return
            subscription.revision = event_revision

    def poll_once(self):
        with self._lock:
            topics = list(self._listeners)
        if not topics:
            return
        # One query per worker/bus cycle, regardless of subscriber count.
        snapshots = self._collection().find({"_id": {"$in": [self._key(t) for t in topics]}})
        for snapshot in snapshots:
            topic = snapshot["_id"][len(self.namespace) + 1:]
            with self._lock:
                for subscription in self._listeners.get(topic, []):
                    # Ignore a stale read if another local poll already advanced.
                    if snapshot["revision"] >= subscription.revision:
                        self._deliver(subscription, snapshot)

    def start(self, app):
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()

            def run():
                error_logged = False
                while not self._stop.is_set():
                    self._wake.wait(self.POLL_INTERVAL)
                    self._wake.clear()
                    if self._stop.is_set():
                        break
                    try:
                        with app.app_context():
                            self.poll_once()
                        error_logged = False
                    except Exception:
                        if not error_logged:
                            app.logger.exception("Realtime event polling failed (%s)", self.namespace)
                            error_logged = True

            self._thread = threading.Thread(target=run, daemon=True,
                                            name=f"realtime-{self.namespace}")
            self._thread.start()

    def stop(self):
        self._stop.set()
        self._wake.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2)


class ChannelEventBus(MongoEventBus):
    def __init__(self):
        super().__init__("channel")


class DMEventBus(MongoEventBus):
    def __init__(self):
        super().__init__("dm")
