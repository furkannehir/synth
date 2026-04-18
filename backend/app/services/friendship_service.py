from app.models import friend_request as request_model
from app.models import user as user_model


class FriendshipError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ── Public API ─────────────────────────────────────────────

def send_request(requester_id: str, username: str) -> dict:
    """Send a friend request to a user by username."""
    target = user_model.find_by_username(username)
    if target is None:
        raise FriendshipError("User not found.", 404)

    target_id = str(target["_id"])

    if target_id == requester_id:
        raise FriendshipError("You cannot send a friend request to yourself.")

    # Already friends?
    if user_model.are_friends(requester_id, target_id):
        raise FriendshipError("You are already friends with this user.")

    # Duplicate pending request?
    existing = request_model.find_between(requester_id, target_id)
    if existing:
        # If the other user already sent us a request, auto-accept
        if str(existing["addressee_id"]) == requester_id:
            user_model.add_friend(requester_id, target_id)
            request_model.delete(str(existing["_id"]))
            return {"auto_accepted": True, "friend": _friend_dict(target)}
        raise FriendshipError("A friend request already exists between you and this user.")

    req_id = request_model.create(requester_id, target_id)
    req = request_model.find_by_id(req_id)
    return {"auto_accepted": False, "request": request_model.to_dict(req, target)}


def accept_request(user_id: str, request_id: str) -> dict:
    """Accept a pending friend request (must be the addressee)."""
    req = request_model.find_by_id(request_id)
    if req is None:
        raise FriendshipError("Friend request not found.", 404)

    if str(req["addressee_id"]) != user_id:
        raise FriendshipError("You can only accept requests addressed to you.", 403)

    requester_id = str(req["requester_id"])

    # Add friends bidirectionally
    user_model.add_friend(user_id, requester_id)

    # Delete the transient request
    request_model.delete(request_id)

    requester = user_model.find_by_id(requester_id)
    return _friend_dict(requester)


def reject_request(user_id: str, request_id: str):
    """Reject a pending friend request (must be the addressee)."""
    req = request_model.find_by_id(request_id)
    if req is None:
        raise FriendshipError("Friend request not found.", 404)

    if str(req["addressee_id"]) != user_id:
        raise FriendshipError("You can only reject requests addressed to you.", 403)

    request_model.delete(request_id)


def cancel_request(user_id: str, request_id: str):
    """Cancel a pending friend request (must be the requester)."""
    req = request_model.find_by_id(request_id)
    if req is None:
        raise FriendshipError("Friend request not found.", 404)

    if str(req["requester_id"]) != user_id:
        raise FriendshipError("You can only cancel requests you sent.", 403)

    request_model.delete(request_id)


def remove_friend(user_id: str, friend_id: str):
    """Remove an existing friend (bidirectional)."""
    if not user_model.are_friends(user_id, friend_id):
        raise FriendshipError("You are not friends with this user.", 400)

    user_model.remove_friend(user_id, friend_id)


def list_friends(user_id: str) -> list[dict]:
    """Return all friends as serialized user dicts."""
    friends = user_model.get_friends(user_id)
    return [_friend_dict(f) for f in friends]


def list_pending(user_id: str) -> dict:
    """Return incoming and outgoing pending friend requests."""
    incoming = request_model.find_pending_incoming(user_id)
    outgoing = request_model.find_pending_outgoing(user_id)

    # Populate user info on each request
    incoming_dicts = []
    for req in incoming:
        requester = user_model.find_by_id(str(req["requester_id"]))
        incoming_dicts.append(request_model.to_dict(req, requester))

    outgoing_dicts = []
    for req in outgoing:
        addressee = user_model.find_by_id(str(req["addressee_id"]))
        outgoing_dicts.append(request_model.to_dict(req, addressee))

    return {"incoming": incoming_dicts, "outgoing": outgoing_dicts}


# ── Helpers ────────────────────────────────────────────────

def _friend_dict(user: dict) -> dict:
    """Serialize a friend user document (lightweight, no roles)."""
    if user is None:
        return None
    return {
        "id": str(user["_id"]),
        "username": user["username"],
        "avatar": user.get("avatar"),
        "is_online": user.get("is_online", False),
        "last_seen": user.get("last_seen", "").isoformat() if user.get("last_seen") else None,
    }
