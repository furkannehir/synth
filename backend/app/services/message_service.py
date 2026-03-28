from app.models import message as message_model
from app.models import channel as channel_model
from app.models import server as server_model
from app.models import user as user_model


class MessageError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ── Helpers ────────────────────────────────────────────────

def _require_channel(channel_id: str) -> dict:
    channel = channel_model.find_by_id(channel_id)
    if channel is None:
        raise MessageError("Channel not found.", 404)
    return channel


def _require_text_channel(channel_id: str) -> dict:
    channel = _require_channel(channel_id)
    if channel.get("type") != "text":
        raise MessageError("This channel does not support messages.", 400)
    return channel


def _require_member(server_id: str, user_id: str):
    if not server_model.is_member(server_id, user_id):
        raise MessageError("You must be a member of this server.", 403)


def _require_message(message_id: str) -> dict:
    msg = message_model.find_by_id(message_id)
    if msg is None:
        raise MessageError("Message not found.", 404)
    return msg


def _populate(msg: dict) -> dict:
    """Attach author username/avatar to a message dict."""
    author = user_model.find_by_id(str(msg["author_id"]))
    return message_model.to_dict(msg, author)


# ── Public API ─────────────────────────────────────────────

def list_messages(channel_id: str, user_id: str, before: str | None = None) -> list[dict]:
    """Return the last PAGE_SIZE messages in a text channel (cursor-paginated)."""
    channel = _require_text_channel(channel_id)
    _require_member(str(channel["server_id"]), user_id)
    msgs = message_model.find_by_channel(channel_id, before=before)
    return [_populate(m) for m in msgs]


def send_message(channel_id: str, user_id: str, content: str) -> dict:
    channel = _require_text_channel(channel_id)
    _require_member(str(channel["server_id"]), user_id)

    content = content.strip()
    if not content:
        raise MessageError("Message content cannot be empty.")
    if len(content) > message_model.MAX_CONTENT_LENGTH:
        raise MessageError(f"Message exceeds {message_model.MAX_CONTENT_LENGTH} characters.")

    msg_id = message_model.create(channel_id, user_id, content)
    msg = message_model.find_by_id(msg_id)
    return _populate(msg)


def edit_message(message_id: str, channel_id: str, user_id: str, content: str) -> dict:
    channel = _require_text_channel(channel_id)
    _require_member(str(channel["server_id"]), user_id)
    msg = _require_message(message_id)

    if str(msg["channel_id"]) != channel_id:
        raise MessageError("Message not found.", 404)
    if str(msg["author_id"]) != user_id:
        raise MessageError("You can only edit your own messages.", 403)

    content = content.strip()
    if not content:
        raise MessageError("Message content cannot be empty.")
    if len(content) > message_model.MAX_CONTENT_LENGTH:
        raise MessageError(f"Message exceeds {message_model.MAX_CONTENT_LENGTH} characters.")

    updated = message_model.update_content(message_id, content)
    return _populate(updated)


def delete_message(message_id: str, channel_id: str, user_id: str, user_permissions: set):
    channel = _require_text_channel(channel_id)
    _require_member(str(channel["server_id"]), user_id)
    msg = _require_message(message_id)

    if str(msg["channel_id"]) != channel_id:
        raise MessageError("Message not found.", 404)

    is_author = str(msg["author_id"]) == user_id
    can_manage = "manage_messages" in user_permissions

    if not is_author and not can_manage:
        raise MessageError("You do not have permission to delete this message.", 403)

    message_model.delete(message_id)
