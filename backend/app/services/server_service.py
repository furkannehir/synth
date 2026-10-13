from bson import ObjectId

from app.models import server as server_model
from app.models import user as user_model
from app.models import role as role_model


class ServerError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def list_servers(user_id: str | None = None) -> list[dict]:
    """List all servers, or only those a user has joined."""
    if user_id:
        servers = server_model.find_by_member(user_id)
    else:
        servers = server_model.find_all()
    return [server_model.to_dict(s) for s in servers]


def get_server(server_id: str) -> dict:
    server = server_model.find_by_id(server_id)
    if server is None:
        raise ServerError("Server not found.", 404)
    return server_model.to_dict(server)


def create_server(name: str, owner_id: str, icon: str | None = None) -> dict:
    if not name or len(name) < 2:
        raise ServerError("Server name must be at least 2 characters.")
    if len(name) > 100:
        raise ServerError("Server name cannot exceed 100 characters.")
    if server_model.find_by_name(name):
        raise ServerError(f"A server named '{name}' already exists.", 409)

    server_id = server_model.create(name, owner_id, icon)

    role_model.seed_defaults(server_id)
    # Owner gets "admin" role scoped to this server
    admin_role = role_model.find_by_name("admin", server_id)
    if admin_role:
        role_model.assign_role(owner_id, str(admin_role["_id"]), server_id)

    server = server_model.find_by_id(server_id)
    if server is None:
        raise ServerError("Server not found.", 404)
    return server_model.to_dict(server)


def update_server(server_id: str, user_id: str, updates: dict) -> dict:
    server = server_model.find_by_id(server_id)
    if server is None:
        raise ServerError("Server not found.", 404)
    if str(server["owner_id"]) != user_id:
        raise ServerError("Only the server owner can edit this server.", 403)

    if "name" in updates:
        if not updates["name"] or len(updates["name"]) < 2:
            raise ServerError("Server name must be at least 2 characters.")
        existing = server_model.find_by_name(updates["name"])
        if existing and str(existing["_id"]) != server_id:
            raise ServerError(f"A server named '{updates['name']}' already exists.", 409)

    updated = server_model.update(server_id, updates)
    if updated is None:
        raise ServerError("Server not found.", 404)
    return server_model.to_dict(updated)


def delete_server(server_id: str, user_id: str):
    from app.extensions import mongo
    from app.services import server_cleanup
    if not ObjectId.is_valid(server_id):
        raise ServerError("Server not found.", 404)
    oid = ObjectId(server_id)
    server = mongo.db.servers.find_one({"_id": oid})
    if server is None:
        job = mongo.db.server_deletions.find_one({"_id": oid, "owner_id": ObjectId(user_id)})
        if job is None:
            raise ServerError("Server not found.", 404)
        server_cleanup.cleanup_now(oid)
        return
    if server.get("is_default"):
        raise ServerError("Cannot delete the default server.", 403)
    if str(server["owner_id"]) != user_id:
        raise ServerError("Only the server owner can delete this server.", 403)
    marked = server_model.mark_deleting(server_id, user_id)
    if marked is None:
        if mongo.db.server_deletions.find_one({"_id": oid, "owner_id": ObjectId(user_id)}) is None:
            raise ServerError("Server not found.", 404)
        server_cleanup.cleanup_now(oid)
        return
    server_cleanup.record(marked)
    server_cleanup.cleanup_now(oid)


def join_server(server_id: str, user_id: str):
    server = server_model.find_by_id(server_id)
    if server is None:
        raise ServerError("Server not found.", 404)
    if server_model.is_member(server_id, user_id):
        raise ServerError("You are already a member of this server.", 409)
    if not server_model.add_member(server_id, user_id):
        if server_model.find_by_id(server_id) is None:
            raise ServerError("Server not found.", 404)
        raise ServerError("You are already a member of this server.", 409)

    # Assign the default "member" role scoped to this server
    default_role = role_model.get_default_role(server_id)
    if default_role:
        role_model.assign_role(user_id, str(default_role["_id"]), server_id)
    if server_model.find_by_id(server_id) is None:
        role_model.remove_all_for_user_in_server(user_id, server_id)
        raise ServerError("Server not found.", 404)


def leave_server(server_id: str, user_id: str):
    server = server_model.find_by_id(server_id)
    if server is None:
        raise ServerError("Server not found.", 404)
    if str(server["owner_id"]) == user_id:
        raise ServerError("The server owner cannot leave. Transfer ownership or delete the server.", 403)
    if not server_model.is_member(server_id, user_id):
        raise ServerError("You are not a member of this server.", 400)
    server_model.remove_member(server_id, user_id)

    # Remove all role assignments for this user in this server
    role_model.remove_all_for_user_in_server(user_id, server_id)
    from app.services.voice_service import revoke_server_sessions
    revoke_server_sessions(server_id, user_id)


def _require_server(server_id: str) -> dict:
    if not ObjectId.is_valid(server_id):
        raise ServerError("Server not found.", 404)
    server = server_model.find_by_id(server_id)
    if server is None:
        raise ServerError("Server not found.", 404)
    return server


def require_member(server_id: str, user_id: str) -> dict:
    server = _require_server(server_id)
    if not ObjectId.is_valid(user_id) or ObjectId(user_id) not in server.get("members", []):
        raise ServerError("You must be a member of this server.", 403)
    return server


def _public_members(server: dict) -> list[dict]:
    # Fetch only the fields this response is allowed to expose.
    users = user_model.get_collection().find(
        {"_id": {"$in": server.get("members", [])}},
        {"username": 1, "avatar": 1, "is_online": 1, "last_seen": 1},
    )
    return [user_model.to_public_dict(user) for user in users]


def get_members(server_id: str, user_id: str) -> list[dict]:
    return _public_members(require_member(server_id, user_id))


def get_presence_members(server_id: str) -> list[dict]:
    """Internal cache refresh; API callers must use get_members with a user ID."""
    return _public_members(_require_server(server_id))
