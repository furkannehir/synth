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

    now = _utc_now()
    expires_at = None
    if expires_in_hours and expires_in_hours > 0:
        from datetime import timedelta
        expires_at = now + timedelta(hours=expires_in_hours)

    # Keep only one active invite per creator/server by expiring prior active links.
    existing_invites = invite_model.find_by_server_and_creator(server_id, user_id)
    for existing in existing_invites:
        if _is_invite_active(existing, now):
            invite_model.expire_by_code(existing["code"], now)

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

    now = _utc_now()
    invites = invite_model.find_by_server(server_id)
    active_invites = [inv for inv in invites if _is_invite_active(inv, now)]
    return [invite_model.to_dict(inv) for inv in active_invites]


def sweep_stale_invites() -> int:
    """Delete invites that are expired or exhausted."""
    return invite_model.delete_stale(_utc_now())


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
    if _is_invite_expired(invite):
        raise InviteError("This invite has expired.", 410)


def _check_used(invite: dict):
    if _is_invite_exhausted(invite):
        raise InviteError("This invite has reached its maximum uses.", 410)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _is_invite_expired(invite: dict, now: datetime | None = None) -> bool:
    expires_at = _as_utc_aware(invite.get("expires_at"))
    if expires_at is None:
        return False
    current = now or _utc_now()
    return expires_at <= current


def _is_invite_exhausted(invite: dict) -> bool:
    max_uses = int(invite.get("max_uses", 0) or 0)
    uses = int(invite.get("uses", 0) or 0)
    return max_uses > 0 and uses >= max_uses


def _is_invite_active(invite: dict, now: datetime | None = None) -> bool:
    return not _is_invite_expired(invite, now) and not _is_invite_exhausted(invite)
