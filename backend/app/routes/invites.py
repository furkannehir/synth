from flask import jsonify
from flask_smorest import Blueprint

from app.middleware.auth_middleware import auth_required, permission_required
from app.services.invite_service import InviteError
from app.services import invite_service
from app.schemas import (
    CreateInviteSchema, InviteResponseSchema, InviteListSchema,
    InviteAcceptResponseSchema, MessageSchema,
)

blp = Blueprint(
    "invites", __name__,
    url_prefix="/api/invites",
    description="Invites — preview, accept, and manage invite links",
)

BEARER = [{"BearerAuth": []}]


# ── GET /api/invites/<code>  —  preview an invite (public) ─
@blp.route("/<code>", methods=["GET"])
@blp.response(200, InviteResponseSchema)
def preview_invite(code):
    try:
        invite = invite_service.get_invite(code)
    except InviteError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"invite": invite}), 200


# ── POST /api/invites/<code>/accept  —  join via invite ────
@blp.route("/<code>/accept", methods=["POST"])
@blp.doc(security=BEARER)
@blp.response(200, InviteAcceptResponseSchema)
@auth_required
def accept_invite(code, current_user=None):
    try:
        server = invite_service.accept_invite(code, str(current_user["_id"]))
    except InviteError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"server": server, "message": "Joined server."}), 200


# ── DELETE /api/invites/<code>  —  revoke an invite ────────
@blp.route("/<code>", methods=["DELETE"])
@blp.doc(security=BEARER)
@blp.response(200, MessageSchema)
@auth_required
def delete_invite(code, current_user=None):
    try:
        invite_service.delete_invite(code, str(current_user["_id"]))
    except InviteError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"message": "Invite deleted."}), 200
