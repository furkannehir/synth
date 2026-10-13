"""Password and voice revocation regressions without a database or media server."""
import hashlib
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import bcrypt
import mongomock
import pytest
from bson import ObjectId
from flask import Flask
from flask_jwt_extended import create_access_token, decode_token
from flask_smorest import Api
from livekit import api as lk

from app import extensions, voice_access
from app.adapters.livekit_adapter import LiveKitAdapter
from app.extensions import jwt, mongo
from app.middleware import auth_middleware
from app.models import channel as channel_model, direct_message as dm_model
from app.models import role as role_model, user as user_model, voice_session
from app.ports.media_server import ParticipantInfo, RoomInfo
from app.realtime import ChannelEventBus, DMEventBus
from app.services import auth_service, channel_service, server_service, voice_service


class MemoryMedia:
    """Model a self-hosted provider that accepts cached tokens after removal."""
    def __init__(self):
        self.rooms = {}
        self.tokens = {}
        self.fail_removals = set()
        self.fail_lists = set()
        self.on_generate = None

    def create_room(self, name, **kwargs):
        self.rooms.setdefault(name, {})
        return RoomInfo(name)

    def list_rooms(self):
        return [RoomInfo(name) for name in self.rooms]

    def generate_token(self, room_name, identity, name="", **kwargs):
        token = f"mock-token-{len(self.tokens)}"
        self.tokens[token] = dict(room=room_name, identity=identity, name=name, **kwargs)
        if self.on_generate:
            callback, self.on_generate = self.on_generate, None
            callback()
        return token

    def connect(self, token):
        grant = self.tokens[token]
        self.rooms.setdefault(grant["room"], {})[grant["identity"]] = ParticipantInfo(
            grant["identity"], name=grant["name"], state="ACTIVE",
        )

    def list_participants(self, room):
        if room in self.fail_lists:
            raise ConnectionError("temporary room failure")
        return list(self.rooms.get(room, {}).values())

    def remove_participant(self, room, identity):
        if (room, identity) in self.fail_removals:
            raise ConnectionError("temporary removal failure")
        self.rooms.get(room, {}).pop(identity, None)

    def mute_participant(self, room, **kwargs):
        self.last_mute = (room, kwargs)


@pytest.fixture
def environment(monkeypatch):
    db = mongomock.MongoClient(tz_aware=True).password_voice_tests
    monkeypatch.setattr(mongo, "db", db)
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="password-voice-test-signing-key-32-bytes",
                      API_TITLE="Tests", API_VERSION="v1", OPENAPI_VERSION="3.0.3",
                      LIVEKIT_URL="ws://mock.test")
    jwt.init_app(app)
    api = Api(app)
    from app.routes import auth, voice, servers, messages, dms
    for module in (auth, voice, servers, messages, dms):
        api.register_blueprint(module.blp)
    role_model.ensure_indexes()
    user_model.ensure_indexes()
    voice_session.ensure_indexes()
    salt = bcrypt.gensalt(rounds=4)
    monkeypatch.setattr(auth_service.bcrypt, "gensalt", lambda: salt)
    media, presence = MemoryMedia(), extensions.PresenceCache()
    channel_bus, dm_bus = ChannelEventBus(), DMEventBus()
    monkeypatch.setattr(extensions, "media_server", media)
    monkeypatch.setattr(extensions, "presence_cache", presence)
    monkeypatch.setattr(presence, "wait_for_update", lambda server_id: None)
    monkeypatch.setattr(messages, "channel_event_bus", channel_bus)
    monkeypatch.setattr(dms, "dm_event_bus", dm_bus)

    def headers(user_id, version=0, legacy=False):
        with app.app_context():
            token = create_access_token(identity=user_id, additional_claims=(
                {} if legacy else {"session_version": version}))
        return {"Authorization": f"Bearer {token}"}

    def make_user(name):
        uid = user_model.create(name, f"{name}@example.test", bcrypt.hashpw(b"original-password", salt).decode())
        return SimpleNamespace(id=uid, headers=headers(uid), email=f"{name}@example.test")

    owner, member = make_user("owner"), make_user("member")
    server = server_service.create_server("First server", owner.id)["id"]
    other_server = server_service.create_server("Second server", owner.id)["id"]
    for sid in (server, other_server):
        server_service.join_server(sid, member.id)
    channel = channel_model.create("voice one", server, "voice")
    second_channel = channel_model.create("voice two", server, "voice")
    other_channel = channel_model.create("other voice", other_server, "voice")
    text_channel = channel_model.create("chat", server, "text")
    user_model.add_friend(owner.id, member.id)
    return SimpleNamespace(app=app, client=app.test_client(), db=db, owner=owner, member=member,
                           server=server, other_server=other_server, channel=channel,
                           second_channel=second_channel, other_channel=other_channel,
                           text_channel=text_channel, media=media, presence=presence,
                           headers=headers, channel_bus=channel_bus, dm_bus=dm_bus, auth_routes=auth)


def reset_link(e, raw="reset-token"):
    user_model.set_reset_token(e.member.id, hashlib.sha256(raw.encode()).hexdigest(),
                               datetime.now(timezone.utc) + timedelta(hours=1))
    return raw


def reset_request(e, raw="reset-token", password="new-password"):
    return e.client.post("/api/auth/reset-password", json={"token": raw, "new_password": password})


def join(e, *, user=None, server=None, channel=None, version=0):
    with e.app.app_context():
        result = voice_service.join_channel(server or e.server, channel or e.channel,
                                           (user or e.member).id, version)
    e.media.connect(result["token"])
    return result


def present(e, result):
    payload = e.media.tokens[result["token"]]
    return payload["identity"] in e.media.rooms[result["room"]]


def test_reset_is_consumed_once_under_concurrent_requests(environment, monkeypatch):
    e = environment
    raw = reset_link(e)
    original = user_model.find_by_reset_token
    barrier = threading.Barrier(2)

    def checked(token):
        snapshot = original(token)
        barrier.wait(timeout=5)
        return snapshot

    monkeypatch.setattr(user_model, "find_by_reset_token", checked)
    def submit(password):
        return e.app.test_client().post("/api/auth/reset-password", json={"token": raw, "new_password": password})
    with ThreadPoolExecutor(max_workers=2) as pool:
        passwords = ["first-password", "second-password"]
        results = list(pool.map(submit, passwords))
    assert sorted(r.status_code for r in results) == [200, 400]
    user = user_model.find_by_id(e.member.id)
    assert user["session_version"] == 1
    assert "reset_token_hash" not in user and "reset_token_expires" not in user
    winner = passwords[next(i for i, r in enumerate(results) if r.status_code == 200)]
    assert bcrypt.checkpw(winner.encode(), user["password_hash"].encode())


@pytest.mark.parametrize("race", ["expires", "replaced"])
def test_reset_rechecks_token_after_password_hashing(environment, monkeypatch, race):
    e = environment
    raw = reset_link(e)
    original_hash = user_model.find_by_id(e.member.id)["password_hash"]
    hashpw = bcrypt.hashpw
    def hashing(password, salt):
        if race == "expires":
            e.db.users.update_one({"_id": ObjectId(e.member.id)}, {"$set": {
                "reset_token_expires": datetime.now(timezone.utc) - timedelta(seconds=1)}})
        else:
            reset_link(e, "replacement-link")
        return hashpw(password, salt)
    monkeypatch.setattr(auth_service.bcrypt, "hashpw", hashing)
    assert reset_request(e, raw).status_code == 400
    user = user_model.find_by_id(e.member.id)
    assert user["password_hash"] == original_hash and user["session_version"] == 0
    if race == "replaced":
        assert user["reset_token_hash"] == hashlib.sha256(b"replacement-link").hexdigest()


@pytest.mark.parametrize("invalid", ["unknown", "expired", "weak"])
def test_invalid_reset_preserves_login_and_voice(environment, invalid):
    e = environment
    result = join(e)
    reset_link(e)
    if invalid == "expired":
        e.db.users.update_one({"_id": ObjectId(e.member.id)}, {"$set": {
            "reset_token_expires": datetime.now(timezone.utc) - timedelta(seconds=1)}})
    response = reset_request(e, "unknown" if invalid == "unknown" else "reset-token",
                             "short" if invalid == "weak" else "new-password")
    assert response.status_code in (400, 422)
    assert user_model.find_by_id(e.member.id)["session_version"] == 0
    assert e.client.get("/api/auth/me", headers=e.member.headers).status_code == 200
    voice_access.enforce_once()
    assert present(e, result)


def test_reset_revokes_all_old_tokens_and_new_password_login_works(environment):
    e = environment
    legacy = e.headers(e.member.id, legacy=True)
    assert e.client.get("/api/auth/me", headers=legacy).status_code == 200
    reset_link(e)
    assert reset_request(e).status_code == 200
    for headers in (e.member.headers, legacy):
        for path in ("/api/auth/me", "/api/servers", f"/api/servers/{e.server}/members"):
            assert e.client.get(path, headers=headers).status_code == 401
    assert reset_request(e).status_code == 400
    assert e.client.post("/api/auth/login", json={"email": e.member.email, "password": "original-password"}).status_code == 401
    response = e.client.post("/api/auth/login", json={"email": e.member.email, "password": "new-password"})
    assert response.status_code == 200
    data = response.get_json()
    assert data["user"]["is_online"] is True
    assert "session_version" not in data["user"]
    with e.app.app_context():
        assert decode_token(data["access_token"])["session_version"] == 1
    assert e.client.get("/api/auth/me", headers={"Authorization": f'Bearer {data["access_token"]}'}).status_code == 200


def test_legacy_account_without_session_version_can_login_and_reset(environment):
    e = environment
    e.db.users.update_one({"_id": ObjectId(e.member.id)}, {"$unset": {"session_version": ""}})
    assert e.client.post("/api/auth/login", json={"email": e.member.email, "password": "original-password"}).status_code == 200
    reset_link(e)
    assert reset_request(e).status_code == 200
    assert user_model.find_by_id(e.member.id)["session_version"] == 1
    assert e.client.get("/api/auth/me", headers=e.member.headers).status_code == 401


@pytest.mark.parametrize("version", [True, "0", -1, 99])
def test_invalid_session_versions_are_rejected(environment, version):
    e = environment
    assert e.client.get("/api/auth/me", headers=e.headers(e.member.id, version)).status_code == 401


def test_login_racing_reset_cannot_issue_new_version_for_old_password(environment, monkeypatch):
    e = environment
    original = user_model.mark_authenticated_login
    def mark(user):
        e.db.users.update_one({"_id": user["_id"]}, {"$inc": {"session_version": 1}})
        return original(user)
    monkeypatch.setattr(user_model, "mark_authenticated_login", mark)
    assert e.client.post("/api/auth/login", json={"email": e.member.email, "password": "original-password"}).status_code == 401


def test_reset_between_login_check_and_token_mint_keeps_old_version(environment, monkeypatch):
    e = environment
    mint = e.auth_routes.create_access_token
    def racing_mint(*args, **kwargs):
        e.db.users.update_one({"_id": ObjectId(e.member.id)}, {"$inc": {"session_version": 1}})
        return mint(*args, **kwargs)
    monkeypatch.setattr(e.auth_routes, "create_access_token", racing_mint)
    response = e.client.post("/api/auth/login", json={"email": e.member.email, "password": "original-password"})
    assert response.status_code == 200
    token = response.get_json()["access_token"]
    with e.app.app_context():
        assert decode_token(token)["session_version"] == 0
    assert e.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


@pytest.mark.parametrize("stream", ["channel", "dm", "members"])
@pytest.mark.parametrize("reason", ["reset", "expired"])
def test_open_streams_close_before_delivery_after_session_revocation(environment, monkeypatch, stream, reason):
    e = environment
    path = {"channel": f"/api/channels/{e.text_channel}/messages/events",
            "dm": f"/api/dms/{e.owner.id}/messages/events",
            "members": f"/api/servers/{e.server}/members/stream"}[stream]
    response = e.client.get(path, headers=e.member.headers, buffered=False)
    frames = iter(response.response)
    next(frames)
    try:
        if reason == "reset":
            reset_link(e)
            assert reset_request(e).status_code == 200
            # Another authenticated request must not overwrite the stream's claims.
            assert e.client.get("/api/auth/me", headers=e.owner.headers).status_code == 200
        else:
            now = time.time()
            monkeypatch.setattr(auth_middleware.time, "time", lambda: now + 86400)
        if stream != "members":
            bus = e.channel_bus if stream == "channel" else e.dm_bus
            topic = e.text_channel if stream == "channel" else dm_model.make_conversation_key(e.member.id, e.owner.id)
            bus.publish(topic, {"type": "resync", "data": {}})
            bus.poll_once()
        with pytest.raises(StopIteration):
            next(frames)
    finally:
        response.close()
    assert not e.channel_bus._listeners and not e.dm_bus._listeners
    assert e.presence.watched_server_ids() == []


@pytest.mark.parametrize("stream", ["channel", "dm"])
def test_quiet_stream_heartbeat_also_rechecks_session(environment, monkeypatch, stream):
    e = environment
    path = f"/api/channels/{e.text_channel}/messages/events" if stream == "channel" else f"/api/dms/{e.owner.id}/messages/events"
    response = e.client.get(path, headers=e.member.headers, buffered=False)
    frames = iter(response.response)
    next(frames)
    bus = e.channel_bus if stream == "channel" else e.dm_bus
    sub = next(iter(bus._listeners.values()))[0]
    def empty(timeout):
        raise queue.Empty
    monkeypatch.setattr(sub, "get", empty)
    reset_link(e)
    assert reset_request(e).status_code == 200
    try:
        with pytest.raises(StopIteration):
            next(frames)
    finally:
        response.close()
    assert not bus._listeners


def test_server_leave_disconnects_all_its_rooms_but_keeps_other_peers(environment):
    e = environment
    first, second = join(e), join(e, channel=e.second_channel)
    other, owner = join(e, server=e.other_server, channel=e.other_channel), join(e, user=e.owner)
    assert e.client.post(f"/api/servers/{e.server}/leave", headers=e.member.headers).status_code == 200
    assert not present(e, first) and not present(e, second)
    assert present(e, other) and present(e, owner)
    assert e.client.post(f"/api/servers/{e.server}/channels/{e.channel}/voice/join", headers=e.member.headers).status_code == 403
    e.media.connect(first["token"])
    voice_access.enforce_once()
    assert not present(e, first) and present(e, other) and present(e, owner)
    assert e.presence.watched_server_ids() == []  # enforcement needs no SSE subscriber


def test_cached_voice_token_stays_revoked_after_server_rejoin(environment):
    e = environment
    old = join(e)
    server_service.leave_server(e.server, e.member.id)
    server_service.join_server(e.server, e.member.id)
    new = join(e)
    assert e.media.tokens[old["token"]]["identity"] != e.media.tokens[new["token"]]["identity"]
    assert e.media.tokens[new["token"]]["ttl_seconds"] == 60
    e.media.connect(old["token"])
    voice_access.enforce_once()
    assert not present(e, old) and present(e, new)


def test_password_reset_disconnects_old_voice_across_servers(environment):
    e = environment
    old, other, owner = join(e), join(e, server=e.other_server, channel=e.other_channel), join(e, user=e.owner)
    reset_link(e)
    assert reset_request(e).status_code == 200
    assert not present(e, old) and not present(e, other) and present(e, owner)
    new = join(e, version=1)
    for result in (old, other):
        e.media.connect(result["token"])
    voice_access.enforce_once()
    assert not present(e, old) and not present(e, other) and present(e, new)


def test_reset_cleanup_preserves_voice_from_a_new_login(environment, monkeypatch):
    e = environment
    old = join(e)
    revoke = voice_service.revoke_user_sessions
    results = []
    def racing_cleanup(user_id):
        results.append(join(e, version=1))
        revoke(user_id)
    monkeypatch.setattr(voice_service, "revoke_user_sessions", racing_cleanup)
    reset_link(e)
    assert reset_request(e).status_code == 200
    assert not present(e, old) and present(e, results[0])


@pytest.mark.parametrize("action", ["leave", "kick", "kick_alias"])
def test_voice_leave_or_kick_revokes_grant_and_cached_token(environment, action):
    e = environment
    old, owner = join(e), join(e, user=e.owner)
    if action == "leave":
        path, headers, method = "leave", e.member.headers, e.client.post
    else:
        identity = e.member.id if action == "kick_alias" else e.media.tokens[old["token"]]["identity"]
        path, headers, method = f"participants/{identity}", e.owner.headers, e.client.delete
    assert method(f"/api/servers/{e.server}/channels/{e.channel}/voice/{path}", headers=headers).status_code == 200
    assert not present(e, old) and present(e, owner)
    e.media.connect(old["token"])
    voice_access.enforce_once()
    assert not present(e, old) and present(e, owner)


def test_mute_accepts_user_alias_and_resolves_current_voice_identity(environment):
    e = environment
    result = join(e)
    response = e.client.post(f"/api/servers/{e.server}/channels/{e.channel}/voice/participants/{e.member.id}/mute",
                             headers=e.owner.headers, json={"track_sid": "track-test", "muted": True})
    assert response.status_code == 200
    assert e.media.last_mute[1]["identity"] == e.media.tokens[result["token"]]["identity"]


@pytest.mark.parametrize("revoked", ["permission", "user", "server", "channel", "channel_type"])
def test_guard_checks_current_account_membership_channel_and_permission(environment, revoked):
    e = environment
    result = join(e)
    if revoked == "permission":
        role_model.remove_all_for_user_in_server(e.member.id, e.server)
    elif revoked == "user":
        e.db.users.delete_one({"_id": ObjectId(e.member.id)})
    elif revoked == "server":
        e.db.servers.delete_one({"_id": ObjectId(e.server)})
    elif revoked == "channel":
        e.db.channels.delete_one({"_id": ObjectId(e.channel)})
    else:
        e.db.channels.update_one({"_id": ObjectId(e.channel)}, {"$set": {"type": "text"}})
    voice_access.enforce_once()
    assert not present(e, result)


@pytest.mark.parametrize("operation", ["delete_server", "delete_channel", "change_channel_type"])
def test_deletion_and_type_change_disconnect_voice_immediately(environment, operation):
    e = environment
    result = join(e)
    if operation == "delete_server":
        server_service.delete_server(e.server, e.owner.id)
    elif operation == "delete_channel":
        channel_service.delete_channel(e.channel, e.server, e.owner.id)
    else:
        channel_service.update_channel(e.channel, e.server, e.owner.id, {"type": "text"})
    assert not present(e, result)


@pytest.mark.parametrize("race", ["leave", "reset", "permission"])
def test_voice_join_rechecks_authorization_after_token_generation(environment, race):
    e = environment
    def invalidate():
        if race == "leave":
            server_service.leave_server(e.server, e.member.id)
        elif race == "reset":
            e.db.users.update_one({"_id": ObjectId(e.member.id)}, {"$inc": {"session_version": 1}})
        else:
            role_model.remove_all_for_user_in_server(e.member.id, e.server)
    e.media.on_generate = invalidate
    response = e.client.post(f"/api/servers/{e.server}/channels/{e.channel}/voice/join", headers=e.member.headers)
    assert response.status_code == 403
    assert e.db.voice_sessions.find_one()["revoked"] is True


def test_concurrent_replacement_join_does_not_get_revoked_by_old_request(environment):
    e = environment
    replacement = []
    e.media.on_generate = lambda: replacement.append(join(e))
    response = e.client.post(f"/api/servers/{e.server}/channels/{e.channel}/voice/join", headers=e.member.headers)
    assert response.status_code == 403
    latest = e.db.voice_sessions.find_one()
    assert latest["revoked"] is False
    assert latest["identity"] == e.media.tokens[replacement[0]["token"]]["identity"]
    # The first request's token is still rejected if a provider accepts it.
    e.media.connect("mock-token-0")
    voice_access.enforce_once()
    assert set(e.media.rooms[replacement[0]["room"]]) == {latest["identity"]}


def test_failed_removal_is_durable_and_does_not_starve_other_rooms(environment):
    e = environment
    first, second = join(e), join(e, channel=e.second_channel)
    identity = e.media.tokens[first["token"]]["identity"]
    e.media.fail_removals.add((first["room"], identity))
    server_service.leave_server(e.server, e.member.id)
    assert present(e, first) and not present(e, second)
    assert e.db.voice_revocations.count_documents({}) == 1
    e.media.connect(second["token"])
    with pytest.raises(RuntimeError, match="voice access operation"):
        voice_access.enforce_once()
    assert not present(e, second) and present(e, first)
    e.media.fail_removals.clear()
    voice_access.enforce_once()
    assert not present(e, first) and e.db.voice_revocations.count_documents({}) == 0


def test_one_unavailable_room_does_not_block_enforcement_in_another(environment):
    e = environment
    first, second = join(e), join(e, channel=e.second_channel)
    e.media.fail_lists.add(first["room"])
    e.db.voice_sessions.update_many({}, {"$set": {"revoked": True}})
    with pytest.raises(RuntimeError, match="voice access operation"):
        voice_access.enforce_once()
    assert not present(e, second)


def test_guard_rejects_legacy_identities_and_ignores_foreign_rooms(environment):
    e = environment
    allowed = join(e)
    e.media.rooms[allowed["room"]][e.member.id] = ParticipantInfo(e.member.id)
    e.media.rooms["unrelated-room"] = {e.member.id: ParticipantInfo(e.member.id)}
    voice_access.enforce_once()
    assert set(e.media.rooms[allowed["room"]]) == {e.media.tokens[allowed["token"]]["identity"]}
    assert e.member.id in e.media.rooms["unrelated-room"]


@pytest.mark.parametrize("loss", ["permission", "membership"])
def test_disconnected_grant_cannot_revive_when_access_is_restored(environment, loss):
    e = environment
    old = join(e)
    # An empty room may expire on the provider before the grant is revoked.
    e.media.rooms.pop(old["room"])
    if loss == "permission":
        role_model.remove_all_for_user_in_server(e.member.id, e.server)
    else:
        # Model a worker interruption after membership removal, before cleanup.
        e.db.servers.update_one({"_id": ObjectId(e.server)}, {"$pull": {"members": ObjectId(e.member.id)}})
    voice_access.enforce_once()
    assert e.db.voice_sessions.find_one()["revoked"] is True
    if loss == "permission":
        role = role_model.get_default_role(e.server)
        role_model.assign_role(e.member.id, str(role["_id"]), e.server)
    else:
        e.db.servers.update_one({"_id": ObjectId(e.server)}, {"$addToSet": {"members": ObjectId(e.member.id)}})
    e.media.connect(old["token"])
    voice_access.enforce_once()
    assert not present(e, old)
    assert present(e, join(e))


def test_workers_can_queue_the_same_revocation_concurrently(environment, monkeypatch):
    e = environment
    join(e)
    grant = e.db.voice_sessions.find_one()
    original = e.db.voice_revocations.update_one
    def concurrent_insert(*args, **kwargs):
        original(*args, **kwargs)
        from pymongo.errors import DuplicateKeyError
        raise DuplicateKeyError("another worker inserted the same identity")
    monkeypatch.setattr(e.db.voice_revocations, "update_one", concurrent_insert)
    voice_session.queue_removal(grant)
    assert e.db.voice_revocations.count_documents({}) == 1


def test_join_after_guard_snapshot_survives_the_current_sweep(environment, monkeypatch):
    e = environment
    old = join(e)
    listing = e.media.list_participants
    fresh = []
    def racing_list(room):
        if not fresh:
            fresh.append(join(e))
        return listing(room)
    monkeypatch.setattr(e.media, "list_participants", racing_list)
    voice_access.enforce_once()
    assert present(e, fresh[0]) and not present(e, old)
    assert e.db.voice_sessions.find_one()["revoked"] is False


def test_livekit_token_has_short_initial_join_ttl():
    adapter = LiveKitAdapter("test-key", "test-secret-that-is-at-least-32-bytes", "ws://mock.test")
    import jwt as pyjwt
    claims = pyjwt.decode(adapter.generate_token("test-room", "opaque-session"),
                         "test-secret-that-is-at-least-32-bytes", algorithms=["HS256"])
    assert claims["exp"] - claims["nbf"] == 60
    assert claims["sub"] == "opaque-session" and claims["video"]["room"] == "test-room"


@pytest.mark.parametrize("error_code", [None, "not_found", "permission_denied"])
def test_livekit_removal_uses_strict_token_cutoff_and_bounded_timeout(monkeypatch, error_code):
    captured = {}
    class FakeAPI:
        def __init__(self, *args, **kwargs):
            captured["timeout"] = kwargs["timeout"].total
            self.room = self
        async def remove_participant(self, request):
            captured["request"] = request
            if error_code:
                raise lk.TwirpError(error_code, "test provider error", status=404 if error_code == "not_found" else 403)
        async def aclose(self):
            captured["closed"] = True
    monkeypatch.setattr(lk, "LiveKitAPI", FakeAPI)
    monkeypatch.setattr("app.adapters.livekit_adapter.time.time", lambda: 1000)
    adapter = LiveKitAdapter("test-key", "test-secret", "ws://mock.test")
    if error_code == "permission_denied":
        with pytest.raises(lk.TwirpError):
            adapter.remove_participant("test-room", "opaque-session")
    else:
        adapter.remove_participant("test-room", "opaque-session")
    request = captured["request"]
    assert request.room == "test-room" and request.identity == "opaque-session"
    assert request.revoke_token_ts == 1030
    assert captured["timeout"] == 5 and captured["closed"]
