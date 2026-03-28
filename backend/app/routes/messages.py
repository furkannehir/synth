import json
from flask import jsonify, request, Response, stream_with_context
from flask_smorest import Blueprint

from app.middleware.auth_middleware import auth_required
from app.models import role as role_model
from app.models import server as server_model
from app.models import channel as channel_model
from app.services.message_service import MessageError
from app.services import message_service
from app.extensions import channel_event_bus
from app.schemas import (
    SendMessageSchema, EditMessageSchema,
    ChatMessageSchema, MessageResponseSchema, MessageListSchema, MessageSchema,
)

blp = Blueprint(
    "messages", __name__,
    url_prefix="/api/channels/<channel_id>/messages",
    description="Messages — text channel messaging",
)

BEARER = [{"BearerAuth": []}]


# ── GET /api/channels/<channel_id>/messages ─────────────────
@blp.route("", methods=["GET"])
@blp.doc(security=BEARER)
@blp.response(200, MessageListSchema)
@blp.alt_response(403, description="Not a member / not a text channel")
@blp.alt_response(404, description="Channel not found")
@auth_required
def list_messages(channel_id, current_user=None):
    """Fetch paginated message history. Pass ?before=<message_id> for older pages."""
    before = request.args.get("before")
    try:
        msgs = message_service.list_messages(
            channel_id=channel_id,
            user_id=str(current_user["_id"]),
            before=before,
        )
    except MessageError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"messages": msgs}), 200


# ── POST /api/channels/<channel_id>/messages ────────────────
@blp.route("", methods=["POST"])
@blp.doc(security=BEARER)
@blp.arguments(SendMessageSchema)
@blp.response(201, MessageResponseSchema)
@blp.alt_response(400, description="Validation error")
@blp.alt_response(403, description="Not a member / not a text channel")
@auth_required
def send_message(data, channel_id, current_user=None):
    """Send a message to a text channel."""
    try:
        msg = message_service.send_message(
            channel_id=channel_id,
            user_id=str(current_user["_id"]),
            content=data["content"],
        )
    except MessageError as exc:
        return jsonify({"error": exc.message}), exc.status_code

    # Push to all SSE subscribers for this channel
    channel_event_bus.publish(channel_id, {"type": "message", "data": msg})

    return jsonify({"message": msg}), 201


# ── PATCH /api/channels/<channel_id>/messages/<message_id> ──
@blp.route("/<message_id>", methods=["PATCH"])
@blp.doc(security=BEARER)
@blp.arguments(EditMessageSchema)
@blp.response(200, MessageResponseSchema)
@blp.alt_response(403, description="Not the author")
@blp.alt_response(404, description="Message not found")
@auth_required
def edit_message(data, channel_id, message_id, current_user=None):
    """Edit your own message."""
    try:
        msg = message_service.edit_message(
            message_id=message_id,
            channel_id=channel_id,
            user_id=str(current_user["_id"]),
            content=data["content"],
        )
    except MessageError as exc:
        return jsonify({"error": exc.message}), exc.status_code

    # Notify SSE subscribers of the edit
    channel_event_bus.publish(channel_id, {"type": "message_edit", "data": msg})

    return jsonify({"message": msg}), 200


# ── DELETE /api/channels/<channel_id>/messages/<message_id> ─
@blp.route("/<message_id>", methods=["DELETE"])
@blp.doc(security=BEARER)
@blp.response(200, MessageSchema)
@blp.alt_response(403, description="No permission to delete")
@blp.alt_response(404, description="Message not found")
@auth_required
def delete_message(channel_id, message_id, current_user=None):
    """Delete a message (own messages, or any if manage_messages permission)."""
    user_id = str(current_user["_id"])

    # Resolve server_id from channel to check permissions
    channel = channel_model.find_by_id(channel_id)
    user_permissions: set = set()
    if channel:
        server_id = str(channel["server_id"])
        server = server_model.find_by_id(server_id)
        if server and str(server.get("owner_id")) == user_id:
            user_permissions.add("manage_messages")
        else:
            user_permissions = role_model.get_user_permissions(user_id, server_id)

    try:
        message_service.delete_message(
            message_id=message_id,
            channel_id=channel_id,
            user_id=user_id,
            user_permissions=user_permissions,
        )
    except MessageError as exc:
        return jsonify({"error": exc.message}), exc.status_code

    # Notify SSE subscribers of the deletion
    channel_event_bus.publish(channel_id, {
        "type": "message_delete",
        "data": {"id": message_id},
    })

    return jsonify({"message": "Message deleted."}), 200


# ── GET /api/channels/<channel_id>/messages/events ──────────
# (SSE endpoint — auth via ?token= query param since EventSource
#  cannot set Authorization headers)
@blp.route("/events", methods=["GET"])
@blp.doc(security=BEARER)
@auth_required
def channel_events(channel_id, current_user=None):
    """
    Server-Sent Events stream for a text channel.
    Connect with EventSource('/api/channels/<id>/messages/events?token=<jwt>').
    """
    user_id = str(current_user["_id"])

    # Validate the user is a member and the channel is text-type
    try:
        message_service.list_messages(channel_id, user_id, before=None)
        # list_messages does 0 rows but validates membership & type
    except MessageError as exc:
        # Return a plain 403 — EventSource ignores non-2xx gracefully
        return jsonify({"error": exc.message}), exc.status_code

    channel_event_bus.subscribe(channel_id)

    def generate():
        try:
            # Send a keep-alive comment immediately so the browser knows the stream is open
            yield ": connected\n\n"
            while True:
                events = channel_event_bus.wait_for_event(channel_id, timeout=25.0)
                if not events:
                    # Heartbeat to prevent proxy timeouts
                    yield ": heartbeat\n\n"
                    continue
                for event in events:
                    yield f"data: {json.dumps(event)}\n\n"
        finally:
            channel_event_bus.unsubscribe(channel_id)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
        },
    )
