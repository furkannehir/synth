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

    # Owner gets "admin" role scoped to this server
    admin_role = role_model.find_by_name("admin")
    if admin_role:
        role_model.assign_role(owner_id, str(admin_role["_id"]), server_id)

    return server_model.to_dict(server_model.find_by_id(server_id))


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
    return server_model.to_dict(updated)


def delete_server(server_id: str, user_id: str):
    server = server_model.find_by_id(server_id)
    if server is None:
        raise ServerError("Server not found.", 404)
    if server.get("is_default"):
        raise ServerError("Cannot delete the default server.", 403)
    if str(server["owner_id"]) != user_id:
        raise ServerError("Only the server owner can delete this server.", 403)
    server_model.delete(server_id)


def join_server(server_id: str, user_id: str):
    server = server_model.find_by_id(server_id)
    if server is None:
        raise ServerError("Server not found.", 404)
    if server_model.is_member(server_id, user_id):
        raise ServerError("You are already a member of this server.", 409)
    server_model.add_member(server_id, user_id)

    # Assign the default "member" role scoped to this server
    default_role = role_model.get_default_role()
    if default_role:
        role_model.assign_role(user_id, str(default_role["_id"]), server_id)


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


def get_members(server_id: str) -> list[dict]:
    server = server_model.find_by_id(server_id)
    if server is None:
        raise ServerError("Server not found.", 404)
    member_ids = server.get("members", [])
    members = []
    for mid in member_ids:
        user = user_model.find_by_id(str(mid))
        if user:
            members.append(user_model.to_dict(user, include_roles=False))
    return members
