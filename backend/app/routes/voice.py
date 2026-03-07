"""
Voice routes – join / leave voice channels, list & manage participants.

All endpoints live under:
    /api/servers/<server_id>/channels/<channel_id>/voice
"""

from flask import jsonify
from flask_smorest import Blueprint

from app.middleware.auth_middleware import auth_required, permission_required
from app.services import voice_service
from app.services.voice_service import VoiceError
from app.adapters.livekit_adapter import LiveKitConnectionError
from app.schemas import (
    JoinVoiceResponseSchema,
    MessageSchema,
    MuteRequestSchema,
    ParticipantListSchema,
)

blp = Blueprint(
    "voice",
    __name__,
    url_prefix="/api/servers/<server_id>/channels/<channel_id>/voice",
    description="Voice channel operations (join, leave, participants)",
)

BEARER = [{"BearerAuth": []}]


@blp.errorhandler(LiveKitConnectionError)
def handle_livekit_error(err):
    return jsonify({"error": "Voice server is currently unavailable. Please try again later."}), 503


# ── Join ────────────────────────────────────────────────────


@blp.route("/join", methods=["POST"])
@blp.doc(security=BEARER)
@blp.response(200, JoinVoiceResponseSchema)
@blp.alt_response(400, description="Not a voice channel")
@blp.alt_response(403, description="Forbidden or channel full")
@blp.alt_response(404, description="Server or channel not found")
@auth_required
@permission_required("join_channel")
def join_voice(server_id, channel_id, current_user=None):
    """Join a voice channel and receive a media-server token."""
    try:
        result = voice_service.join_channel(
            server_id, channel_id, str(current_user["_id"])
        )
    except VoiceError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify(result), 200


# ── Leave ───────────────────────────────────────────────────


@blp.route("/leave", methods=["POST"])
@blp.doc(security=BEARER)
@blp.response(200, MessageSchema)
@blp.alt_response(404, description="Server or channel not found")
@auth_required
def leave_voice(server_id, channel_id, current_user=None):
    """Leave a voice channel."""
    try:
        voice_service.leave_channel(
            server_id, channel_id, str(current_user["_id"])
        )
    except VoiceError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"message": "Left the voice channel."}), 200


# ── Participants ────────────────────────────────────────────


@blp.route("/participants", methods=["GET"])
@blp.doc(security=BEARER)
@blp.response(200, ParticipantListSchema)
@blp.alt_response(404, description="Server or channel not found")
@auth_required
@permission_required("join_channel")
def list_participants(server_id, channel_id, current_user=None):
    """List participants currently in a voice channel."""
    try:
        participants = voice_service.get_participants(
            server_id, channel_id, str(current_user["_id"])
        )
    except VoiceError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"participants": participants}), 200


# ── Kick participant ────────────────────────────────────────


@blp.route("/participants/<identity>", methods=["DELETE"])
@blp.doc(security=BEARER)
@blp.response(200, MessageSchema)
@blp.alt_response(403, description="Missing kick_user permission")
@blp.alt_response(404, description="Server or channel not found")
@auth_required
@permission_required("kick_user")
def kick_participant(server_id, channel_id, identity, current_user=None):
    """Kick a participant from a voice channel."""
    try:
        voice_service.kick_participant(
            server_id, channel_id, str(current_user["_id"]), identity
        )
    except VoiceError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"message": f"Participant '{identity}' removed."}), 200


# ── Mute participant ───────────────────────────────────────


@blp.route("/participants/<identity>/mute", methods=["POST"])
@blp.doc(security=BEARER)
@blp.arguments(MuteRequestSchema)
@blp.response(200, MessageSchema)
@blp.alt_response(403, description="Missing mute_user permission")
@blp.alt_response(404, description="Server or channel not found")
@auth_required
@permission_required("mute_user")
def mute_participant(mute_data, server_id, channel_id, identity, current_user=None):
    """Mute or unmute a participant's track."""
    try:
        voice_service.mute_participant(
            server_id,
            channel_id,
            str(current_user["_id"]),
            target_identity=identity,
            track_sid=mute_data["track_sid"],
            muted=mute_data.get("muted", True),
        )
    except VoiceError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    action = "muted" if mute_data.get("muted", True) else "unmuted"
    return jsonify({"message": f"Track {action}."}), 200
