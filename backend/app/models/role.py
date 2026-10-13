from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError, OperationFailure

from app.extensions import mongo


# ── Schema reference ────────────────────────────────────────
# roles {
#   "_id":         ObjectId,
#   "name":        str  (unique within a server),
#   "server_id":   ObjectId,
#   "is_builtin":  bool,
#   "permissions": list[str],
#   "is_default":  bool  (auto-assigned to new members in this server),
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
    # Messages
    "manage_messages",      # delete any message in a text channel
    "send_messages",        # send messages in text channels
    # Moderation
    "kick_user",            # kick someone from a channel
    "mute_user",            # server-mute another user
    # Admin / Server
    "manage_server",        # edit server settings, create invites
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
            "send_messages", "manage_messages",
            "kick_user", "mute_user", "join_any_channel",
        ],
        "is_default": False,
    },
    {
        "name": "member",
        "permissions": [
            "join_channel", "speak", "send_messages",
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
    # Install the scoped constraint before dropping the old global constraint.
    _roles().create_index([("server_id", 1), ("name", 1)], unique=True)
    for name, index in _roles().index_information().items():
        if index.get("unique") and index["key"] == [("name", 1)]:
            try:
                _roles().drop_index(name)
            except OperationFailure as exc:
                if exc.code != 27:  # another startup worker already dropped it
                    raise
    _user_roles().create_index(
        [("user_id", 1), ("role_id", 1), ("server_id", 1)], unique=True
    )
    _user_roles().create_index("server_id")


def _ensure_role(server_id: str, definition: dict) -> dict:
    """Insert once, including when multiple startup workers seed concurrently."""
    query = {"server_id": ObjectId(server_id), "name": definition["name"]}
    try:
        return _roles().find_one_and_update(
            query,
            {"$setOnInsert": {
                **definition,
                "server_id": query["server_id"],
                "created_at": datetime.now(timezone.utc),
            }},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError:
        role = _roles().find_one(query)
        if role is None:
            raise
        return role


def seed_defaults(server_id: str):
    """Create this server's built-ins without overwriting its local settings."""
    has_default = get_default_role(server_id) is not None
    for definition in DEFAULT_ROLES:
        _ensure_role(server_id, {
            **definition,
            "is_default": definition["is_default"] and not has_default,
            "is_builtin": True,
        })


def migrate_legacy_roles():
    """Idempotently replace global role assignments with server-local copies.

    Shared built-ins/defaults are rebuilt from code, since their old settings
    could have been changed by an unrelated server owner. Custom roles are
    copied only into servers where they have existing member assignments.
    Unscoped definitions and invalid assignments remain inert for inspection.
    """
    servers = {s["_id"]: s for s in mongo.db.servers.find({"deleting": {"$ne": True}})}
    for server_id in servers:
        seed_defaults(str(server_id))

    legacy_roles = {r["_id"]: r for r in _roles().find({"server_id": None})}
    if not legacy_roles:
        return

    builtin_names = {r["name"] for r in DEFAULT_ROLES}
    copies = {}
    assignments = _user_roles().find({"role_id": {"$in": list(legacy_roles)}})
    for assignment in assignments:
        server_id = assignment.get("server_id")
        server = servers.get(server_id)
        if server is None:
            continue
        user_id = assignment["user_id"]
        if user_id not in server.get("members", []) and user_id != server.get("owner_id"):
            continue

        legacy = legacy_roles[assignment["role_id"]]
        key = (server_id, legacy["_id"])
        if key not in copies:
            if legacy["name"] in builtin_names:
                copies[key] = find_by_name(legacy["name"], str(server_id))
            else:
                copies[key] = _ensure_role(str(server_id), {
                    "name": legacy["name"],
                    "permissions": legacy.get("permissions", []),
                    "is_default": False,
                    "is_builtin": False,
                })

        # Copy before removing the old assignment so interruptions are retryable.
        scoped_role = copies[key]
        if assign_role(str(user_id), str(scoped_role["_id"]), str(server_id)):
            _user_roles().delete_one({
                "_id": assignment["_id"], "role_id": legacy["_id"],
            })


def find_all(server_id: str):
    return list(_roles().find({"server_id": ObjectId(server_id)}))


def find_by_id(role_id: str, server_id: str):
    if not ObjectId.is_valid(role_id):
        return None
    return _roles().find_one({
        "_id": ObjectId(role_id), "server_id": ObjectId(server_id),
    })


def find_by_name(name: str, server_id: str):
    return _roles().find_one({"name": name, "server_id": ObjectId(server_id)})


def get_default_role(server_id: str):
    return _roles().find_one({"server_id": ObjectId(server_id), "is_default": True})


def clear_default(server_id: str):
    _roles().update_many(
        {"server_id": ObjectId(server_id)}, {"$set": {"is_default": False}},
    )


def create(name: str, permissions: list[str], server_id: str,
           is_default: bool = False) -> str:
    result = _roles().insert_one({
        "name": name,
        "permissions": permissions,
        "server_id": ObjectId(server_id),
        "is_default": is_default,
        "is_builtin": False,
        "created_at": datetime.now(timezone.utc),
    })
    return str(result.inserted_id)


def update(role_id: str, server_id: str, updates: dict):
    allowed = {"name", "permissions", "is_default"}
    safe = {k: v for k, v in updates.items() if k in allowed}
    if safe:
        _roles().update_one(
            {"_id": ObjectId(role_id), "server_id": ObjectId(server_id)},
            {"$set": safe},
        )
    return find_by_id(role_id, server_id)


def delete(role_id: str, server_id: str):
    if find_by_id(role_id, server_id) is None:
        return
    _user_roles().delete_many({
        "role_id": ObjectId(role_id), "server_id": ObjectId(server_id),
    })
    _roles().delete_one({
        "_id": ObjectId(role_id), "server_id": ObjectId(server_id),
    })


def assign_role(user_id: str, role_id: str, server_id: str) -> bool:
    if find_by_id(role_id, server_id) is None:
        return False
    try:
        _user_roles().insert_one({
            "user_id": ObjectId(user_id),
            "role_id": ObjectId(role_id),
            "server_id": ObjectId(server_id),
        })
    except DuplicateKeyError:
        pass
    return True


def revoke_role(user_id: str, role_id: str, server_id: str):
    if find_by_id(role_id, server_id) is None:
        return
    _user_roles().delete_one({
        "user_id": ObjectId(user_id),
        "role_id": ObjectId(role_id),
        "server_id": ObjectId(server_id),
    })


def get_user_roles(user_id: str, server_id: str | None = None) -> list[dict]:
    query = {"user_id": ObjectId(user_id)}
    if server_id is not None:
        query["server_id"] = ObjectId(server_id)
    # Check both scopes: corrupt or legacy assignments must never import global
    # permissions or permissions from a different server, including in profiles.
    scopes = [
        {"_id": a["role_id"], "server_id": a["server_id"]}
        for a in _user_roles().find(query)
        if a.get("server_id") is not None
    ]
    return list(_roles().find({"$or": scopes})) if scopes else []


def get_user_permissions(user_id: str, server_id: str) -> set[str]:
    perms = set()
    for role in get_user_roles(user_id, server_id):
        perms.update(role.get("permissions", []))
    return perms


def user_has_permission(user_id: str, permission: str, server_id: str) -> bool:
    return permission in get_user_permissions(user_id, server_id)


def remove_all_for_user_in_server(user_id: str, server_id: str):
    _user_roles().delete_many({
        "user_id": ObjectId(user_id), "server_id": ObjectId(server_id),
    })


def to_dict(role: dict) -> dict:
    if role is None:
        return None
    return {
        "id": str(role["_id"]),
        "server_id": str(role["server_id"]),
        "name": role["name"],
        "permissions": role.get("permissions", []),
        "is_default": role.get("is_default", False),
        "is_builtin": role.get("is_builtin", False),
        "created_at": role["created_at"].isoformat() if role.get("created_at") else None,
    }
