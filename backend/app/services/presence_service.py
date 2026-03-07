from datetime import datetime, timezone, timedelta

from app.models import user as user_model

# Users who haven't sent a heartbeat within this window are considered offline
HEARTBEAT_TIMEOUT = timedelta(seconds=60)


def heartbeat(user_id: str) -> dict:
    """
    Record a heartbeat — mark user online and update last_seen.
    Returns the serialised user dict.
    """
    user_model.set_online(user_id, True)
    user = user_model.find_by_id(user_id)
    return user_model.to_dict(user)


def go_offline(user_id: str) -> None:
    """Explicitly mark a user as offline (logout / disconnect)."""
    user_model.set_online(user_id, False)


def sweep_stale_users() -> int:
    """
    Mark users offline if their last_seen is older than HEARTBEAT_TIMEOUT.
    Returns the number of users marked offline.
    """
    cutoff = datetime.now(timezone.utc) - HEARTBEAT_TIMEOUT
    col = user_model.get_collection()
    result = col.update_many(
        {"is_online": True, "last_seen": {"$lt": cutoff}},
        {"$set": {"is_online": False}},
    )
    return result.modified_count
