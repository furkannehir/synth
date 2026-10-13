from bson import ObjectId
from flask import jsonify, request, Response, stream_with_context
from flask_smorest import Blueprint
from flask_jwt_extended import get_jwt

from app.middleware.auth_middleware import auth_required, ensure_session, SessionError
from app.services.dm_service import DMError
from app.services import dm_service
from app.models import direct_message as dm_model
from app.extensions import dm_event_bus
from app.schemas import (
    SendDMSchema, EditDMSchema,
    DMResponseSchema, DMListSchema, MessageSchema,
    ConversationListSchema, ConversationQuerySchema,
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
@blp.alt_response(422, description="Invalid pagination parameters")
@auth_required
@blp.arguments(ConversationQuerySchema, location="query")
def list_conversations(query, current_user=None):
    """List recent conversations."""
    cvs = dm_service.get_conversations(str(current_user["_id"]), query["offset"], query["limit"])
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
@blp.alt_response(400, description="Invalid friend ID or pagination cursor")
@blp.alt_response(403, description="Not friends")
@blp.alt_response(404, description="Pagination cursor not found in this conversation")
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
            friend_id=friend_id,
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
            friend_id=friend_id,
        )
    except DMError as exc:
        return jsonify({"error": exc.message}), exc.status_code

    conv_key = dm_model.make_conversation_key(str(current_user["_id"]), friend_id)
    dm_event_bus.publish(conv_key, {"type": "dm_delete", "data": {"id": str(ObjectId(dm_id))}})

    return jsonify({"message": "Message deleted."}), 200


# ── POST /api/dms/<friend_id>/messages/read ────────────────
@blp.route("/<friend_id>/messages/read", methods=["POST"])
@blp.doc(security=BEARER)
@blp.response(200, MessageSchema)
@blp.alt_response(400, description="Invalid friend ID")
@auth_required
def read_dms(friend_id, current_user=None):
    """Mark all unread DMs from a friend as read."""
    user_id = str(current_user["_id"])
    try:
        receipt = dm_service.mark_as_read(user_id, friend_id)
    except DMError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    
    if receipt["count"] > 0:
        conv_key = dm_model.make_conversation_key(user_id, friend_id)
        if receipt["message_ids"] is None:
            dm_event_bus.publish(conv_key, {"type": "resync", "data": {}})
        else:
            dm_event_bus.publish(conv_key, {"type": "dm_read", "data": {
                "by": user_id, "friend_id": str(ObjectId(friend_id)),
                "message_ids": receipt["message_ids"],
            }})
        
    return jsonify({"message": "Messages marked as read."}), 200


# ── GET /api/dms/<friend_id>/messages/events ───────────────
@blp.route("/<friend_id>/messages/events", methods=["GET"])
@blp.doc(security=BEARER)
@blp.alt_response(400, description="Invalid friend ID")
@blp.alt_response(403, description="Not friends")
@auth_required
def dm_events(friend_id, current_user=None):
    """
    SSE stream for a DM conversation.
    Connect with EventSource('/api/dms/<friend_id>/messages/events?token=<jwt>').
    """
    user_id = str(current_user["_id"])
    claims = get_jwt().copy()

    try:
        conv_key = dm_service.validate_conversation_access(user_id, friend_id)
    except DMError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    q = dm_event_bus.subscribe(conv_key, request.headers.get("Last-Event-ID"))

    def generate():
        import queue
        try:
            ensure_session(user_id, claims)
            dm_service.validate_conversation_access(user_id, friend_id)
            yield f'id: {q.initial_revision}\ndata: {{"type":"connected","data":{{"revision":{q.connected_revision}}}}}\n\n'
            while True:
                try:
                    event = q.get(timeout=25.0)
                    payload = dm_service.resolve_event(user_id, friend_id, event.event)
                    ensure_session(user_id, claims)
                    dm_service.validate_conversation_access(user_id, friend_id)
                    yield event.sse(payload)
                except queue.Empty:
                    ensure_session(user_id, claims)
                    dm_service.validate_conversation_access(user_id, friend_id)
                    yield ": heartbeat\n\n"
        except (DMError, SessionError):
            return
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
