"""Enforce application authorization independently of presence subscribers."""
import logging
import re
import threading
from bson import ObjectId

from app.extensions import mongo
from app.models import role as role_model
from app.models.voice_session import queue_removal, revoke

log = logging.getLogger(__name__)
ROOM_PATTERN = re.compile(r"^synth_([0-9a-f]{24})_([0-9a-f]{24})$")


def allowed(grant: dict, user: dict | None, server: dict | None, channel: dict | None) -> bool:
    if (grant.get("revoked") or user is None or server is None or channel is None
            or server.get("deleting") or user.get("session_version", 0) != grant["session_version"]
            or grant["user_id"] not in server.get("members", [])
            or channel.get("type") != "voice" or channel["server_id"] != grant["server_id"]):
        return False
    return (server.get("owner_id") == grant["user_id"] or "join_channel" in
            role_model.get_user_permissions(str(grant["user_id"]), str(grant["server_id"])))


def remove(grant: dict):
    from app import extensions as ext
    if ext.media_server is None:
        raise RuntimeError("Voice server is unavailable")
    ext.media_server.remove_participant(grant["room"], grant["identity"])
    ext.presence_cache.remove_voice_participant(
        str(grant["server_id"]), str(grant["channel_id"]), grant["identity"],
    )
    mongo.db.voice_revocations.delete_one({"_id": f'{grant["room"]}:{grant["identity"]}'})


def remove_now(grants: list[dict]):
    for grant in grants:
        try:
            remove(grant)
        except Exception:
            # The Mongo revocation remains pending; the guard retries it.
            log.warning("Voice removal pending; access guard will retry", exc_info=True)


def enforce_once():
    from app import extensions as ext
    if ext.media_server is None:
        return
    failures = []
    for pending in list(mongo.db.voice_revocations.find()):
        try:
            remove(pending)
        except Exception as exc:
            failures.append(exc)
    # Check disconnected grants too: restoring membership/permissions must not
    # resurrect a cached token, even after the empty media room has disappeared.
    grants = list(mongo.db.voice_sessions.find({"revoked": False}))
    users = {u["_id"]: u for u in mongo.db.users.find(
        {"_id": {"$in": list({g["user_id"] for g in grants})}}, {"session_version": 1},
    )}
    servers = {s["_id"]: s for s in mongo.db.servers.find(
        {"_id": {"$in": list({g["server_id"] for g in grants})}}, {"members": 1, "owner_id": 1, "deleting": 1},
    )}
    channels = {c["_id"]: c for c in mongo.db.channels.find(
        {"_id": {"$in": list({g["channel_id"] for g in grants})}}, {"server_id": 1, "type": 1},
    )}
    permitted = set()
    for grant in grants:
        if allowed(grant, users.get(grant["user_id"]), servers.get(grant["server_id"]), channels.get(grant["channel_id"])):
            permitted.add((grant["room"], grant["identity"]))
        else:
            try:
                # Match the exact identity so a concurrent fresh join survives.
                for revoked in revoke({"_id": grant["_id"], "identity": grant["identity"]}):
                    remove(revoked)
            except Exception as exc:
                failures.append(exc)
    rooms = [room for room in ext.media_server.list_rooms() if ROOM_PATTERN.fullmatch(room.name)]
    for room in rooms:
        try:
            participants = ext.media_server.list_participants(room.name)
        except Exception as exc:
            failures.append(exc)
            continue
        for participant in participants:
            if (room.name, participant.identity) not in permitted:
                # A join on another worker can commit after this sweep's
                # snapshot. Recheck its fresh grant before disconnecting it.
                current = mongo.db.voice_sessions.find_one({"room": room.name, "identity": participant.identity})
                if current and allowed(
                        current, mongo.db.users.find_one({"_id": current["user_id"]}),
                        mongo.db.servers.find_one({"_id": current["server_id"]}),
                        mongo.db.channels.find_one({"_id": current["channel_id"]})):
                    continue
                match = ROOM_PATTERN.fullmatch(room.name)
                grant = {"room": room.name, "identity": participant.identity,
                         "server_id": ObjectId(match[1]), "channel_id": ObjectId(match[2])}
                try:
                    if current:
                        revoke({"_id": current["_id"], "identity": current["identity"]})
                    queue_removal(grant)
                    remove(grant)
                except Exception as exc:
                    failures.append(exc)
    if failures:
        # Finish all independent removals before reporting an unhealthy sweep.
        raise RuntimeError(f"{len(failures)} voice access operation(s) failed") from failures[0]


class VoiceAccessGuard:
    INTERVAL = 2.0

    def __init__(self):
        self._stop = threading.Event()
        self._thread = None

    def start(self, app):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        def run():
            error_logged = False
            while not self._stop.wait(self.INTERVAL):
                try:
                    with app.app_context():
                        enforce_once()
                    error_logged = False
                except Exception:
                    if not error_logged:
                        app.logger.exception("Voice access check failed; retrying")
                        error_logged = True
        self._thread = threading.Thread(target=run, name="voice-access", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2)


voice_access_guard = VoiceAccessGuard()
