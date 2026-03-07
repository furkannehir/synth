from datetime import datetime, timezone

from app.extensions import mongo


# ── Schema reference ────────────────────────────────────────
# {
#   "_id":          ObjectId,
#   "username":     str   (unique),
#   "email":        str   (unique),
#   "password_hash": str,
#   "avatar":       str | None,
#   "is_online":    bool,
#   "last_seen":    datetime,
#   "created_at":   datetime,
# }
# ────────────────────────────────────────────────────────────

COLLECTION = "users"


def get_collection():
    return mongo.db[COLLECTION]


def ensure_indexes():
    """Create unique indexes (call once at app startup)."""
    col = get_collection()
    col.create_index("username", unique=True)
    col.create_index("email", unique=True)


def find_by_id(user_id):
    from bson import ObjectId
    return get_collection().find_one({"_id": ObjectId(user_id)})


def find_by_email(email: str):
    return get_collection().find_one({"email": email.lower()})


def find_by_username(username: str):
    return get_collection().find_one({"username": username})


def create(username: str, email: str, password_hash: str) -> str:
    """Insert a new user and return the inserted id as a string."""
    result = get_collection().insert_one({
        "username": username,
        "email": email.lower(),
        "password_hash": password_hash,
        "avatar": None,
        "is_online": False,
        "last_seen": datetime.now(timezone.utc),
        "created_at": datetime.now(timezone.utc),
    })
    return str(result.inserted_id)


def set_online(user_id, online: bool = True):
    from bson import ObjectId
    get_collection().update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {
            "is_online": online,
            "last_seen": datetime.now(timezone.utc),
        }},
    )


def to_dict(user: dict, include_roles: bool = True, server_id: str | None = None) -> dict:
    """Serialize a user document for API responses (no password)."""
    if user is None:
        return None
    data = {
        "id": str(user["_id"]),
        "username": user["username"],
        "email": user["email"],
        "avatar": user.get("avatar"),
        "is_online": user.get("is_online", False),
        "last_seen": user.get("last_seen", "").isoformat() if user.get("last_seen") else None,
        "created_at": user.get("created_at", "").isoformat() if user.get("created_at") else None,
    }
    if include_roles:
        from app.models import role as role_model
        roles = role_model.get_user_roles(str(user["_id"]), server_id)
        data["roles"] = [role_model.to_dict(r) for r in roles]
    return data
