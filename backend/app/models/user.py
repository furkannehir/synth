from datetime import datetime, timezone

from app.extensions import mongo


# ── Schema reference ────────────────────────────────────────
# {
#   "_id":                ObjectId,
#   "username":           str   (unique),
#   "email":              str   (unique),
#   "password_hash":      str,
#   "avatar":             str | None,
#   "is_online":          bool,
#   "last_seen":          datetime,
#   "created_at":         datetime,
#   "friends":            [ObjectId],   # list of friend user IDs
#   "reset_token_hash":   str | None,   # SHA-256 of one-time reset token
#   "reset_token_expires": datetime | None,
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
        "friends": [],
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


def set_reset_token(user_id: str, token_hash: str, expires) -> None:
    """Persist a hashed password-reset token with an expiry timestamp."""
    from bson import ObjectId
    get_collection().update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {
            "reset_token_hash": token_hash,
            "reset_token_expires": expires,
        }},
    )


def find_by_reset_token(token_hash: str):
    """Return the user whose reset token matches and has not expired."""
    from datetime import datetime, timezone
    return get_collection().find_one({
        "reset_token_hash": token_hash,
        "reset_token_expires": {"$gt": datetime.now(timezone.utc)},
    })


def update_password_and_clear_token(user_id: str, new_password_hash: str) -> None:
    """Set a new password hash and remove the reset token fields."""
    from bson import ObjectId
    get_collection().update_one(
        {"_id": ObjectId(user_id)},
        {
            "$set": {"password_hash": new_password_hash},
            "$unset": {"reset_token_hash": "", "reset_token_expires": ""},
        },
    )


# ── Friend management ───────────────────────────────────────

def add_friend(user_id: str, friend_id: str):
    """Add friend to both users' friends lists (bidirectional)."""
    from bson import ObjectId
    col = get_collection()
    col.update_one(
        {"_id": ObjectId(user_id)},
        {"$addToSet": {"friends": ObjectId(friend_id)}},
    )
    col.update_one(
        {"_id": ObjectId(friend_id)},
        {"$addToSet": {"friends": ObjectId(user_id)}},
    )


def remove_friend(user_id: str, friend_id: str):
    """Remove friend from both users' friends lists (bidirectional)."""
    from bson import ObjectId
    col = get_collection()
    col.update_one(
        {"_id": ObjectId(user_id)},
        {"$pull": {"friends": ObjectId(friend_id)}},
    )
    col.update_one(
        {"_id": ObjectId(friend_id)},
        {"$pull": {"friends": ObjectId(user_id)}},
    )


def are_friends(user_id: str, friend_id: str) -> bool:
    """Check if two users are friends."""
    from bson import ObjectId
    user = get_collection().find_one(
        {"_id": ObjectId(user_id), "friends": ObjectId(friend_id)},
        {"_id": 1},
    )
    return user is not None


def get_friends(user_id: str) -> list:
    """Return the full user documents for all friends of a user."""
    from bson import ObjectId
    user = find_by_id(user_id)
    if not user:
        return []
    friend_ids = user.get("friends", [])
    if not friend_ids:
        return []
    return list(get_collection().find({"_id": {"$in": friend_ids}}))


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
        "friends": [str(fid) for fid in user.get("friends", [])],
    }
    if include_roles:
        from app.models import role as role_model
        roles = role_model.get_user_roles(str(user["_id"]), server_id)
        data["roles"] = [role_model.to_dict(r) for r in roles]
    return data
