from app.models import channel as channel_model
from app.models import server as server_model


class ChannelError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ── Helpers ────────────────────────────────────────────────

def _require_server(server_id: str) -> dict:
    server = server_model.find_by_id(server_id)
    if server is None:
        raise ChannelError("Server not found.", 404)
    return server


def _require_channel(channel_id: str) -> dict:
    channel = channel_model.find_by_id(channel_id)
    if channel is None:
        raise ChannelError("Channel not found.", 404)
    return channel


def _require_channel_in_server(channel_id: str, server_id: str) -> dict:
    """Fetch a channel and verify it belongs to the given server."""
    channel = _require_channel(channel_id)
    if str(channel["server_id"]) != server_id:
        raise ChannelError("Channel not found.", 404)
    return channel


def _require_member(server_id: str, user_id: str):
    if not server_model.is_member(server_id, user_id):
        raise ChannelError("You must be a member of this server.", 403)


# ── Public API ─────────────────────────────────────────────

def list_channels(server_id: str, user_id: str) -> list[dict]:
    """Return all channels in a server (caller must be a member)."""
    _require_server(server_id)
    _require_member(server_id, user_id)
    channels = channel_model.find_by_server(server_id)
    return [channel_model.to_dict(c) for c in channels]


def get_channel(channel_id: str, server_id: str, user_id: str) -> dict:
    """Get a single channel (must belong to server_id, caller must be a member)."""
    _require_server(server_id)
    _require_member(server_id, user_id)
    channel = _require_channel_in_server(channel_id, server_id)
    return channel_model.to_dict(channel)


def create_channel(
    server_id: str,
    user_id: str,
    name: str,
    channel_type: str = "voice",
    position: int | None = None,
    user_limit: int = 0,
) -> dict:
    server = _require_server(server_id)
    _require_member(server_id, user_id)

    # Validate name
    name = name.strip()
    if not name or len(name) < 2:
        raise ChannelError("Channel name must be at least 2 characters.")
    if len(name) > 100:
        raise ChannelError("Channel name cannot exceed 100 characters.")

    # Validate type
    if channel_type not in channel_model.VALID_TYPES:
        raise ChannelError(
            f"Invalid channel type. Must be one of: {', '.join(channel_model.VALID_TYPES)}"
        )

    # Validate user_limit
    if user_limit < 0:
        raise ChannelError("User limit cannot be negative.")

    # Check duplicate name within server
    if channel_model.find_by_name_in_server(server_id, name):
        raise ChannelError(
            f"A channel named '{name}' already exists in this server.", 409
        )

    channel_id = channel_model.create(
        name=name,
        server_id=server_id,
        channel_type=channel_type,
        position=position,
        user_limit=user_limit,
    )
    return channel_model.to_dict(channel_model.find_by_id(channel_id))


def update_channel(
    channel_id: str,
    server_id: str,
    user_id: str,
    updates: dict,
) -> dict:
    _require_server(server_id)
    _require_member(server_id, user_id)
    channel = _require_channel_in_server(channel_id, server_id)

    # Validate name update
    if "name" in updates:
        new_name = updates["name"].strip()
        if not new_name or len(new_name) < 2:
            raise ChannelError("Channel name must be at least 2 characters.")
        if len(new_name) > 100:
            raise ChannelError("Channel name cannot exceed 100 characters.")
        existing = channel_model.find_by_name_in_server(server_id, new_name)
        if existing and str(existing["_id"]) != channel_id:
            raise ChannelError(
                f"A channel named '{new_name}' already exists in this server.",
                409,
            )
        updates["name"] = new_name

    # Validate type update
    if "type" in updates:
        if updates["type"] not in channel_model.VALID_TYPES:
            raise ChannelError(
                f"Invalid channel type. Must be one of: {', '.join(channel_model.VALID_TYPES)}"
            )

    # Validate user_limit
    if "user_limit" in updates:
        if updates["user_limit"] < 0:
            raise ChannelError("User limit cannot be negative.")

    updated = channel_model.update(channel_id, updates)
    return channel_model.to_dict(updated)


def delete_channel(channel_id: str, server_id: str, user_id: str):
    _require_server(server_id)
    _require_member(server_id, user_id)
    channel = _require_channel_in_server(channel_id, server_id)

    if channel.get("is_default"):
        raise ChannelError("Cannot delete the default channel.", 403)

    channel_model.delete(channel_id)
