from app.models import direct_message as dm_model
from app.models import user as user_model


class DMError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ── Helpers ────────────────────────────────────────────────

def _require_friendship(user_id: str, friend_id: str):
    """Raise if the two users are not friends."""
    if not user_model.are_friends(user_id, friend_id):
        raise DMError("You can only message friends.", 403)


def _require_dm(dm_id: str) -> dict:
    dm = dm_model.find_by_id(dm_id)
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
    _require_friendship(user_id, friend_id)
    conv_key = dm_model.make_conversation_key(user_id, friend_id)
    dms = dm_model.find_by_conversation(conv_key, before=before)
    return [_populate(dm) for dm in dms]


def send_dm(sender_id: str, recipient_id: str, content: str) -> dict:
    """Send a direct message to a friend."""
    _require_friendship(sender_id, recipient_id)

    content = content.strip()
    if not content:
        raise DMError("Message content cannot be empty.")
    if len(content) > dm_model.MAX_CONTENT_LENGTH:
        raise DMError(f"Message exceeds {dm_model.MAX_CONTENT_LENGTH} characters.")

    dm_id = dm_model.create(sender_id, recipient_id, content)
    dm = dm_model.find_by_id(dm_id)
    return _populate(dm)


def edit_dm(dm_id: str, user_id: str, content: str) -> dict:
    """Edit a direct message (only the sender can edit)."""
    dm = _require_dm(dm_id)

    if str(dm["sender_id"]) != user_id:
        raise DMError("You can only edit your own messages.", 403)

    content = content.strip()
    if not content:
        raise DMError("Message content cannot be empty.")
    if len(content) > dm_model.MAX_CONTENT_LENGTH:
        raise DMError(f"Message exceeds {dm_model.MAX_CONTENT_LENGTH} characters.")

    updated = dm_model.update_content(dm_id, content)
    return _populate(updated)


def delete_dm(dm_id: str, user_id: str):
    """Delete a direct message (only the sender can delete)."""
    dm = _require_dm(dm_id)

    if str(dm["sender_id"]) != user_id:
        raise DMError("You can only delete your own messages.", 403)

    dm_model.delete(dm_id)


def mark_as_read(user_id: str, friend_id: str) -> int:
    """Mark all unread DMs from friend_id to user_id as read."""
    # We only mark messages where we are the recipient
    conv_key = dm_model.make_conversation_key(user_id, friend_id)
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
