from datetime import datetime, timezone

from app.models import invite as invite_model
from app.models import server as server_model
from app.models import role as role_model


class InviteError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def create_invite(server_id: str, user_id: str,
                  max_uses: int = 0,
                  expires_in_hours: int | None = None) -> dict:
    server = server_model.find_by_id(server_id)
    if server is None:
        raise InviteError("Server not found.", 404)
    if not server_model.is_member(server_id, user_id):
        raise InviteError("You must be a member of this server.", 403)

    expires_at = None
    if expires_in_hours and expires_in_hours > 0:
        from datetime import timedelta
        expires_at = datetime.now(timezone.utc) + timedelta(hours=expires_in_hours)

    invite = invite_model.create(server_id, user_id, max_uses, expires_at)
    return invite_model.to_dict(invite)


def get_invite(code: str) -> dict:
    """Preview an invite — returns invite info + server name."""
    invite = invite_model.find_by_code(code)
    if invite is None:
        raise InviteError("Invite not found or invalid.", 404)

    _check_expired(invite)
    _check_used(invite)

    result = invite_model.to_dict(invite)
    server = server_model.find_by_id(str(invite["server_id"]))
    if server:
        result["server_name"] = server["name"]
        result["server_icon"] = server.get("icon")
        result["member_count"] = len(server.get("members", []))
    return result


def accept_invite(code: str, user_id: str) -> dict:
    """Accept an invite and join the server."""
    invite = invite_model.find_by_code(code)
    if invite is None:
        raise InviteError("Invite not found or invalid.", 404)

    _check_expired(invite)
    _check_used(invite)

    server_id = str(invite["server_id"])
    server = server_model.find_by_id(server_id)
    if server is None:
        raise InviteError("Server no longer exists.", 404)

    if server_model.is_member(server_id, user_id):
        raise InviteError("You are already a member of this server.", 409)

    server_model.add_member(server_id, user_id)

    # Assign default "member" role scoped to this server
    default_role = role_model.get_default_role()
    if default_role:
        role_model.assign_role(user_id, str(default_role["_id"]), server_id)

    invite_model.increment_uses(code)

    return server_model.to_dict(server_model.find_by_id(server_id))


def list_server_invites(server_id: str, user_id: str) -> list[dict]:
    server = server_model.find_by_id(server_id)
    if server is None:
        raise InviteError("Server not found.", 404)
    if not server_model.is_member(server_id, user_id):
        raise InviteError("You must be a member of this server.", 403)

    invites = invite_model.find_by_server(server_id)
    return [invite_model.to_dict(inv) for inv in invites]


def delete_invite(code: str, user_id: str):
    invite = invite_model.find_by_code(code)
    if invite is None:
        raise InviteError("Invite not found.", 404)

    # Only the invite creator or server owner can delete
    server = server_model.find_by_id(str(invite["server_id"]))
    is_creator = str(invite["created_by"]) == user_id
    is_owner = server and str(server.get("owner_id")) == user_id
    if not is_creator and not is_owner:
        raise InviteError("Only the invite creator or server owner can delete this invite.", 403)

    invite_model.delete_by_code(code)


def _check_expired(invite: dict):
    if invite.get("expires_at") and invite["expires_at"] < datetime.now(timezone.utc):
        raise InviteError("This invite has expired.", 410)


def _check_used(invite: dict):
    if invite.get("max_uses", 0) > 0 and invite.get("uses", 0) >= invite["max_uses"]:
        raise InviteError("This invite has reached its maximum uses.", 410)
