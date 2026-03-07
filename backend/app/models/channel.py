from datetime import datetime, timezone

from bson import ObjectId
from app.extensions import mongo


# ── Schema reference ────────────────────────────────────────
# channels {
#   "_id":         ObjectId,
#   "name":        str,
#   "server_id":   ObjectId,
#   "type":        str   ("voice" | "text" — voice-only for now),
#   "position":    int   (ordering within the server),
#   "user_limit":  int   (0 = unlimited),
#   "is_default":  bool  (auto-created "General" channel),
#   "created_at":  datetime,
# }
# ────────────────────────────────────────────────────────────

COLLECTION = "channels"
VALID_TYPES = ["voice", "text"]


def _col():
    return mongo.db[COLLECTION]


def ensure_indexes():
    # Unique channel name within a server
    _col().create_index([("server_id", 1), ("name", 1)], unique=True)
    _col().create_index("server_id")


def seed_default_for_server(server_id: str):
    """Create a default 'General' voice channel for a server if none exists."""
    oid = ObjectId(server_id)
    if _col().find_one({"server_id": oid, "is_default": True}):
        return
    _col().insert_one({
        "name": "General",
        "server_id": oid,
        "type": "voice",
        "position": 0,
        "user_limit": 0,
        "is_default": True,
        "created_at": datetime.now(timezone.utc),
    })


# ── Queries ─────────────────────────────────────────────────

def find_by_id(channel_id: str):
    return _col().find_one({"_id": ObjectId(channel_id)})


def find_by_server(server_id: str):
    """Return all channels in a server, ordered by position."""
    return list(
        _col()
        .find({"server_id": ObjectId(server_id)})
        .sort("position", 1)
    )


def find_by_name_in_server(server_id: str, name: str):
    return _col().find_one({
        "server_id": ObjectId(server_id),
        "name": name,
    })


def count_in_server(server_id: str) -> int:
    return _col().count_documents({"server_id": ObjectId(server_id)})


# ── Mutations ───────────────────────────────────────────────

def create(
    name: str,
    server_id: str,
    channel_type: str = "voice",
    position: int | None = None,
    user_limit: int = 0,
) -> str:
    if position is None:
        position = count_in_server(server_id)

    result = _col().insert_one({
        "name": name,
        "server_id": ObjectId(server_id),
        "type": channel_type,
        "position": position,
        "user_limit": user_limit,
        "is_default": False,
        "created_at": datetime.now(timezone.utc),
    })
    return str(result.inserted_id)


def update(channel_id: str, updates: dict):
    allowed = {"name", "position", "user_limit", "type"}
    safe = {k: v for k, v in updates.items() if k in allowed}
    if safe:
        _col().update_one({"_id": ObjectId(channel_id)}, {"$set": safe})
    return find_by_id(channel_id)


def delete(channel_id: str):
    _col().delete_one({"_id": ObjectId(channel_id)})


def delete_by_server(server_id: str):
    """Remove all channels belonging to a server (used on server deletion)."""
    _col().delete_many({"server_id": ObjectId(server_id)})


# ── Serialization ──────────────────────────────────────────

def to_dict(channel: dict) -> dict:
    if channel is None:
        return None
    return {
        "id": str(channel["_id"]),
        "name": channel["name"],
        "server_id": str(channel["server_id"]),
        "type": channel.get("type", "voice"),
        "position": channel.get("position", 0),
        "user_limit": channel.get("user_limit", 0),
        "is_default": channel.get("is_default", False),
        "created_at": (
            channel["created_at"].isoformat()
            if channel.get("created_at")
            else None
        ),
    }
