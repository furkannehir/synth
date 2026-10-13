from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.models import role as role_model
from app.models import server as server_model
from app.models import user as user_model


class RoleError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _require_server(server_id: str) -> dict:
    if not ObjectId.is_valid(server_id):
        raise RoleError("Server not found.", 404)
    server = server_model.find_by_id(server_id)
    if server is None:
        raise RoleError("Server not found.", 404)
    return server


def _require_member(server_id: str, user_id: str):
    _require_server(server_id)
    if not ObjectId.is_valid(user_id) or not server_model.is_member(server_id, user_id):
        raise RoleError("You must be a member of this server.", 403)


def _require_role(role_id: str, server_id: str) -> dict:
    role = role_model.find_by_id(role_id, server_id)
    if role is None:
        raise RoleError("Role not found.", 404)
    return role


def list_roles(server_id: str, user_id: str) -> list[dict]:
    _require_member(server_id, user_id)
    return [role_model.to_dict(r) for r in role_model.find_all(server_id)]


def list_permissions(server_id: str, user_id: str) -> list[str]:
    _require_member(server_id, user_id)
    return role_model.ALL_PERMISSIONS


def get_role(role_id: str, server_id: str, user_id: str) -> dict:
    _require_member(server_id, user_id)
    return role_model.to_dict(_require_role(role_id, server_id))


def create_role(name: str, permissions: list[str], server_id: str,
                is_default: bool = False) -> dict:
    _require_server(server_id)
    if not name or len(name) < 2:
        raise RoleError("Role name must be at least 2 characters.")
    invalid = set(permissions) - set(role_model.ALL_PERMISSIONS)
    if invalid:
        raise RoleError(f"Unknown permissions: {', '.join(sorted(invalid))}")
    if role_model.find_by_name(name, server_id):
        raise RoleError(f"Role '{name}' already exists.", 409)

    try:
        role_id = role_model.create(name, permissions, server_id)
    except DuplicateKeyError:
        raise RoleError(f"Role '{name}' already exists.", 409)
    if is_default:
        role_model.clear_default(server_id)
        role_model.update(role_id, server_id, {"is_default": True})
    if server_model.find_by_id(server_id) is None:
        role_model.delete(role_id, server_id)
        raise RoleError("Server not found.", 404)
    return role_model.to_dict(role_model.find_by_id(role_id, server_id))


def update_role(role_id: str, server_id: str, updates: dict) -> dict:
    _require_server(server_id)
    role = _require_role(role_id, server_id)
    if "permissions" in updates:
        invalid = set(updates["permissions"]) - set(role_model.ALL_PERMISSIONS)
        if invalid:
            raise RoleError(f"Unknown permissions: {', '.join(sorted(invalid))}")
    if "name" in updates and updates["name"] != role["name"]:
        if role.get("is_builtin"):
            raise RoleError("Cannot rename built-in roles.", 403)
        if not updates["name"] or len(updates["name"].strip()) < 2:
            raise RoleError("Role name must be at least 2 characters.")
        if role_model.find_by_name(updates["name"], server_id):
            raise RoleError(f"Role '{updates['name']}' already exists.", 409)

    # A failed name update must not clear the server's current default.
    safe_updates = {k: v for k, v in updates.items() if k != "is_default"}
    try:
        role_model.update(role_id, server_id, safe_updates)
    except DuplicateKeyError:
        raise RoleError(f"Role '{updates['name']}' already exists.", 409)
    if "is_default" in updates:
        if updates["is_default"]:
            role_model.clear_default(server_id)
        role_model.update(role_id, server_id, {"is_default": updates["is_default"]})
    return role_model.to_dict(role_model.find_by_id(role_id, server_id))


def delete_role(role_id: str, server_id: str):
    _require_server(server_id)
    role = _require_role(role_id, server_id)
    if role.get("is_builtin"):
        raise RoleError("Cannot delete built-in roles.", 403)
    role_model.delete(role_id, server_id)


def assign_role_to_user(user_id: str, role_id: str, server_id: str):
    _require_server(server_id)
    _require_role(role_id, server_id)
    if not ObjectId.is_valid(user_id) or user_model.find_by_id(user_id) is None:
        raise RoleError("User not found.", 404)
    _require_member(server_id, user_id)
    if not role_model.assign_role(user_id, role_id, server_id):
        raise RoleError("Role not found.", 404)
    if server_model.find_by_id(server_id) is None:
        role_model.remove_all_for_user_in_server(user_id, server_id)
        raise RoleError("Server not found.", 404)


def revoke_role_from_user(user_id: str, role_id: str, server_id: str):
    _require_server(server_id)
    _require_role(role_id, server_id)
    if not ObjectId.is_valid(user_id) or user_model.find_by_id(user_id) is None:
        raise RoleError("User not found.", 404)
    _require_member(server_id, user_id)
    role_model.revoke_role(user_id, role_id, server_id)


def get_user_roles(user_id: str, server_id: str, current_user_id: str) -> list[dict]:
    _require_member(server_id, current_user_id)
    if not ObjectId.is_valid(user_id) or user_model.find_by_id(user_id) is None:
        raise RoleError("User not found.", 404)
    _require_member(server_id, user_id)
    return [role_model.to_dict(r) for r in role_model.get_user_roles(user_id, server_id)]
