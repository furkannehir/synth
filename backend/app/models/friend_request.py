import enum
from datetime import datetime, timezone

from bson import ObjectId
from app.extensions import mongo


# ── Status enum ─────────────────────────────────────────────
class FriendRequestStatus(enum.Enum):
    PENDING = "pending"


# ── Schema reference ────────────────────────────────────────
# friend_requests {
#   "_id":           ObjectId,
#   "requester_id":  ObjectId,   # who sent the request
#   "addressee_id":  ObjectId,   # who receives the request
#   "status":        str,        # FriendRequestStatus value
#   "created_at":    datetime,
# }
# ────────────────────────────────────────────────────────────

COLLECTION = "friend_requests"


def _col():
    return mongo.db[COLLECTION]


def ensure_indexes():
    """Create indexes (call once at app startup)."""
    _col().create_index(
        [("requester_id", 1), ("addressee_id", 1)],
        unique=True,
    )
    _col().create_index([("addressee_id", 1), ("status", 1)])


# ── Queries ─────────────────────────────────────────────────

def find_by_id(request_id: str):
    return _col().find_one({"_id": ObjectId(request_id)})


def find_between(user_a: str, user_b: str):
    """Find any pending request between two users (either direction)."""
    return _col().find_one({
        "$or": [
            {"requester_id": ObjectId(user_a), "addressee_id": ObjectId(user_b)},
            {"requester_id": ObjectId(user_b), "addressee_id": ObjectId(user_a)},
        ],
    })


def find_pending_incoming(user_id: str) -> list:
    """Requests addressed to this user (they need to accept/reject)."""
    return list(_col().find({
        "addressee_id": ObjectId(user_id),
        "status": FriendRequestStatus.PENDING.value,
    }).sort("created_at", -1))


def find_pending_outgoing(user_id: str) -> list:
    """Requests sent by this user (awaiting response)."""
    return list(_col().find({
        "requester_id": ObjectId(user_id),
        "status": FriendRequestStatus.PENDING.value,
    }).sort("created_at", -1))


# ── Mutations ───────────────────────────────────────────────

def create(requester_id: str, addressee_id: str) -> str:
    """Insert a new pending friend request. Returns the inserted id."""
    result = _col().insert_one({
        "requester_id": ObjectId(requester_id),
        "addressee_id": ObjectId(addressee_id),
        "status": FriendRequestStatus.PENDING.value,
        "created_at": datetime.now(timezone.utc),
    })
    return str(result.inserted_id)


def delete(request_id: str):
    """Remove a friend request (used on accept, reject, cancel)."""
    _col().delete_one({"_id": ObjectId(request_id)})


# ── Serialization ───────────────────────────────────────────

def to_dict(doc: dict, user: dict | None = None) -> dict:
    """Serialize a friend request document for API responses."""
    if doc is None:
        return None
    data = {
        "id": str(doc["_id"]),
        "requester_id": str(doc["requester_id"]),
        "addressee_id": str(doc["addressee_id"]),
        "status": doc["status"],
        "created_at": doc["created_at"].isoformat() if doc.get("created_at") else None,
    }
    if user:
        data["user"] = {
            "id": str(user["_id"]),
            "username": user["username"],
            "avatar": user.get("avatar"),
            "is_online": user.get("is_online", False),
        }
    return data
