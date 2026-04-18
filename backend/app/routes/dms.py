import json
from flask import jsonify, request, Response, stream_with_context
from flask_smorest import Blueprint

from app.middleware.auth_middleware import auth_required
from app.services.dm_service import DMError
from app.services import dm_service
from app.models import direct_message as dm_model
from app.extensions import dm_event_bus
from app.schemas import (
    SendDMSchema, EditDMSchema,
    DMSchema, DMResponseSchema, DMListSchema, MessageSchema,
    ConversationListSchema,
)

blp = Blueprint(
    "dms", __name__,
    url_prefix="/api/dms",
    description="Direct Messages — 1-on-1 messaging between friends",
)

BEARER = [{"BearerAuth": []}]


# ── GET /api/dms/conversations ──────────────────────────────
@blp.route("/conversations", methods=["GET"])
@blp.doc(security=BEARER)
@blp.response(200, ConversationListSchema)
@auth_required
def list_conversations(current_user=None):
    """List recent conversations."""
    offset = int(request.args.get("offset", 0))
    limit = int(request.args.get("limit", 20))
    
    cvs = dm_service.get_conversations(str(current_user["_id"]), offset, limit)
    return jsonify({"conversations": cvs}), 200


# ── GET /api/dms/unread_count ───────────────────────────────
@blp.route("/unread_count", methods=["GET"])
@blp.doc(security=BEARER)
@auth_required
def get_unread_count(current_user=None):
    count = dm_service.get_total_unread_count(str(current_user["_id"]))
    return jsonify({"unread_count": count}), 200


# ── GET /api/dms/<friend_id>/messages ──────────────────────
@blp.route("/<friend_id>/messages", methods=["GET"])
@blp.doc(security=BEARER)
@blp.response(200, DMListSchema)
@blp.alt_response(403, description="Not friends")
@auth_required
def list_dms(friend_id, current_user=None):
    """Fetch paginated DM history. Pass ?before=<dm_id> for older pages."""
    before = request.args.get("before")
    try:
        msgs = dm_service.list_dms(
            user_id=str(current_user["_id"]),
            friend_id=friend_id,
            before=before,
        )
    except DMError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"messages": msgs}), 200


# ── POST /api/dms/<friend_id>/messages ─────────────────────
@blp.route("/<friend_id>/messages", methods=["POST"])
@blp.doc(security=BEARER)
@blp.arguments(SendDMSchema)
@blp.response(201, DMResponseSchema)
@blp.alt_response(400, description="Validation error")
@blp.alt_response(403, description="Not friends")
@auth_required
def send_dm(data, friend_id, current_user=None):
    """Send a direct message to a friend."""
    try:
        msg = dm_service.send_dm(
            sender_id=str(current_user["_id"]),
            recipient_id=friend_id,
            content=data["content"],
        )
    except DMError as exc:
        return jsonify({"error": exc.message}), exc.status_code

    # Push to SSE subscribers
    conv_key = dm_model.make_conversation_key(str(current_user["_id"]), friend_id)
    dm_event_bus.publish(conv_key, {"type": "dm", "data": msg})

    return jsonify({"message": msg}), 201


# ── PATCH /api/dms/<friend_id>/messages/<dm_id> ────────────
@blp.route("/<friend_id>/messages/<dm_id>", methods=["PATCH"])
@blp.doc(security=BEARER)
@blp.arguments(EditDMSchema)
@blp.response(200, DMResponseSchema)
@blp.alt_response(403, description="Not the sender")
@blp.alt_response(404, description="Message not found")
@auth_required
def edit_dm(data, friend_id, dm_id, current_user=None):
    """Edit a direct message."""
    try:
        msg = dm_service.edit_dm(
            dm_id=dm_id,
            user_id=str(current_user["_id"]),
            content=data["content"],
        )
    except DMError as exc:
        return jsonify({"error": exc.message}), exc.status_code

    conv_key = dm_model.make_conversation_key(str(current_user["_id"]), friend_id)
    dm_event_bus.publish(conv_key, {"type": "dm_edit", "data": msg})

    return jsonify({"message": msg}), 200


# ── DELETE /api/dms/<friend_id>/messages/<dm_id> ───────────
@blp.route("/<friend_id>/messages/<dm_id>", methods=["DELETE"])
@blp.doc(security=BEARER)
@blp.response(200, MessageSchema)
@blp.alt_response(403, description="Not the sender")
@blp.alt_response(404, description="Message not found")
@auth_required
def delete_dm(friend_id, dm_id, current_user=None):
    """Delete a direct message."""
    try:
        dm_service.delete_dm(
            dm_id=dm_id,
            user_id=str(current_user["_id"]),
        )
    except DMError as exc:
        return jsonify({"error": exc.message}), exc.status_code

    conv_key = dm_model.make_conversation_key(str(current_user["_id"]), friend_id)
    dm_event_bus.publish(conv_key, {"type": "dm_delete", "data": {"id": dm_id}})

    return jsonify({"message": "Message deleted."}), 200


# ── POST /api/dms/<friend_id>/messages/read ────────────────
@blp.route("/<friend_id>/messages/read", methods=["POST"])
@blp.doc(security=BEARER)
@blp.response(200, MessageSchema)
@auth_required
def read_dms(friend_id, current_user=None):
    """Mark all unread DMs from a friend as read."""
    user_id = str(current_user["_id"])
    count = dm_service.mark_as_read(user_id, friend_id)
    
    if count > 0:
        conv_key = dm_model.make_conversation_key(user_id, friend_id)
        dm_event_bus.publish(conv_key, {"type": "dm_read", "data": {"by": user_id, "friend_id": friend_id}})
        
    return jsonify({"message": "Messages marked as read."}), 200


# ── GET /api/dms/<friend_id>/messages/events ───────────────
@blp.route("/<friend_id>/messages/events", methods=["GET"])
@blp.doc(security=BEARER)
@auth_required
def dm_events(friend_id, current_user=None):
    """
    SSE stream for a DM conversation.
    Connect with EventSource('/api/dms/<friend_id>/messages/events?token=<jwt>').
    """
    user_id = str(current_user["_id"])

    # Validate friendship
    from app.models import user as user_model
    if not user_model.are_friends(user_id, friend_id):
        return jsonify({"error": "You can only message friends."}), 403

    conv_key = dm_model.make_conversation_key(user_id, friend_id)
    q = dm_event_bus.subscribe(conv_key)

    def generate():
        import queue
        try:
            yield ": connected\n\n"
            while True:
                try:
                    event = q.get(timeout=25.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except queue.Empty:
                    yield ": heartbeat\n\n"
        finally:
            dm_event_bus.unsubscribe(conv_key, q)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
