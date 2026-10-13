"""Latest authorized voice grant for each user and channel, shared by workers."""
import secrets
from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.extensions import mongo


def ensure_indexes():
    mongo.db.voice_sessions.create_index("identity", unique=True)
    mongo.db.voice_sessions.create_index([("user_id", 1), ("server_id", 1)])
    mongo.db.voice_sessions.create_index("room")
    mongo.db.voice_sessions.create_index("server_id")


def issue(server_id: str, channel_id: str, user_id: str, version: int, room: str, desktop_session=None):
    grant = {
        "_id": f"{channel_id}:{user_id}", "server_id": ObjectId(server_id),
        "channel_id": ObjectId(channel_id), "user_id": ObjectId(user_id),
        "session_version": version, "identity": f"{user_id}.{secrets.token_hex(16)}",
        "room": room, "revoked": False, "created_at": datetime.now(timezone.utc),
        "desktop_session": desktop_session,
    }
    fields = {key: value for key, value in grant.items() if key != "_id"}
    try:
        previous = mongo.db.voice_sessions.find_one_and_update(
            {"_id": grant["_id"]}, {"$set": fields}, upsert=True,
            return_document=ReturnDocument.BEFORE,
        )
    except DuplicateKeyError:
        previous = mongo.db.voice_sessions.find_one_and_update(
            {"_id": grant["_id"]}, {"$set": fields}, return_document=ReturnDocument.BEFORE,
        )
    return grant, previous


def queue_removal(grant: dict):
    try:
        mongo.db.voice_revocations.update_one(
            {"_id": f'{grant["room"]}:{grant["identity"]}'},
            {"$setOnInsert": {key: grant[key] for key in ("room", "identity", "server_id", "channel_id")}},
            upsert=True,
        )
    except DuplicateKeyError:
        pass  # another worker already queued this exact room/identity


def revoke(query: dict) -> list[dict]:
    grants = list(mongo.db.voice_sessions.find(query))
    for grant in grants:
        # An old request must never revoke a newly issued replacement grant.
        mongo.db.voice_sessions.update_one(
            {"_id": grant["_id"], "identity": grant["identity"]}, {"$set": {"revoked": True}},
        )
        queue_removal(grant)
    return grants
