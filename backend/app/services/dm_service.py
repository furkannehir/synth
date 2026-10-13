from bson import ObjectId

from app.models import direct_message as dm_model
from app.models import user as user_model


class DMError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ── Helpers ────────────────────────────────────────────────

def _conversation_key(user_id: str, friend_id: str) -> str:
    if not ObjectId.is_valid(friend_id):
        raise DMError("Invalid friend ID.", 400)
    return dm_model.make_conversation_key(user_id, friend_id)


def validate_conversation_access(user_id: str, friend_id: str) -> str:
    """Raise if the two users are not friends."""
    conv_key = _conversation_key(user_id, friend_id)
    if not user_model.are_friends(user_id, friend_id):
        raise DMError("You can only message friends.", 403)
    return conv_key


def _require_dm(dm_id: str, conversation_key: str) -> dict:
    dm = dm_model.find_by_id(dm_id, conversation_key)
    if dm is None:
        raise DMError("Message not found.", 404)
    return dm


def _populate(dm: dict) -> dict:
    """Attach sender username/avatar to a DM dict."""
    sender = user_model.find_by_id(str(dm["sender_id"]))
    return dm_model.to_dict(dm, sender)


# ── Public API ─────────────────────────────────────────────

def list_dms(user_id: str, friend_id: str, before: str | None = None) -> list[dict]:
    """Return the last PAGE_SIZE DMs with a friend (cursor-paginated)."""
    conv_key = validate_conversation_access(user_id, friend_id)
    if before is not None and not ObjectId.is_valid(before):
        raise DMError("Invalid pagination cursor.", 400)
    try:
        dms = dm_model.find_by_conversation(conv_key, before=before)
    except ValueError as exc:
        raise DMError(str(exc), 404) from exc
    return [_populate(dm) for dm in dms]


def resolve_event(user_id: str, friend_id: str, event: dict) -> dict:
    """Resolve a journal notification; stream callers must check friendship."""
    if event["type"] not in {"dm", "dm_edit"}:
        return event
    dm_id = event["data"]["id"]
    conv_key = dm_model.make_conversation_key(user_id, friend_id)
    dm = dm_model.find_by_id(dm_id, conv_key)
    if dm is None:
        return {"type": "dm_delete", "data": {"id": dm_id}}
    return {"type": event["type"], "data": _populate(dm)}


def send_dm(sender_id: str, recipient_id: str, content: str) -> dict:
    """Send a direct message to a friend."""
    conv_key = validate_conversation_access(sender_id, recipient_id)

    content = content.strip()
    if not content:
        raise DMError("Message content cannot be empty.")
    if len(content) > dm_model.MAX_CONTENT_LENGTH:
        raise DMError(f"Message exceeds {dm_model.MAX_CONTENT_LENGTH} characters.")

    dm_id = dm_model.create(sender_id, recipient_id, content)
    dm = _require_dm(dm_id, conv_key)
    return _populate(dm)


def edit_dm(dm_id: str, user_id: str, content: str, friend_id: str) -> dict:
    """Edit a direct message (only the sender can edit)."""
    conv_key = _conversation_key(user_id, friend_id)
    dm = _require_dm(dm_id, conv_key)

    if str(dm["sender_id"]) != user_id:
        raise DMError("You can only edit your own messages.", 403)

    content = content.strip()
    if not content:
        raise DMError("Message content cannot be empty.")
    if len(content) > dm_model.MAX_CONTENT_LENGTH:
        raise DMError(f"Message exceeds {dm_model.MAX_CONTENT_LENGTH} characters.")

    updated = dm_model.update_content(dm_id, content, user_id, conv_key)
    if updated is None:
        raise DMError("Message not found.", 404)
    return _populate(updated)


def delete_dm(dm_id: str, user_id: str, friend_id: str):
    """Delete a direct message (only the sender can delete)."""
    conv_key = _conversation_key(user_id, friend_id)
    dm = _require_dm(dm_id, conv_key)

    if str(dm["sender_id"]) != user_id:
        raise DMError("You can only delete your own messages.", 403)

    if not dm_model.delete(dm_id, user_id, conv_key):
        raise DMError("Message not found.", 404)


def mark_as_read(user_id: str, friend_id: str) -> dict:
    """Mark all unread DMs from friend_id to user_id as read."""
    # We only mark messages where we are the recipient
    conv_key = _conversation_key(user_id, friend_id)
    return dm_model.mark_read(conv_key, user_id)


def get_conversations(user_id: str, offset: int = 0, limit: int = 20) -> list[dict]:
    """Get recent conversations formatted for the API."""
    raw_convos = dm_model.get_recent_conversations(user_id, offset, limit)
    
    result = []
    for c in raw_convos:
        last_msg = c["last_message"]
        
        # Determine the friend's ID from the last message
        friend_id_obj = last_msg["sender_id"] if str(last_msg["sender_id"]) != user_id else last_msg["recipient_id"]
        friend = user_model.find_by_id(str(friend_id_obj))
        
        if not friend:
            continue
            
        # Serialize last message
        msg_val = _populate(last_msg)
        
        # Format friend object
        friend_val = {
            "id": str(friend["_id"]),
            "username": friend["username"],
            "avatar": friend.get("avatar"),
            "is_online": friend.get("is_online", False),
            "last_seen": friend.get("last_seen", "").isoformat() if friend.get("last_seen") else None,
        }
        
        result.append({
            "friend": friend_val,
            "last_message": msg_val,
            "unread_count": c.get("unread_count", 0),
        })
        
    return result


def get_total_unread_count(user_id: str) -> int:
    return dm_model.get_total_unread_count(user_id)
