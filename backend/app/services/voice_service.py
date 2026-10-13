"""
Voice service – business logic for joining / leaving voice channels
and managing participants.

All media-server interaction goes through the :class:`MediaServerPort`
so the service never touches vendor-specific code.
"""

from app.models import channel as channel_model
from app.models import server as server_model
from app.models import user as user_model
from app.models import voice_session as session_model
from app.voice_access import allowed, remove_now
from bson import ObjectId
import app.extensions as ext


class VoiceError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ── Helpers ────────────────────────────────────────────────

def _room_name(server_id: str, channel_id: str) -> str:
    """Deterministic room name for a given server/channel pair."""
    return f"synth_{ObjectId(server_id)}_{ObjectId(channel_id)}"


def _require_server(server_id: str) -> dict:
    if not ObjectId.is_valid(server_id):
        raise VoiceError("Server not found.", 404)
    server = server_model.find_by_id(server_id)
    if server is None:
        raise VoiceError("Server not found.", 404)
    return server


def _require_channel_in_server(channel_id: str, server_id: str) -> dict:
    if not ObjectId.is_valid(channel_id):
        raise VoiceError("Channel not found.", 404)
    channel = channel_model.find_by_id(channel_id)
    if channel is None:
        raise VoiceError("Channel not found.", 404)
    if channel["server_id"] != ObjectId(server_id):
        raise VoiceError("Channel not found.", 404)
    return channel


def _require_member(server_id: str, user_id: str):
    if not server_model.is_member(server_id, user_id):
        raise VoiceError("You must be a member of this server.", 403)


def _require_voice_channel(channel: dict):
    if channel.get("type") != "voice":
        raise VoiceError("This is not a voice channel.", 400)


# ── Public API ─────────────────────────────────────────────

def join_channel(server_id: str, channel_id: str, user_id: str, session_version: int | None = None,
                 desktop_session=None) -> dict:
    """
    Join a voice channel.

    Returns a dict with ``token`` (JWT for the media server) and
    ``url`` (the media server's WebSocket URL).
    """
    from flask import current_app

    server = _require_server(server_id)
    _require_member(server_id, user_id)
    channel = _require_channel_in_server(channel_id, server_id)
    _require_voice_channel(channel)

    server_id, channel_id = str(server["_id"]), str(channel["_id"])
    if ext.media_server is None:
        raise VoiceError("Voice server is currently unavailable.", 503)

    room = _room_name(server_id, channel_id)

    # Enforce user_limit (0 = unlimited)
    user_limit = channel.get("user_limit", 0)
    if user_limit > 0:
        participants = ext.media_server.list_participants(room)
        if len(participants) >= user_limit:
            raise VoiceError(
                f"Channel is full ({user_limit}/{user_limit}).", 403
            )

    # Ensure the room exists on the media server
    ext.media_server.create_room(
        room,
        empty_timeout=300,
        max_participants=user_limit,
    )

    # Resolve display name for the participant
    user = user_model.find_by_id(user_id)
    if user is None:
        raise VoiceError("User not found.", 401)
    display_name = user["username"]

    version = session_version if session_version is not None else user.get("session_version", 0)
    grant, previous = session_model.issue(server_id, channel_id, user_id, version, room, desktop_session)
    if previous:
        session_model.queue_removal(previous)
        remove_now([previous])
    try:
        token = ext.media_server.generate_token(
            room_name=room, identity=grant["identity"], name=display_name, ttl_seconds=60,
        )
        current = ext.mongo.db.voice_sessions.find_one({"_id": grant["_id"]})
        if (current is None or current["identity"] != grant["identity"] or not allowed(
                current, user_model.find_by_id(user_id), server_model.find_by_id(server_id),
                channel_model.find_by_id(channel_id))):
            raise VoiceError("Voice access was revoked. Please join again.", 403)
    except Exception:
        remove_now(session_model.revoke({"_id": grant["_id"], "identity": grant["identity"]}))
        raise

    return {
        "token": token,
        "url": current_app.config["LIVEKIT_URL"],
        "room": room,
    }


def leave_channel(server_id: str, channel_id: str, user_id: str) -> None:
    """Remove yourself from a voice channel."""
    _require_server(server_id)
    _require_member(server_id, user_id)
    channel = _require_channel_in_server(channel_id, server_id)
    _require_voice_channel(channel)

    remove_now(session_model.revoke({"channel_id": channel["_id"], "user_id": ObjectId(user_id)}))


def get_participants(
    server_id: str, channel_id: str, user_id: str
) -> list[dict]:
    """List everyone currently in a voice channel."""
    _require_server(server_id)
    _require_member(server_id, user_id)
    channel = _require_channel_in_server(channel_id, server_id)
    _require_voice_channel(channel)

    room = _room_name(server_id, channel_id)

    try:
        participants = ext.media_server.list_participants(room)
    except Exception:
        return []  # room may not exist yet

    return [
        {
            "identity": p.identity,
            "name": p.name,
            "sid": p.sid,
            "state": p.state,
            "tracks": [
                {
                    "sid": t.sid,
                    "name": t.name,
                    "kind": t.kind,
                    "muted": t.muted,
                }
                for t in p.tracks
            ],
        }
        for p in participants
    ]


def kick_participant(
    server_id: str,
    channel_id: str,
    user_id: str,
    target_identity: str,
) -> None:
    """Forcibly remove another user from a voice channel."""
    _require_server(server_id)
    _require_member(server_id, user_id)
    channel = _require_channel_in_server(channel_id, server_id)
    _require_voice_channel(channel)

    room = _room_name(server_id, channel_id)
    target_identity = _target_identity(room, target_identity)
    grants = session_model.revoke({"room": room, "identity": target_identity})
    if not grants:
        grant = {"room": room, "identity": target_identity, "server_id": channel["server_id"],
                 "channel_id": channel["_id"]}
        session_model.queue_removal(grant)
        grants = [grant]
    remove_now(grants)


def mute_participant(
    server_id: str,
    channel_id: str,
    user_id: str,
    target_identity: str,
    track_sid: str,
    muted: bool = True,
) -> None:
    """Server-side mute / unmute a participant's track."""
    _require_server(server_id)
    _require_member(server_id, user_id)
    channel = _require_channel_in_server(channel_id, server_id)
    _require_voice_channel(channel)

    room = _room_name(server_id, channel_id)
    target_identity = _target_identity(room, target_identity)
    ext.media_server.mute_participant(
        room, identity=target_identity, track_sid=track_sid, muted=muted
    )


def _target_identity(room: str, identity: str) -> str:
    if ObjectId.is_valid(identity):
        grant = ext.mongo.db.voice_sessions.find_one({"room": room, "user_id": ObjectId(identity), "revoked": False})
        if grant:
            return grant["identity"]
    return identity


def revoke_user_sessions(user_id: str):
    user = user_model.find_by_id(user_id)
    version = user.get("session_version", 0) if user else 0
    remove_now(session_model.revoke({"user_id": ObjectId(user_id), "session_version": {"$lt": version}}))


def revoke_server_sessions(server_id: str, user_id: str | None = None):
    query = {"server_id": ObjectId(server_id)}
    if user_id is not None:
        query["user_id"] = ObjectId(user_id)
    remove_now(session_model.revoke(query))


def revoke_channel_sessions(channel_id: str):
    remove_now(session_model.revoke({"channel_id": ObjectId(channel_id)}))
