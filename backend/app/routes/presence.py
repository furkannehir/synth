from flask import jsonify, request
from flask_jwt_extended import get_jwt
from flask_smorest import Blueprint

from app.middleware.auth_middleware import auth_required
from app.services import presence_service
from app.extensions import presence_cache
from app.schemas import MessageSchema, UserResponseSchema

blp = Blueprint(
    "presence", __name__,
    url_prefix="/api/presence",
    description="Presence — heartbeat, online status, logout",
)

BEARER = [{"BearerAuth": []}]


def _session_id():
    data = request.get_json(silent=True)
    if data is None and not request.data:
        return None
    if not isinstance(data, dict):
        raise presence_service.PresenceError("Expected a JSON object.")
    return presence_service.normalize_session_id(data.get("session_id"))


# ── POST /api/presence/heartbeat ───────────────────────────
@blp.route("/heartbeat", methods=["POST"])
@blp.doc(security=BEARER)
@blp.response(200, UserResponseSchema)
@auth_required
def heartbeat(current_user=None):
    """Client calls this every ~30 s to stay online."""
    try:
        user = presence_service.heartbeat(str(current_user["_id"]), get_jwt(), _session_id())
    except presence_service.PresenceError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    presence_cache.mark_dirty()
    return jsonify({"user": user}), 200


# ── POST /api/presence/offline  (logout) ───────────────────
@blp.route("/offline", methods=["POST"])
@blp.doc(security=BEARER)
@blp.response(200, MessageSchema)
@auth_required
def go_offline(current_user=None):
    """Explicitly mark the current user as offline."""
    try:
        presence_service.go_offline(str(current_user["_id"]), get_jwt(), _session_id())
    except presence_service.PresenceError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    presence_cache.mark_dirty()
    return jsonify({"message": "You are now offline."}), 200
