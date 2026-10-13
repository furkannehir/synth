"""Retryable server cascades; retained ID tombstones also catch late writes."""
import logging
import re
from bson import ObjectId

from app import extensions as ext
from app.models import voice_session
from app.voice_access import remove_now
from pymongo.errors import DuplicateKeyError

log = logging.getLogger(__name__)


def record(server: dict):
    try:
        ext.mongo.db.server_deletions.update_one(
            {"_id": server["_id"]},
            {"$setOnInsert": {"owner_id": server["owner_id"], "channel_ids": []}},
            upsert=True,
        )
    except DuplicateKeyError:
        pass  # another worker already recorded the same authorized deletion


def cleanup_data(server_id):
    db = ext.mongo.db
    job = db.server_deletions.find_one({"_id": server_id})
    if job is None:
        return
    parent = db.servers.find_one({"_id": server_id})
    if parent and (not parent.get("deleting") or parent.get("is_default")):
        raise RuntimeError("Refusing to clean an active server")

    # Persist channel IDs before removing their documents, including legacy
    # messages that have only channel_id. Later passes find delayed inserts.
    channel_ids = [channel["_id"] for channel in db.channels.find({"server_id": server_id}, {"_id": 1})]
    if channel_ids:
        db.server_deletions.update_one({"_id": server_id}, {"$addToSet": {"channel_ids": {"$each": channel_ids}}})
    job = db.server_deletions.find_one({"_id": server_id})
    channel_ids = job["channel_ids"]

    # Revoke tokens before deleting grants. Pending removals survive a media
    # outage independently of these server records.
    remove_now(voice_session.revoke({"server_id": server_id}))
    db.voice_sessions.delete_many({"server_id": server_id})
    db.messages.delete_many({"$or": [
        {"server_id": server_id}, {"channel_id": {"$in": channel_ids}},
    ]})
    db.realtime_streams.delete_many({"_id": {"$in": [f"channel:{cid}" for cid in channel_ids]}})
    db.invites.delete_many({"server_id": server_id})
    db.user_roles.delete_many({"server_id": server_id})
    db.roles.delete_many({"server_id": server_id})
    db.channels.delete_many({"server_id": server_id})
    # Delete the parent last; an interrupted cascade stays inaccessible and
    # discoverable by the sweeper even if recording its job initially failed.
    db.servers.delete_one({"_id": server_id, "deleting": True, "is_default": {"$ne": True}})
    ext.presence_cache.evict(str(server_id))


def cleanup_rooms(server_ids):
    if ext.media_server is None or not server_ids:
        return
    failures = []
    protected = {s["_id"] for s in ext.mongo.db.servers.find({
        "_id": {"$in": server_ids}, "$or": [{"deleting": {"$ne": True}}, {"is_default": True}],
    }, {"_id": 1})}
    prefixes = {f"synth_{sid}_" for sid in server_ids if sid not in protected}
    if not prefixes:
        return
    room_pattern = re.compile(r"^synth_[0-9a-f]{24}_[0-9a-f]{24}$")
    for room in ext.media_server.list_rooms():
        if room_pattern.fullmatch(room.name) and room.name[:31] in prefixes:
            try:
                ext.media_server.delete_room(room.name)
            except Exception as exc:
                failures.append(exc)
    if failures:
        raise RuntimeError(f"{len(failures)} deleted-server room cleanup(s) failed") from failures[0]


def cleanup_now(server_id):
    # Database cleanup must not depend on LiveKit being available.
    try:
        cleanup_data(server_id)
    except Exception:
        log.warning("Server data cleanup pending; the sweeper will retry", exc_info=True)
    try:
        cleanup_rooms([server_id])
    except Exception:
        log.warning("Server room cleanup pending; the sweeper will retry", exc_info=True)


def sweep_deleted_servers():
    db = ext.mongo.db
    # Recover interruption between marking a server and recording its job.
    for server in db.servers.find({"deleting": True, "is_default": {"$ne": True}}):
        record(server)
    # Older versions deleted the parent without cascading. Their children still
    # carry server IDs, so they can be recovered without touching global roles.
    candidates = set()
    for collection in ("channels", "messages", "roles", "user_roles", "invites", "voice_sessions", "voice_revocations"):
        candidates.update(sid for sid in db[collection].distinct("server_id") if isinstance(sid, ObjectId))
    existing = {s["_id"] for s in db.servers.find({"_id": {"$in": list(candidates)}}, {"_id": 1})}
    for sid in candidates - existing:
        try:
            db.server_deletions.update_one({"_id": sid}, {"$setOnInsert": {"owner_id": None, "channel_ids": []}}, upsert=True)
        except DuplicateKeyError:
            pass
    ids, failures = [], []
    for job in db.server_deletions.find({}, {"_id": 1}):
        ids.append(job["_id"])
        try:
            cleanup_data(job["_id"])
        except Exception as exc:
            failures.append(exc)
    try:
        cleanup_rooms(ids)
    except Exception as exc:
        failures.append(exc)
    if failures:
        raise RuntimeError(f"{len(failures)} server cleanup operation(s) failed") from failures[0]
