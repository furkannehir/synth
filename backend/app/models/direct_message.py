from datetime import datetime, timezone

from bson import ObjectId
from app.extensions import mongo


# ── Schema reference ────────────────────────────────────────
# direct_messages {
#   "_id":              ObjectId,
#   "sender_id":        ObjectId,
#   "recipient_id":     ObjectId,
#   "conversation_key": str,       # sorted "{min_id}_{max_id}"
#   "content":          str,
#   "created_at":       datetime,
#   "edited_at":        datetime | None,
#   "is_read":          bool,
# }
# ────────────────────────────────────────────────────────────

COLLECTION = "direct_messages"
MAX_CONTENT_LENGTH = 2000
PAGE_SIZE = 50


def _col():
    return mongo.db[COLLECTION]


def ensure_indexes():
    """Create indexes (call once at app startup)."""
    _col().create_index([("conversation_key", 1), ("created_at", -1)])
    _col().create_index("sender_id")
    _col().create_index("recipient_id")


# ── Helpers ─────────────────────────────────────────────────

def make_conversation_key(user_a: str, user_b: str) -> str:
    """Deterministic key for a conversation between two users."""
    ids = sorted([str(user_a), str(user_b)])
    return f"{ids[0]}_{ids[1]}"


# ── Queries ─────────────────────────────────────────────────

def find_by_id(dm_id: str):
    return _col().find_one({"_id": ObjectId(dm_id)})


def find_by_conversation(
    conversation_key: str,
    before: str | None = None,
    limit: int = PAGE_SIZE,
) -> list:
    """
    Return up to `limit` messages in a conversation, ordered newest-first.
    Pass `before` (a message _id string) for cursor-based pagination.
    Returns in chronological order.
    """
    query: dict = {"conversation_key": conversation_key}

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
    docs.reverse()
    return docs


def get_recent_conversations(user_id: str, offset: int = 0, limit: int = PAGE_SIZE):
    """
    Return recent conversations for a user, paginated.
    Returns: list of dicts: {"_id": conv_key, "last_message": doc, "unread_count": int}
    """
    user_oid = ObjectId(user_id)
    pipeline = [
        {"$match": {"$or": [{"sender_id": user_oid}, {"recipient_id": user_oid}]}},
        {"$sort": {"created_at": -1}},
        {"$group": {
            "_id": "$conversation_key",
            "last_message": {"$first": "$$ROOT"},
            "unread_count": {
                "$sum": {
                    "$cond": [{"$and": [{"$eq": ["$recipient_id", user_oid]}, {"$ne": ["$is_read", True]}]}, 1, 0]
                }
            }
        }},
        {"$sort": {"last_message.created_at": -1}},
        {"$skip": offset},
        {"$limit": limit}
    ]
    return list(_col().aggregate(pipeline))


def get_total_unread_count(user_id: str) -> int:
    return _col().count_documents(
        {"recipient_id": ObjectId(user_id), "is_read": {"$ne": True}}
    )


# ── Mutations ───────────────────────────────────────────────

def create(sender_id: str, recipient_id: str, content: str) -> str:
    """Insert a new direct message and return the inserted id."""
    result = _col().insert_one({
        "sender_id": ObjectId(sender_id),
        "recipient_id": ObjectId(recipient_id),
        "conversation_key": make_conversation_key(sender_id, recipient_id),
        "content": content,
        "created_at": datetime.now(timezone.utc),
        "edited_at": None,
        "is_read": False,
    })
    return str(result.inserted_id)


def update_content(dm_id: str, content: str):
    _col().update_one(
        {"_id": ObjectId(dm_id)},
        {"$set": {
            "content": content,
            "edited_at": datetime.now(timezone.utc),
        }},
    )
    return find_by_id(dm_id)


def delete(dm_id: str):
    _col().delete_one({"_id": ObjectId(dm_id)})


def mark_read(conversation_key: str, recipient_id: str) -> int:
    """Mark all unread messages addressed to the recipient in this conversation as read."""
    res = _col().update_many(
        {
            "conversation_key": conversation_key,
            "recipient_id": ObjectId(recipient_id),
            "is_read": {"$ne": True}
        },
        {"$set": {"is_read": True}}
    )
    return res.modified_count


# ── Serialization ───────────────────────────────────────────

def to_dict(dm: dict, sender: dict | None = None) -> dict:
    """Serialize a DM document for API responses."""
    if dm is None:
        return None
    return {
        "id": str(dm["_id"]),
        "sender_id": str(dm["sender_id"]),
        "recipient_id": str(dm["recipient_id"]),
        "conversation_key": dm["conversation_key"],
        "content": dm["content"],
        "created_at": dm["created_at"].isoformat() if dm.get("created_at") else None,
        "edited_at": dm["edited_at"].isoformat() if dm.get("edited_at") else None,
        "is_read": dm.get("is_read", False),
        # Denormalised sender fields
        "sender_username": sender["username"] if sender else None,
        "sender_avatar": sender.get("avatar") if sender else None,
    }
