"""Revocable desktop sessions with hashed, rotating refresh credentials."""
import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from flask import current_app
from pymongo import ReturnDocument

from app.extensions import mongo
from app.models import user as user_model

TOKEN_PATTERN = re.compile(r"^([0-9a-f]{32})\.([A-Za-z0-9_-]{43})$")


class DesktopSessionError(Exception):
    pass


def ensure_indexes():
    mongo.db.desktop_sessions.create_index("absolute_expires_at", expireAfterSeconds=0)
    mongo.db.desktop_sessions.create_index("user_id")


def _hash(token):
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def _session_id(token):
    match = TOKEN_PATTERN.fullmatch(token) if isinstance(token, str) else None
    if not match:
        raise DesktopSessionError("Session expired. Please sign in again.")
    return match[1]


def _now():
    return datetime.now(timezone.utc)


def _utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _check(session):
    now = _now()
    if (not session or session.get("revoked") or _utc(session["expires_at"]) <= now
            or _utc(session["absolute_expires_at"]) <= now):
        raise DesktopSessionError("Session expired. Please sign in again.")
    user = user_model.find_by_id(str(session["user_id"]))
    if user is None or user.get("session_version", 0) != session["session_version"]:
        raise DesktopSessionError("Session expired. Please sign in again.")
    return user


def create(user_id, version):
    sid = secrets.token_hex(16)
    refresh = f"{sid}.{secrets.token_urlsafe(32)}"
    revocation = f"{sid}.{secrets.token_urlsafe(32)}"
    now = _now()
    absolute = now + timedelta(days=current_app.config.get("DESKTOP_SESSION_MAX_DAYS", 90))
    session = {
        "_id": sid, "user_id": ObjectId(user_id), "session_version": version,
        "refresh_hash": _hash(refresh), "revocation_hash": _hash(revocation),
        "used_hashes": [], "revoked": False, "created_at": now,
        "absolute_expires_at": absolute,
        "expires_at": min(absolute, now + timedelta(days=current_app.config.get("DESKTOP_SESSION_IDLE_DAYS", 30))),
    }
    _check(session)
    mongo.db.desktop_sessions.insert_one(session)
    return session, refresh, revocation


def rotate(refresh, next_refresh):
    sid = _session_id(refresh)
    if _session_id(next_refresh) != sid or refresh == next_refresh:
        raise DesktopSessionError("Invalid session renewal.")
    col = mongo.db.desktop_sessions
    session = col.find_one({"_id": sid})
    _check(session)
    old_hash, new_hash = _hash(refresh), _hash(next_refresh)
    now = _now()
    # The client persists the replacement before requesting renewal. Retrying
    # the exact pair recovers a lost response or a crash without a second rotate.
    if session.get("rotation_from") == old_hash and session["refresh_hash"] == new_hash:
        return session
    if new_hash in session.get("used_hashes", []):
        raise DesktopSessionError("Invalid session renewal.")
    updated = col.find_one_and_update({
        "_id": sid, "revoked": False, "refresh_hash": old_hash,
        "expires_at": {"$gt": now}, "absolute_expires_at": {"$gt": now},
    }, {
        "$set": {"refresh_hash": new_hash, "rotation_from": old_hash,
                 "expires_at": min(_utc(session["absolute_expires_at"]), now + timedelta(
                     days=current_app.config.get("DESKTOP_SESSION_IDLE_DAYS", 30)))},
        "$push": {"used_hashes": {"$each": [old_hash], "$slice": -32}},
    }, return_document=ReturnDocument.AFTER)
    if updated is not None:
        _check(updated)
        return updated
    # Another worker can have committed the identical request while we waited.
    session = col.find_one({"_id": sid})
    _check(session)
    if session.get("rotation_from") == old_hash and session["refresh_hash"] == new_hash:
        return session
    if old_hash in session.get("used_hashes", []):
        col.update_one({"_id": sid}, {"$set": {"revoked": True}})
    raise DesktopSessionError("Session expired. Please sign in again.")


def revoke(credential):
    sid = _session_id(credential)
    # A separate stable secret allows queued offline logout even after rotation.
    mongo.db.desktop_sessions.update_one(
        {"_id": sid, "revocation_hash": _hash(credential)}, {"$set": {"revoked": True}},
    )


def is_active(sid, user_id, version):
    if not isinstance(sid, str) or not re.fullmatch(r"[0-9a-f]{32}", sid):
        return False
    now = _now()
    return mongo.db.desktop_sessions.find_one({
        "_id": sid, "user_id": ObjectId(user_id), "session_version": version,
        "revoked": False, "expires_at": {"$gt": now}, "absolute_expires_at": {"$gt": now},
    }, {"_id": 1}) is not None
