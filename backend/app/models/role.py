from datetime import datetime, timezone

from bson import ObjectId
from app.extensions import mongo


# ── Schema reference ────────────────────────────────────────
# roles {
#   "_id":         ObjectId,
#   "name":        str  (unique — "admin", "moderator", "member"),
#   "permissions": list[str],
#   "is_default":  bool  (auto-assigned to new users?),
#   "created_at":  datetime,
# }
#
# user_roles {
#   "_id":       ObjectId,
#   "user_id":   ObjectId,
#   "role_id":   ObjectId,
#   "server_id": ObjectId,     ← scoped to a specific server
# }
# ────────────────────────────────────────────────────────────

# ── All known permissions ───────────────────────────────────
ALL_PERMISSIONS = [
    # Channels
    "manage_channels",      # create / edit / delete channels
    "join_channel",         # join a voice channel
    "speak",                # unmute & talk in a channel
    # Moderation
    "kick_user",            # kick someone from a channel
    "mute_user",            # server-mute another user
    # Admin
    "manage_roles",         # create / edit / delete roles
    "assign_roles",         # assign / revoke roles to users
    "join_any_channel",     # bypass channel restrictions
]

# ── Default role definitions (seeded on first boot) ─────────
DEFAULT_ROLES = [
    {
        "name": "admin",
        "permissions": ALL_PERMISSIONS,
        "is_default": False,
    },
    {
        "name": "moderator",
        "permissions": [
            "join_channel", "speak",
            "kick_user", "mute_user", "join_any_channel",
        ],
        "is_default": False,
    },
    {
        "name": "member",
        "permissions": [
            "join_channel", "speak",
        ],
        "is_default": True,
    },
]


# ─────────────────────────────────────────────────────────────
#  Roles collection helpers
# ─────────────────────────────────────────────────────────────

def _roles():
    return mongo.db["roles"]


def _user_roles():
    return mongo.db["user_roles"]


def ensure_indexes():
    _roles().create_index("name", unique=True)
    _user_roles().create_index(
        [("user_id", 1), ("role_id", 1), ("server_id", 1)], unique=True
    )


def seed_defaults():
    """Insert default roles if they don't already exist."""
    for role_def in DEFAULT_ROLES:
        if _roles().find_one({"name": role_def["name"]}) is None:
            _roles().insert_one({
                **role_def,
                "created_at": datetime.now(timezone.utc),
            })


# ── Role CRUD ───────────────────────────────────────────────

def find_all():
    return list(_roles().find())


def find_by_id(role_id: str):
    return _roles().find_one({"_id": ObjectId(role_id)})


def find_by_name(name: str):
    return _roles().find_one({"name": name})


def get_default_role():
    """Return the role marked as is_default (usually 'member')."""
    return _roles().find_one({"is_default": True})


def create(name: str, permissions: list[str], is_default: bool = False) -> str:
    result = _roles().insert_one({
        "name": name,
        "permissions": permissions,
        "is_default": is_default,
        "created_at": datetime.now(timezone.utc),
    })
    return str(result.inserted_id)


def update(role_id: str, updates: dict):
    allowed = {"name", "permissions", "is_default"}
    safe = {k: v for k, v in updates.items() if k in allowed}
    if safe:
        _roles().update_one({"_id": ObjectId(role_id)}, {"$set": safe})
    return find_by_id(role_id)


def delete(role_id: str):
    # Also remove all user_role assignments for this role
    _user_roles().delete_many({"role_id": ObjectId(role_id)})
    _roles().delete_one({"_id": ObjectId(role_id)})


# ── User ↔ Role assignments (server-scoped) ─────────────────

def assign_role(user_id: str, role_id: str, server_id: str):
    """Give a user a role in a specific server. Silently ignores if already assigned."""
    try:
        _user_roles().insert_one({
            "user_id": ObjectId(user_id),
            "role_id": ObjectId(role_id),
            "server_id": ObjectId(server_id),
        })
    except Exception:
        pass  # duplicate — already has this role in this server


def revoke_role(user_id: str, role_id: str, server_id: str):
    _user_roles().delete_one({
        "user_id": ObjectId(user_id),
        "role_id": ObjectId(role_id),
        "server_id": ObjectId(server_id),
    })


def get_user_roles(user_id: str, server_id: str | None = None) -> list[dict]:
    """
    Return all role documents assigned to a user.
    If server_id is given, only roles for that server.
    If server_id is None, roles across all servers (for user profile display).
    """
    query = {"user_id": ObjectId(user_id)}
    if server_id:
        query["server_id"] = ObjectId(server_id)
    assignments = _user_roles().find(query)
    role_ids = list({a["role_id"] for a in assignments})
    if not role_ids:
        return []
    return list(_roles().find({"_id": {"$in": role_ids}}))


def get_user_permissions(user_id: str, server_id: str) -> set[str]:
    """Return the merged set of permissions for a user in a specific server."""
    roles = get_user_roles(user_id, server_id)
    perms = set()
    for role in roles:
        perms.update(role.get("permissions", []))
    return perms


def user_has_permission(user_id: str, permission: str, server_id: str) -> bool:
    return permission in get_user_permissions(user_id, server_id)


def remove_all_for_user_in_server(user_id: str, server_id: str):
    """Remove all role assignments for a user in a server (e.g. on leave)."""
    _user_roles().delete_many({
        "user_id": ObjectId(user_id),
        "server_id": ObjectId(server_id),
    })


# ── Serialization ──────────────────────────────────────────

def to_dict(role: dict) -> dict:
    if role is None:
        return None
    return {
        "id": str(role["_id"]),
        "name": role["name"],
        "permissions": role.get("permissions", []),
        "is_default": role.get("is_default", False),
        "created_at": role.get("created_at", "").isoformat() if role.get("created_at") else None,
    }
