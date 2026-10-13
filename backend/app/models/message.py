from datetime import datetime, timezone

from bson import ObjectId
from app.extensions import mongo


# ── Schema reference ────────────────────────────────────────
# messages {
#   "_id":         ObjectId,
#   "channel_id":  ObjectId,
#   "server_id":   ObjectId,  # retained for cleanup if the channel is removed
#   "author_id":   ObjectId,
#   "content":     str  (max 2000 chars),
#   "created_at":  datetime,
#   "edited_at":   datetime | None,
# }
# ────────────────────────────────────────────────────────────

COLLECTION = "messages"
MAX_CONTENT_LENGTH = 2000
PAGE_SIZE = 50


def _col():
    return mongo.db[COLLECTION]


def ensure_indexes():
    # Primary query: history for a channel, newest first
    _col().create_index([("channel_id", 1), ("created_at", -1), ("_id", -1)])
    _col().create_index("server_id")


# ── Queries ─────────────────────────────────────────────────

def find_by_id(message_id: str):
    if not ObjectId.is_valid(message_id):
        return None
    return _col().find_one({"_id": ObjectId(message_id)})


def find_by_channel(channel_id: str, before: str | None = None, limit: int = PAGE_SIZE) -> list:
    """
    Return up to `limit` messages from a channel in chronological order.
    A cursor belongs to this channel. Timestamp ties are ordered by _id
    so a page boundary cannot skip messages created in the same millisecond.
    """
    query: dict = {"channel_id": ObjectId(channel_id)}

    if before is not None:
        pivot = _col().find_one({"_id": ObjectId(before), "channel_id": query["channel_id"]},
                               {"created_at": 1})
        if pivot is None:
            raise ValueError("Pagination cursor not found in this channel.")
        query["$or"] = [
            {"created_at": {"$lt": pivot["created_at"]}},
            {"created_at": pivot["created_at"], "_id": {"$lt": pivot["_id"]}},
        ]

    docs = list(
        _col()
        .find(query)
        .sort([("created_at", -1), ("_id", -1)])
        .limit(limit)
    )
    # Return in chronological order for the frontend
    docs.reverse()
    return docs


def count_by_channel(channel_id: str) -> int:
    return _col().count_documents({"channel_id": ObjectId(channel_id)})


# ── Mutations ───────────────────────────────────────────────

def create(channel_id: str, author_id: str, content: str, server_id: str | None = None) -> str:
    if server_id is None:
        from app.models import channel as channel_model
        channel = channel_model.find_by_id(channel_id)
        server_oid = channel["server_id"] if channel else None
    else:
        server_oid = ObjectId(server_id)
    result = _col().insert_one({
        "channel_id": ObjectId(channel_id),
        "server_id": server_oid,
        "author_id":  ObjectId(author_id),
        "content":    content,
        "created_at": datetime.now(timezone.utc),
        "edited_at":  None,
    })
    return str(result.inserted_id)


def update_content(message_id: str, content: str):
    _col().update_one(
        {"_id": ObjectId(message_id)},
        {"$set": {
            "content":   content,
            "edited_at": datetime.now(timezone.utc),
        }},
    )
    return find_by_id(message_id)


def delete(message_id: str):
    _col().delete_one({"_id": ObjectId(message_id)})


def delete_by_channel(channel_id: str):
    """Remove all messages in a channel (used on channel deletion)."""
    _col().delete_many({"channel_id": ObjectId(channel_id)})


# ── Serialization ───────────────────────────────────────────

def to_dict(msg: dict, author: dict | None = None) -> dict:
    if msg is None:
        return None
    return {
        "id":         str(msg["_id"]),
        "channel_id": str(msg["channel_id"]),
        "author_id":  str(msg["author_id"]),
        "content":    msg["content"],
        "created_at": msg["created_at"].isoformat() if msg.get("created_at") else None,
        "edited_at":  msg["edited_at"].isoformat()  if msg.get("edited_at")  else None,
        # Denormalised author fields (populated by service layer)
        "author_username": author["username"] if author else None,
        "author_avatar":   author.get("avatar") if author else None,
    }
