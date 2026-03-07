from flask import jsonify
from flask_smorest import Blueprint

from app.middleware.auth_middleware import auth_required, permission_required
from app.services.channel_service import ChannelError
from app.services import channel_service
from app.schemas import (
    CreateChannelSchema, UpdateChannelSchema,
    ChannelResponseSchema, ChannelListSchema, MessageSchema,
)

blp = Blueprint(
    "channels", __name__,
    url_prefix="/api/servers/<server_id>/channels",
    description="Channels — voice/text channels nested under servers",
)

BEARER = [{"BearerAuth": []}]


# ── GET /api/servers/<server_id>/channels ──────────────────
@blp.route("", methods=["GET"])
@blp.doc(security=BEARER)
@blp.response(200, ChannelListSchema)
@blp.alt_response(404, description="Server not found")
@auth_required
def list_channels(server_id, current_user=None):
    try:
        channels = channel_service.list_channels(server_id, str(current_user["_id"]))
    except ChannelError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"channels": channels}), 200


# ── POST /api/servers/<server_id>/channels ─────────────────
@blp.route("", methods=["POST"])
@blp.doc(security=BEARER)
@blp.arguments(CreateChannelSchema)
@blp.response(201, ChannelResponseSchema)
@blp.alt_response(400, description="Validation error")
@blp.alt_response(409, description="Duplicate channel name")
@auth_required
@permission_required("manage_channels")
def create_channel(data, server_id, current_user=None):
    try:
        channel = channel_service.create_channel(
            server_id=server_id,
            user_id=str(current_user["_id"]),
            name=data.get("name", ""),
            channel_type=data.get("type", "voice"),
            position=data.get("position"),
            user_limit=data.get("user_limit", 0),
        )
    except ChannelError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"channel": channel}), 201


# ── GET /api/servers/<server_id>/channels/<channel_id> ─────
@blp.route("/<channel_id>", methods=["GET"])
@blp.doc(security=BEARER)
@blp.response(200, ChannelResponseSchema)
@blp.alt_response(404, description="Channel not found")
@auth_required
def get_channel(server_id, channel_id, current_user=None):
    try:
        channel = channel_service.get_channel(channel_id, server_id, str(current_user["_id"]))
    except ChannelError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"channel": channel}), 200


# ── PUT /api/servers/<server_id>/channels/<channel_id> ─────
@blp.route("/<channel_id>", methods=["PUT"])
@blp.doc(security=BEARER)
@blp.arguments(UpdateChannelSchema)
@blp.response(200, ChannelResponseSchema)
@blp.alt_response(403, description="Insufficient permissions")
@blp.alt_response(409, description="Duplicate channel name")
@auth_required
@permission_required("manage_channels")
def update_channel(data, server_id, channel_id, current_user=None):
    try:
        channel = channel_service.update_channel(
            channel_id=channel_id,
            server_id=server_id,
            user_id=str(current_user["_id"]),
            updates=data,
        )
    except ChannelError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"channel": channel}), 200


# ── DELETE /api/servers/<server_id>/channels/<channel_id> ──
@blp.route("/<channel_id>", methods=["DELETE"])
@blp.doc(security=BEARER)
@blp.response(200, MessageSchema)
@blp.alt_response(403, description="Cannot delete default channel or insufficient permissions")
@auth_required
@permission_required("manage_channels")
def delete_channel(server_id, channel_id, current_user=None):
    try:
        channel_service.delete_channel(
            channel_id=channel_id,
            server_id=server_id,
            user_id=str(current_user["_id"]),
        )
    except ChannelError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"message": "Channel deleted."}), 200
