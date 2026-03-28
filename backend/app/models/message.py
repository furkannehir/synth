from datetime import datetime, timezone

from bson import ObjectId
from app.extensions import mongo


# ── Schema reference ────────────────────────────────────────
# messages {
#   "_id":         ObjectId,
#   "channel_id":  ObjectId,
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
    _col().create_index([("channel_id", 1), ("created_at", -1)])


# ── Queries ─────────────────────────────────────────────────

def find_by_id(message_id: str):
    return _col().find_one({"_id": ObjectId(message_id)})


def find_by_channel(channel_id: str, before: str | None = None, limit: int = PAGE_SIZE) -> list:
    """
    Return up to `limit` messages in a channel, ordered newest-first.
    Pass `before` (a message _id string) for cursor-based pagination —
    only messages created before that message are returned.
    """
    query: dict = {"channel_id": ObjectId(channel_id)}

    if before:
        pivot = _col().find_one({"_id": ObjectId(before)}, {"created_at": 1})
        if pivot:
            query["created_at"] = {"$lt": pivot["created_at"]}

    docs = list(
        _col()
        .find(query)
        .sort("created_at", -1)
        .limit(limit)
    )
    # Return in chronological order for the frontend
    docs.reverse()
    return docs


def count_by_channel(channel_id: str) -> int:
    return _col().count_documents({"channel_id": ObjectId(channel_id)})


# ── Mutations ───────────────────────────────────────────────

def create(channel_id: str, author_id: str, content: str) -> str:
    result = _col().insert_one({
        "channel_id": ObjectId(channel_id),
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
