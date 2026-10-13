import secrets
from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from app.extensions import mongo


# ── Schema reference ────────────────────────────────────────
# invites {
#   "_id":         ObjectId,
#   "code":        str  (unique, random 8-char alphanumeric),
#   "server_id":   ObjectId,
#   "created_by":  ObjectId  (user who created the invite),
#   "max_uses":    int  (0 = unlimited),
#   "uses":        int  (how many times used so far),
#   "expires_at":  datetime | None,
#   "created_at":  datetime,
# }
# ────────────────────────────────────────────────────────────

COLLECTION = "invites"


def _col():
    return mongo.db[COLLECTION]


def _as_utc_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def ensure_indexes():
    _col().create_index("code", unique=True)
    _col().create_index("server_id")
    _col().create_index("expires_at")


def _generate_code(length=8):
    """Generate a URL-safe random invite code."""
    return secrets.token_urlsafe(length)[:length]


def create(server_id: str, created_by: str,
           max_uses: int = 0, expires_at: datetime | None = None) -> dict:
    doc = {
        "server_id": ObjectId(server_id),
        "created_by": ObjectId(created_by),
        "max_uses": max_uses,
        "uses": 0,
        "expires_at": expires_at,
        "created_at": datetime.now(timezone.utc),
    }
    while True:
        doc["code"] = _generate_code()
        try:
            _col().insert_one(doc)
            break
        except DuplicateKeyError:
            # The unique index, rather than a read, arbitrates concurrent creates.
            doc.pop("_id", None)
    return doc


def find_by_code(code: str):
    return _col().find_one({"code": code})


def find_by_server(server_id: str) -> list[dict]:
    return list(_col().find({"server_id": ObjectId(server_id)}))


def find_by_server_and_creator(server_id: str, created_by: str) -> list[dict]:
    return list(_col().find({
        "server_id": ObjectId(server_id),
        "created_by": ObjectId(created_by),
    }))


def claim_use(invite_id: ObjectId, now: datetime) -> dict | None:
    """Reserve a use only while this exact invite is active and below its limit."""
    return _col().find_one_and_update({
        "_id": invite_id,
        "$and": [
            {"$or": [{"expires_at": None}, {"expires_at": {"$gt": now}}]},
            {"$or": [{"max_uses": 0}, {"max_uses": {"$exists": False}},
                     {"$expr": {"$lt": [{"$ifNull": ["$uses", 0]}, "$max_uses"]}}]},
        ],
    }, {"$inc": {"uses": 1, "pending_uses": 1}}, return_document=ReturnDocument.AFTER)


def finish_use(invite_id: ObjectId, *, refund: bool = False):
    changes = {"pending_uses": -1}
    if refund:
        changes["uses"] = -1
    _col().update_one({"_id": invite_id, "pending_uses": {"$gt": 0}}, {"$inc": changes})


def expire_by_code(code: str, expired_at: datetime):
    _col().update_one({"code": code}, {"$set": {"expires_at": expired_at}})


def delete_by_code(code: str):
    _col().delete_one({"code": code})


def delete_by_server(server_id: str):
    _col().delete_many({"server_id": ObjectId(server_id)})


def delete_stale(now: datetime) -> int:
    result = _col().delete_many({
        "$or": [
            {"expires_at": {"$ne": None, "$lte": now}},
            {"max_uses": {"$gt": 0}, "pending_uses": {"$not": {"$gt": 0}},
             "$expr": {"$gte": ["$uses", "$max_uses"]}},
        ]
    })
    return result.deleted_count


def to_dict(invite: dict) -> dict:
    expires_at = _as_utc_aware(invite.get("expires_at"))
    created_at = _as_utc_aware(invite.get("created_at"))
    return {
        "id": str(invite["_id"]),
        "code": invite["code"],
        "server_id": str(invite["server_id"]),
        "created_by": str(invite["created_by"]),
        "max_uses": invite.get("max_uses", 0),
        "uses": invite.get("uses", 0),
        "expires_at": expires_at.isoformat() if expires_at else None,
        "created_at": created_at.isoformat() if created_at else None,
    }
