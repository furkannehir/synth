from flask import jsonify
from flask_smorest import Blueprint

from app.middleware.auth_middleware import auth_required
from app.services import presence_service
from app.models import user as user_model
from app.schemas import MessageSchema, UserResponseSchema

blp = Blueprint(
    "presence", __name__,
    url_prefix="/api/presence",
    description="Presence — heartbeat, online status, logout",
)

BEARER = [{"BearerAuth": []}]


# ── POST /api/presence/heartbeat ───────────────────────────
@blp.route("/heartbeat", methods=["POST"])
@blp.doc(security=BEARER)
@blp.response(200, UserResponseSchema)
@auth_required
def heartbeat(current_user=None):
    """Client calls this every ~30 s to stay online."""
    user = presence_service.heartbeat(str(current_user["_id"]))
    return jsonify({"user": user}), 200


# ── POST /api/presence/offline  (logout) ───────────────────
@blp.route("/offline", methods=["POST"])
@blp.doc(security=BEARER)
@blp.response(200, MessageSchema)
@auth_required
def go_offline(current_user=None):
    """Explicitly mark the current user as offline."""
    presence_service.go_offline(str(current_user["_id"]))
    return jsonify({"message": "You are now offline."}), 200
