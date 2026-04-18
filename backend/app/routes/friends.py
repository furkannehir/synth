from flask import jsonify
from flask_smorest import Blueprint

from app.middleware.auth_middleware import auth_required
from app.services.friendship_service import FriendshipError
from app.services import friendship_service
from app.schemas import (
    SendFriendRequestSchema, FriendListSchema, PendingListSchema,
    FriendRequestResponseSchema, MessageSchema, FriendUserSchema,
)

blp = Blueprint(
    "friends", __name__,
    url_prefix="/api/friends",
    description="Friends — friend requests and friend list management",
)

BEARER = [{"BearerAuth": []}]


# ── GET /api/friends ───────────────────────────────────────
@blp.route("", methods=["GET"])
@blp.doc(security=BEARER)
@blp.response(200, FriendListSchema)
@auth_required
def list_friends(current_user=None):
    """List all friends with online status."""
    friends = friendship_service.list_friends(str(current_user["_id"]))
    return jsonify({"friends": friends}), 200


# ── GET /api/friends/pending ───────────────────────────────
@blp.route("/pending", methods=["GET"])
@blp.doc(security=BEARER)
@blp.response(200, PendingListSchema)
@auth_required
def list_pending(current_user=None):
    """List pending incoming and outgoing friend requests."""
    result = friendship_service.list_pending(str(current_user["_id"]))
    return jsonify(result), 200


# ── POST /api/friends/request ──────────────────────────────
@blp.route("/request", methods=["POST"])
@blp.doc(security=BEARER)
@blp.arguments(SendFriendRequestSchema)
@blp.response(201, FriendRequestResponseSchema)
@blp.alt_response(400, description="Validation error")
@blp.alt_response(404, description="User not found")
@auth_required
def send_request(data, current_user=None):
    """Send a friend request by username."""
    try:
        result = friendship_service.send_request(
            requester_id=str(current_user["_id"]),
            username=data["username"],
        )
    except FriendshipError as exc:
        return jsonify({"error": exc.message}), exc.status_code

    status = 200 if result.get("auto_accepted") else 201
    return jsonify(result), status


# ── POST /api/friends/<request_id>/accept ──────────────────
@blp.route("/<request_id>/accept", methods=["POST"])
@blp.doc(security=BEARER)
@blp.response(200, FriendUserSchema)
@blp.alt_response(403, description="Not the addressee")
@blp.alt_response(404, description="Request not found")
@auth_required
def accept_request(request_id, current_user=None):
    """Accept a pending friend request."""
    try:
        friend = friendship_service.accept_request(
            user_id=str(current_user["_id"]),
            request_id=request_id,
        )
    except FriendshipError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify(friend), 200


# ── POST /api/friends/<request_id>/reject ──────────────────
@blp.route("/<request_id>/reject", methods=["POST"])
@blp.doc(security=BEARER)
@blp.response(200, MessageSchema)
@blp.alt_response(403, description="Not the addressee")
@blp.alt_response(404, description="Request not found")
@auth_required
def reject_request(request_id, current_user=None):
    """Reject a pending friend request."""
    try:
        friendship_service.reject_request(
            user_id=str(current_user["_id"]),
            request_id=request_id,
        )
    except FriendshipError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"message": "Friend request rejected."}), 200


# ── POST /api/friends/<request_id>/cancel ──────────────────
@blp.route("/<request_id>/cancel", methods=["POST"])
@blp.doc(security=BEARER)
@blp.response(200, MessageSchema)
@blp.alt_response(403, description="Not the requester")
@blp.alt_response(404, description="Request not found")
@auth_required
def cancel_request(request_id, current_user=None):
    """Cancel a friend request you sent."""
    try:
        friendship_service.cancel_request(
            user_id=str(current_user["_id"]),
            request_id=request_id,
        )
    except FriendshipError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"message": "Friend request cancelled."}), 200


# ── DELETE /api/friends/<friend_id> ────────────────────────
@blp.route("/<friend_id>", methods=["DELETE"])
@blp.doc(security=BEARER)
@blp.response(200, MessageSchema)
@blp.alt_response(400, description="Not friends")
@auth_required
def remove_friend(friend_id, current_user=None):
    """Remove a friend."""
    try:
        friendship_service.remove_friend(
            user_id=str(current_user["_id"]),
            friend_id=friend_id,
        )
    except FriendshipError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"message": "Friend removed."}), 200
