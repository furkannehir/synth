"""
Voice service – business logic for joining / leaving voice channels
and managing participants.

All media-server interaction goes through the :class:`MediaServerPort`
so the service never touches vendor-specific code.
"""

from app.models import channel as channel_model
from app.models import server as server_model
from app.models import user as user_model
import app.extensions as ext


class VoiceError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ── Helpers ────────────────────────────────────────────────

def _room_name(server_id: str, channel_id: str) -> str:
    """Deterministic room name for a given server/channel pair."""
    return f"synth_{server_id}_{channel_id}"


def _require_server(server_id: str) -> dict:
    server = server_model.find_by_id(server_id)
    if server is None:
        raise VoiceError("Server not found.", 404)
    return server


def _require_channel_in_server(channel_id: str, server_id: str) -> dict:
    channel = channel_model.find_by_id(channel_id)
    if channel is None:
        raise VoiceError("Channel not found.", 404)
    if str(channel["server_id"]) != server_id:
        raise VoiceError("Channel not found.", 404)
    return channel


def _require_member(server_id: str, user_id: str):
    if not server_model.is_member(server_id, user_id):
        raise VoiceError("You must be a member of this server.", 403)


def _require_voice_channel(channel: dict):
    if channel.get("type") != "voice":
        raise VoiceError("This is not a voice channel.", 400)


# ── Public API ─────────────────────────────────────────────

def join_channel(server_id: str, channel_id: str, user_id: str) -> dict:
    """
    Join a voice channel.

    Returns a dict with ``token`` (JWT for the media server) and
    ``url`` (the media server's WebSocket URL).
    """
    from flask import current_app

    _require_server(server_id)
    _require_member(server_id, user_id)
    channel = _require_channel_in_server(channel_id, server_id)
    _require_voice_channel(channel)

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
    display_name = user["username"] if user else user_id

    token = ext.media_server.generate_token(
        room_name=room,
        identity=user_id,
        name=display_name,
    )

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

    room = _room_name(server_id, channel_id)

    try:
        ext.media_server.remove_participant(room, identity=user_id)
    except Exception:
        pass  # already left or room doesn't exist — idempotent


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
    ext.media_server.remove_participant(room, identity=target_identity)


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
    ext.media_server.mute_participant(
        room, identity=target_identity, track_sid=track_sid, muted=muted
    )
