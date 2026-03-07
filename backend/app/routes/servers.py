from flask import request, jsonify
from flask_smorest import Blueprint

from app.middleware.auth_middleware import auth_required, permission_required
from app.services.server_service import ServerError
from app.services import server_service
from app.schemas import (
    CreateServerSchema, UpdateServerSchema,
    ServerResponseSchema, ServerListSchema,
    MemberListSchema, MessageSchema,
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
