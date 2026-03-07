from app.models import role as role_model


class RoleError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def list_roles() -> list[dict]:
    roles = role_model.find_all()
    return [role_model.to_dict(r) for r in roles]


def get_role(role_id: str) -> dict:
    role = role_model.find_by_id(role_id)
    if role is None:
        raise RoleError("Role not found.", 404)
    return role_model.to_dict(role)


def create_role(name: str, permissions: list[str], is_default: bool = False) -> dict:
    if not name or len(name) < 2:
        raise RoleError("Role name must be at least 2 characters.")

    # Validate permissions
    invalid = set(permissions) - set(role_model.ALL_PERMISSIONS)
    if invalid:
        raise RoleError(f"Unknown permissions: {', '.join(sorted(invalid))}")

    if role_model.find_by_name(name):
        raise RoleError(f"Role '{name}' already exists.", 409)

    # If marking as default, unset previous default
    if is_default:
        _clear_default()

    role_id = role_model.create(name, permissions, is_default)
    return role_model.to_dict(role_model.find_by_id(role_id))


def update_role(role_id: str, updates: dict) -> dict:
    role = role_model.find_by_id(role_id)
    if role is None:
        raise RoleError("Role not found.", 404)

    # Validate permissions if being updated
    if "permissions" in updates:
        invalid = set(updates["permissions"]) - set(role_model.ALL_PERMISSIONS)
        if invalid:
            raise RoleError(f"Unknown permissions: {', '.join(sorted(invalid))}")

    # If changing name, check for duplicates
    if "name" in updates and updates["name"] != role["name"]:
        if role_model.find_by_name(updates["name"]):
            raise RoleError(f"Role '{updates['name']}' already exists.", 409)

    # If marking as default, unset previous default
    if updates.get("is_default"):
        _clear_default()

    updated = role_model.update(role_id, updates)
    return role_model.to_dict(updated)


def delete_role(role_id: str):
    role = role_model.find_by_id(role_id)
    if role is None:
        raise RoleError("Role not found.", 404)
    if role.get("name") in ("admin", "moderator", "member"):
        raise RoleError("Cannot delete built-in roles.", 403)
    role_model.delete(role_id)


def assign_role_to_user(user_id: str, role_id: str, server_id: str):
    from app.models import user as user_model
    if user_model.find_by_id(user_id) is None:
        raise RoleError("User not found.", 404)
    if role_model.find_by_id(role_id) is None:
        raise RoleError("Role not found.", 404)
    role_model.assign_role(user_id, role_id, server_id)


def revoke_role_from_user(user_id: str, role_id: str, server_id: str):
    from app.models import user as user_model
    if user_model.find_by_id(user_id) is None:
        raise RoleError("User not found.", 404)
    role_model.revoke_role(user_id, role_id, server_id)


def get_user_roles(user_id: str, server_id: str | None = None) -> list[dict]:
    from app.models import user as user_model
    if user_model.find_by_id(user_id) is None:
        raise RoleError("User not found.", 404)
    roles = role_model.get_user_roles(user_id, server_id)
    return [role_model.to_dict(r) for r in roles]


def _clear_default():
    """Unset is_default on all roles."""
    role_model._roles().update_many({}, {"$set": {"is_default": False}})
