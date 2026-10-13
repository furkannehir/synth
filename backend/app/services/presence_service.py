from datetime import datetime, timezone, timedelta
from uuid import UUID

from bson import ObjectId
from pymongo import ReturnDocument

from app.models import user as user_model

# Users who haven't sent a heartbeat within this window are considered offline
HEARTBEAT_TIMEOUT = timedelta(seconds=60)
MAX_PRESENCE_SESSIONS = 256


class PresenceError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def normalize_session_id(session_id):
    if session_id is None:
        return None  # older clients have one presence slot per JWT
    if not isinstance(session_id, str) or len(session_id) > 36:
        raise PresenceError("Invalid presence session ID.")
    try:
        return str(UUID(session_id))
    except ValueError as exc:
        raise PresenceError("Invalid presence session ID.") from exc


def _utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _change_presence(user_id, online, claims, session_id):
    """CAS the account's leases so workers cannot undo one another's updates."""
    session_id = normalize_session_id(session_id)
    lease_id = f"{claims['jti']}:{session_id or 'legacy'}"
    version = claims.get("session_version", 0)
    expires = datetime.fromtimestamp(claims["exp"], timezone.utc)
    col = user_model.get_collection()
    for _ in range(20):
        now = datetime.now(timezone.utc)
        user = user_model.find_by_id(user_id)
        if user is None or user.get("session_version", 0) != version or expires <= now:
            raise PresenceError("Session expired. Please sign in again.", 401)
        leases = [dict(lease) for lease in user.get("presence_sessions", [])
                  if _utc(lease["expires_at"]) > now and lease["session_version"] == version]
        lease = next((lease for lease in leases if lease["id"] == lease_id), None)
        # A lease is permanently closed until JWT expiry. This also handles
        # offline arriving before the initial or an already-authenticated beat.
        if online and session_id is not None and lease and lease["closed"]:
            return user
        if lease is None:
            if len(leases) >= MAX_PRESENCE_SESSIONS:
                raise PresenceError("Too many presence sessions. Try again later.", 429)
            lease = {"id": lease_id, "expires_at": expires, "session_version": version}
            leases.append(lease)
        lease.update(closed=not online, last_seen=now)
        active = [lease for lease in leases if not lease["closed"]
                  and _utc(lease["last_seen"]) > now - HEARTBEAT_TIMEOUT]
        revision = user.get("presence_revision", 0)
        query = {"_id": ObjectId(user_id), "presence_revision": revision}
        if "presence_revision" not in user:
            query["presence_revision"] = {"$exists": False}
        if "session_version" in user:
            query["session_version"] = version
        else:
            query["session_version"] = {"$exists": False}
        updated = col.find_one_and_update(query, {
            "$set": {"presence_sessions": leases, "is_online": bool(active),
                     "last_seen": max(_utc(lease["last_seen"]) for lease in active) if active else now},
            "$inc": {"presence_revision": 1},
        }, return_document=ReturnDocument.AFTER)
        if updated is not None:
            return updated
    raise PresenceError("Presence changed concurrently. Please retry.", 503)


def heartbeat(user_id: str, claims: dict, session_id=None) -> dict:
    return user_model.to_dict(_change_presence(user_id, True, claims, session_id))


def go_offline(user_id: str, claims: dict, session_id=None) -> None:
    _change_presence(user_id, False, claims, session_id)


def sweep_stale_users() -> int:
    """
    Mark users offline if their last_seen is older than HEARTBEAT_TIMEOUT.
    Returns the number of users marked offline.
    """
    cutoff = datetime.now(timezone.utc) - HEARTBEAT_TIMEOUT
    col = user_model.get_collection()
    result = col.update_many(
        {"is_online": True, "last_seen": {"$lt": cutoff}},
        {"$set": {"is_online": False}},
    )
    return result.modified_count
