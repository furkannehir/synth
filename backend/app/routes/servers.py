from flask import request, jsonify, Response, stream_with_context, current_app
from flask_smorest import Blueprint
import json

from app.middleware.auth_middleware import auth_required, permission_required
from app.services.server_service import ServerError
from app.services import server_service
from app.services.invite_service import InviteError
from app.services import invite_service
from app.schemas import (
    CreateServerSchema, UpdateServerSchema,
    ServerResponseSchema, ServerListSchema,
    MemberListSchema, MessageSchema,
    CreateInviteSchema, InviteResponseSchema, InviteListSchema,
)

blp = Blueprint(
    "servers", __name__,
    url_prefix="/api/servers",
    description="Servers — Discord-style communities",
)

BEARER = [{"BearerAuth": []}]


# ── GET /api/servers  —  list servers the user has joined ──
@blp.route("", methods=["GET"])
@blp.doc(security=BEARER, parameters=[{
    "in": "query", "name": "all",
    "schema": {"type": "boolean"},
    "description": "Pass true to list every server (discovery)",
}])
@blp.response(200, ServerListSchema)
@auth_required
def list_servers(current_user=None):
    user_id = str(current_user["_id"])
    # ?all=true  →  list every server (for discovery later)
    if request.args.get("all") == "true":
        servers = server_service.list_servers()
    else:
        servers = server_service.list_servers(user_id=user_id)
    return jsonify({"servers": servers}), 200


# ── POST /api/servers  —  create a new server ─────────────
@blp.route("", methods=["POST"])
@blp.doc(security=BEARER)
@blp.arguments(CreateServerSchema)
@blp.response(201, ServerResponseSchema)
@blp.alt_response(400, description="Validation error")
@auth_required
def create_server(data, current_user=None):
    try:
        server = server_service.create_server(
            name=data.get("name", "").strip(),
            owner_id=str(current_user["_id"]),
            icon=data.get("icon"),
        )
    except ServerError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"server": server}), 201


# ── GET /api/servers/<id>  —  get server details ──────────
@blp.route("/<server_id>", methods=["GET"])
@blp.doc(security=BEARER)
@blp.response(200, ServerResponseSchema)
@blp.alt_response(404, description="Server not found")
@auth_required
def get_server(server_id, current_user=None):
    try:
        server = server_service.get_server(server_id)
    except ServerError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"server": server}), 200


# ── PUT /api/servers/<id>  —  update server (owner only) ──
@blp.route("/<server_id>", methods=["PUT"])
@blp.doc(security=BEARER)
@blp.arguments(UpdateServerSchema)
@blp.response(200, ServerResponseSchema)
@blp.alt_response(403, description="Not the owner")
@auth_required
def update_server(data, server_id, current_user=None):
    try:
        server = server_service.update_server(
            server_id, str(current_user["_id"]), data,
        )
    except ServerError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"server": server}), 200


# ── DELETE /api/servers/<id>  —  delete server (owner only)
@blp.route("/<server_id>", methods=["DELETE"])
@blp.doc(security=BEARER)
@blp.response(200, MessageSchema)
@blp.alt_response(403, description="Not the owner")
@auth_required
def delete_server(server_id, current_user=None):
    try:
        server_service.delete_server(server_id, str(current_user["_id"]))
    except ServerError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"message": "Server deleted."}), 200


# ── POST /api/servers/<id>/join  —  join a server ─────────
@blp.route("/<server_id>/join", methods=["POST"])
@blp.doc(security=BEARER)
@blp.response(200, MessageSchema)
@blp.alt_response(409, description="Already a member")
@auth_required
def join_server(server_id, current_user=None):
    try:
        server_service.join_server(server_id, str(current_user["_id"]))
    except ServerError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"message": "Joined server."}), 200


# ── POST /api/servers/<id>/leave  —  leave a server ───────
@blp.route("/<server_id>/leave", methods=["POST"])
@blp.doc(security=BEARER)
@blp.response(200, MessageSchema)
@blp.alt_response(400, description="Cannot leave default server")
@auth_required
def leave_server(server_id, current_user=None):
    try:
        server_service.leave_server(server_id, str(current_user["_id"]))
    except ServerError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"message": "Left server."}), 200


# ── GET /api/servers/<id>/members  —  list server members ─
@blp.route("/<server_id>/members", methods=["GET"])
@blp.doc(security=BEARER)
@blp.response(200, MemberListSchema)
@blp.alt_response(404, description="Server not found")
@auth_required
def get_members(server_id, current_user=None):
    try:
        members = server_service.get_members(server_id)
    except ServerError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"members": members}), 200


# ── POST /api/servers/<id>/invites  —  create an invite ────
@blp.route("/<server_id>/invites", methods=["POST"])
@blp.doc(security=BEARER)
@blp.arguments(CreateInviteSchema)
@blp.response(201, InviteResponseSchema)
@auth_required
@permission_required("manage_server")
def create_invite(data, server_id, current_user=None):
    expires_in_hours = data.get("expires_in_hours")
    if expires_in_hours is None:
        expires_in_hours = current_app.config.get("INVITE_DEFAULT_EXPIRES_HOURS", 24)

    try:
        invite = invite_service.create_invite(
            server_id=server_id,
            user_id=str(current_user["_id"]),
            max_uses=data.get("max_uses", 0),
            expires_in_hours=expires_in_hours,
        )
    except InviteError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"invite": invite}), 201


# ── GET /api/servers/<id>/invites  —  list server invites ──
@blp.route("/<server_id>/invites", methods=["GET"])
@blp.doc(security=BEARER)
@blp.response(200, InviteListSchema)
@auth_required
def list_invites(server_id, current_user=None):
    try:
        invites = invite_service.list_server_invites(
            server_id, str(current_user["_id"]),
        )
    except InviteError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"invites": invites}), 200


# ── GET /api/servers/<id>/members/stream  —  SSE presence ───
@blp.route("/<server_id>/members/stream", methods=["GET"])
@blp.doc(security=BEARER)
@auth_required
def stream_members(server_id, current_user=None):
    """
    Server-Sent Events stream of member presence for a server.

    The client opens one long-lived connection.  The server's background
    cache-refresh thread queries MongoDB every REFRESH_INTERVAL seconds and
    wakes all sleeping generators via a threading.Condition.  This means
    N clients watching the same server cost O(1) DB queries per cycle.
    """
    from app.extensions import presence_cache
    from app.services.server_service import get_members

    # Verify the server exists (reuse existing route logic)
    try:
        initial_members = get_members(server_id)
    except ServerError as exc:
        return jsonify({"error": exc.message}), exc.status_code

    presence_cache.register(server_id)
    # Seed cache immediately so first SSE frame is instant
    if presence_cache.get(server_id) is None:
        presence_cache.update(server_id, {"members": initial_members, "voice_channels": {}})

    def generate():
        last_payload = None
        try:
            # --- First frame: send immediately without waiting ---
            cached_data = presence_cache.get(server_id)
            if not isinstance(cached_data, dict):
                cached_data = {"members": cached_data or initial_members, "voice_channels": {}}
                
            payload = json.dumps(cached_data)
            last_payload = payload
            yield f"data: {payload}\n\n"

            # --- Subsequent frames: wake on cache update ---
            while True:
                presence_cache.wait_for_update(server_id)
                cached_data = presence_cache.get(server_id)
                if cached_data is None:
                    continue
                if not isinstance(cached_data, dict):
                    cached_data = {"members": cached_data, "voice_channels": {}}
                    
                payload = json.dumps(cached_data)
                if payload != last_payload:          # send only when changed
                    last_payload = payload
                    yield f"data: {payload}\n\n"
        except GeneratorExit:
            pass  # client disconnected
        finally:
            presence_cache.unregister(server_id)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # tell Nginx/Render not to buffer
            "Connection": "keep-alive",
        },
    )

