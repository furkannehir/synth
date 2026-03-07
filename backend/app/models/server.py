from datetime import datetime, timezone

from bson import ObjectId
from app.extensions import mongo


# ── Schema reference ────────────────────────────────────────
# servers {
#   "_id":         ObjectId,
#   "name":        str  (unique),
#   "icon":        str | None,
#   "owner_id":    ObjectId,
#   "is_default":  bool   (the one auto-created server),
#   "members":     list[ObjectId],   (user IDs)
#   "created_at":  datetime,
# }
# ────────────────────────────────────────────────────────────

COLLECTION = "servers"


def _col():
    return mongo.db[COLLECTION]


def ensure_indexes():
    _col().create_index("name", unique=True)


def seed_default(owner_id: str | None = None):
    """Create the default server if it doesn't exist yet."""
    if _col().find_one({"is_default": True}) is not None:
        return
    _col().insert_one({
        "name": "Synth",
        "icon": None,
        "owner_id": ObjectId(owner_id) if owner_id else None,
        "is_default": True,
        "members": [],
        "created_at": datetime.now(timezone.utc),
    })


# ── Queries ─────────────────────────────────────────────────

def find_by_id(server_id: str):
    return _col().find_one({"_id": ObjectId(server_id)})


def find_by_name(name: str):
    return _col().find_one({"name": name})


def find_default():
    return _col().find_one({"is_default": True})


def find_all():
    return list(_col().find())


def find_by_member(user_id: str):
    """Return all servers a user has joined."""
    return list(_col().find({"members": ObjectId(user_id)}))


# ── Mutations ───────────────────────────────────────────────

def create(name: str, owner_id: str, icon: str | None = None) -> str:
    result = _col().insert_one({
        "name": name,
        "icon": icon,
        "owner_id": ObjectId(owner_id),
        "is_default": False,
        "members": [ObjectId(owner_id)],  # owner auto-joins
        "created_at": datetime.now(timezone.utc),
    })
    return str(result.inserted_id)


def update(server_id: str, updates: dict):
    allowed = {"name", "icon"}
    safe = {k: v for k, v in updates.items() if k in allowed}
    if safe:
        _col().update_one({"_id": ObjectId(server_id)}, {"$set": safe})
    return find_by_id(server_id)


def delete(server_id: str):
    _col().delete_one({"_id": ObjectId(server_id)})


def add_member(server_id: str, user_id: str):
    _col().update_one(
        {"_id": ObjectId(server_id)},
        {"$addToSet": {"members": ObjectId(user_id)}},
    )


def remove_member(server_id: str, user_id: str):
    _col().update_one(
        {"_id": ObjectId(server_id)},
        {"$pull": {"members": ObjectId(user_id)}},
    )


def is_member(server_id: str, user_id: str) -> bool:
    doc = _col().find_one({
        "_id": ObjectId(server_id),
        "members": ObjectId(user_id),
    })
    return doc is not None


def member_count(server_id: str) -> int:
    doc = find_by_id(server_id)
    return len(doc.get("members", [])) if doc else 0


# ── Serialization ──────────────────────────────────────────

def to_dict(server: dict) -> dict:
    if server is None:
        return None
    return {
        "id": str(server["_id"]),
        "name": server["name"],
        "icon": server.get("icon"),
        "owner_id": str(server["owner_id"]) if server.get("owner_id") else None,
        "is_default": server.get("is_default", False),
        "member_count": len(server.get("members", [])),
        "created_at": server.get("created_at", "").isoformat() if server.get("created_at") else None,
    }
