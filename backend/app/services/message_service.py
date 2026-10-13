from bson import ObjectId
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
    if not ObjectId.is_valid(channel_id):
        raise MessageError("Channel not found.", 404)
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

def validate_channel_access(channel_id: str, user_id: str) -> dict:
    channel = _require_text_channel(channel_id)
    _require_member(str(channel["server_id"]), user_id)
    return channel


def resolve_event(channel_id: str, event: dict) -> dict:
    """Resolve a journal notification; stream callers must check access."""
    if event["type"] not in {"message", "message_edit"}:
        return event
    message_id = event["data"]["id"]
    msg = message_model.find_by_id(message_id)
    if msg is None or msg["channel_id"] != ObjectId(channel_id):
        return {"type": "message_delete", "data": {"id": message_id}}
    return {"type": event["type"], "data": _populate(msg)}


def list_messages(channel_id: str, user_id: str, before: str | None = None) -> list[dict]:
    """Return the last PAGE_SIZE messages in a text channel (cursor-paginated)."""
    validate_channel_access(channel_id, user_id)
    if before is not None and not ObjectId.is_valid(before):
        raise MessageError("Invalid pagination cursor.", 400)
    try:
        msgs = message_model.find_by_channel(channel_id, before=before)
    except ValueError as exc:
        raise MessageError(str(exc), 404) from exc
    return [_populate(m) for m in msgs]


def send_message(channel_id: str, user_id: str, content: str) -> dict:
    channel = _require_text_channel(channel_id)
    _require_member(str(channel["server_id"]), user_id)

    content = content.strip()
    if not content:
        raise MessageError("Message content cannot be empty.")
    if len(content) > message_model.MAX_CONTENT_LENGTH:
        raise MessageError(f"Message exceeds {message_model.MAX_CONTENT_LENGTH} characters.")

    server_id = str(channel["server_id"])
    msg_id = message_model.create(channel_id, user_id, content, server_id=server_id)
    if server_model.find_by_id(server_id) is None or channel_model.find_by_id(channel_id) is None:
        message_model.delete(msg_id)
        raise MessageError("Channel not found.", 404)
    msg = message_model.find_by_id(msg_id)
    if msg is None:
        raise MessageError("Message not found.", 404)
    return _populate(msg)


def edit_message(message_id: str, channel_id: str, user_id: str, content: str) -> dict:
    channel = _require_text_channel(channel_id)
    _require_member(str(channel["server_id"]), user_id)
    msg = _require_message(message_id)

    if msg["channel_id"] != channel["_id"]:
        raise MessageError("Message not found.", 404)
    if str(msg["author_id"]) != user_id:
        raise MessageError("You can only edit your own messages.", 403)

    content = content.strip()
    if not content:
        raise MessageError("Message content cannot be empty.")
    if len(content) > message_model.MAX_CONTENT_LENGTH:
        raise MessageError(f"Message exceeds {message_model.MAX_CONTENT_LENGTH} characters.")

    updated = message_model.update_content(message_id, content)
    if updated is None or server_model.find_by_id(str(channel["server_id"])) is None:
        raise MessageError("Message not found.", 404)
    return _populate(updated)


def delete_message(message_id: str, channel_id: str, user_id: str, user_permissions: set):
    channel = _require_text_channel(channel_id)
    _require_member(str(channel["server_id"]), user_id)
    msg = _require_message(message_id)

    if msg["channel_id"] != channel["_id"]:
        raise MessageError("Message not found.", 404)

    is_author = str(msg["author_id"]) == user_id
    can_manage = "manage_messages" in user_permissions

    if not is_author and not can_manage:
        raise MessageError("You do not have permission to delete this message.", 403)

    message_model.delete(message_id)
