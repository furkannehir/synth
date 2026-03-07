import secrets
from datetime import datetime, timezone

from bson import ObjectId
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


def ensure_indexes():
    _col().create_index("code", unique=True)
    _col().create_index("server_id")


def _generate_code(length=8):
    """Generate a URL-safe random invite code."""
    return secrets.token_urlsafe(length)[:length]


def create(server_id: str, created_by: str,
           max_uses: int = 0, expires_at: datetime | None = None) -> dict:
    code = _generate_code()
    # Ensure uniqueness (extremely unlikely collision, but be safe)
    while _col().find_one({"code": code}):
        code = _generate_code()

    doc = {
        "code": code,
        "server_id": ObjectId(server_id),
        "created_by": ObjectId(created_by),
        "max_uses": max_uses,
        "uses": 0,
        "expires_at": expires_at,
        "created_at": datetime.now(timezone.utc),
    }
    _col().insert_one(doc)
    return doc


def find_by_code(code: str):
    return _col().find_one({"code": code})


def find_by_server(server_id: str) -> list[dict]:
    return list(_col().find({"server_id": ObjectId(server_id)}))


def increment_uses(code: str):
    _col().update_one({"code": code}, {"$inc": {"uses": 1}})


def delete_by_code(code: str):
    _col().delete_one({"code": code})


def delete_by_server(server_id: str):
    _col().delete_many({"server_id": ObjectId(server_id)})


def to_dict(invite: dict) -> dict:
    return {
        "id": str(invite["_id"]),
        "code": invite["code"],
        "server_id": str(invite["server_id"]),
        "created_by": str(invite["created_by"]),
        "max_uses": invite.get("max_uses", 0),
        "uses": invite.get("uses", 0),
        "expires_at": invite["expires_at"].isoformat() if invite.get("expires_at") else None,
        "created_at": invite["created_at"].isoformat(),
    }
