"""Concurrent invite claims and retryable server deletion, without live services."""
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import mongomock
import pytest
from bson import ObjectId
from flask import Flask
from flask_jwt_extended import create_access_token
from flask_smorest import Api

from app import extensions, voice_access
from app.adapters.livekit_adapter import LiveKitAdapter
from livekit import api as lk
from app.extensions import jwt, mongo
from app.models import channel as channel_model, invite as invite_model, message as message_model
from app.models import role as role_model, server as server_model, user as user_model, voice_session
from app.ports.media_server import RoomInfo, ParticipantInfo
from app.realtime import ChannelEventBus
from app.services import channel_service, invite_service, message_service, role_service
from app.services import server_cleanup, server_service, voice_service


class MemoryMedia:
    def __init__(self):
        self.rooms = {}
        self.fail_delete = set()
        self.fail_remove = False
        self.tokens = {}

    def create_room(self, name, **kwargs):
        self.rooms.setdefault(name, {})
        return RoomInfo(name)

    def list_rooms(self):
        return [RoomInfo(name) for name in self.rooms]

    def generate_token(self, room_name, identity, name="", **kwargs):
        token = f"mock-token-{len(self.tokens)}"
        self.tokens[token] = (room_name, identity)
        return token

    def connect(self, token):
        room, identity = self.tokens[token]
        self.rooms.setdefault(room, {})[identity] = ParticipantInfo(identity)

    def list_participants(self, room):
        return list(self.rooms.get(room, {}).values())

    def remove_participant(self, room, identity):
        if self.fail_remove:
            raise ConnectionError("provider temporarily unavailable")
        self.rooms.get(room, {}).pop(identity, None)

    def delete_room(self, room):
        if room in self.fail_delete:
            raise ConnectionError("provider temporarily unavailable")
        self.rooms.pop(room, None)


@pytest.fixture
def environment(monkeypatch):
    db = mongomock.MongoClient(tz_aware=True).invite_server_cleanup_tests
    monkeypatch.setattr(mongo, "db", db)
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="invite-server-test-signing-key-32-bytes",
                      API_TITLE="Tests", API_VERSION="v1", OPENAPI_VERSION="3.0.3",
                      LIVEKIT_URL="ws://mock.test", INVITE_DEFAULT_EXPIRES_HOURS=24)
    jwt.init_app(app)
    api = Api(app)
    from app.routes import servers, invites, channels, roles, messages, voice
    for module in (servers, invites, channels, roles, messages, voice):
        api.register_blueprint(module.blp)
    for model in (user_model, server_model, role_model, invite_model, channel_model, voice_session):
        model.ensure_indexes()
    presence, media, bus = extensions.PresenceCache(), MemoryMedia(), ChannelEventBus()
    monkeypatch.setattr(extensions, "presence_cache", presence)
    monkeypatch.setattr(extensions, "media_server", media)
    monkeypatch.setattr(messages, "channel_event_bus", bus)
    monkeypatch.setattr(presence, "wait_for_update", lambda server_id: None)
    def make_user(name):
        uid = user_model.create(name, f"{name}@example.test", "private-hash")
        with app.app_context():
            token = create_access_token(identity=uid)
        return SimpleNamespace(id=uid, headers={"Authorization": f"Bearer {token}"})
    owner, other_owner = make_user("owner"), make_user("other-owner")
    candidates = [make_user(f"candidate-{n}") for n in range(16)]
    server = server_service.create_server("First server", owner.id)["id"]
    other_server = server_service.create_server("Other server", other_owner.id)["id"]
    text = channel_model.create("chat", server, "text")
    voice_channel = channel_model.create("voice", server, "voice")
    other_text = channel_model.create("other chat", other_server, "text")
    return SimpleNamespace(app=app, client=app.test_client(), db=db, owner=owner, other_owner=other_owner,
                           candidates=candidates, server=server, other_server=other_server,
                           text=text, voice_channel=voice_channel, other_text=other_text,
                           media=media, presence=presence, bus=bus, make_user=make_user)


def create_invite(e, limit=1, **kwargs):
    return invite_model.create(e.server, e.owner.id, max_uses=limit, **kwargs)


def concurrently_accept(e, code, users):
    def submit(user):
        return e.app.test_client().post(f"/api/invites/{code}/accept", headers=user.headers)
    with ThreadPoolExecutor(max_workers=len(users)) as pool:
        return list(pool.map(submit, users))


@pytest.mark.parametrize("limit", [1, 3, 0])
def test_parallel_acceptances_never_exceed_the_limit(environment, monkeypatch, limit):
    e = environment
    invite = create_invite(e, limit)
    barrier = threading.Barrier(len(e.candidates))
    lookup = invite_model.find_by_code
    def checked(code):
        snapshot = lookup(code)
        barrier.wait(timeout=5)
        return snapshot
    monkeypatch.setattr(invite_model, "find_by_code", checked)
    # Only the first lookup needs synchronization; failure classification reads
    # must not wait for callers that have already returned.
    claim = invite_model.claim_use
    def claiming(*args):
        monkeypatch.setattr(invite_model, "find_by_code", lookup)
        return claim(*args)
    monkeypatch.setattr(invite_model, "claim_use", claiming)
    responses = concurrently_accept(e, invite["code"], e.candidates)
    expected = limit or len(e.candidates)
    assert sum(r.status_code == 200 for r in responses) == expected
    assert all(r.status_code in (200, 410) for r in responses)
    stored = e.db.invites.find_one({"_id": invite["_id"]})
    assert stored["uses"] == expected and stored["pending_uses"] == 0
    assert server_model.member_count(e.server) == expected + 1
    assert e.db.user_roles.count_documents({"server_id": ObjectId(e.server)}) == expected + 1


def test_duplicate_acceptances_consume_only_one_use(environment, monkeypatch):
    e = environment
    invite = create_invite(e, 16)
    barrier = threading.Barrier(8)
    membership = server_model.is_member
    local = threading.local()
    def checked(*args):
        snapshot = membership(*args)
        if not getattr(local, "checked", False):
            local.checked = True
            barrier.wait(timeout=5)
        return snapshot
    monkeypatch.setattr(server_model, "is_member", checked)
    responses = concurrently_accept(e, invite["code"], [e.candidates[0]] * 8)
    assert sum(r.status_code == 200 for r in responses) == 1
    assert sum(r.status_code == 409 for r in responses) == 7
    stored = e.db.invites.find_one({"_id": invite["_id"]})
    assert stored["uses"] == 1 and stored["pending_uses"] == 0
    assert server_model.member_count(e.server) == 2


def test_two_invites_racing_for_same_member_refund_the_losing_claim(environment, monkeypatch):
    e = environment
    invites = [create_invite(e) for _ in range(2)]
    barrier = threading.Barrier(2)
    membership = server_model.is_member
    def checked(*args):
        snapshot = membership(*args)
        barrier.wait(timeout=5)
        return snapshot
    monkeypatch.setattr(server_model, "is_member", checked)
    def submit(invite):
        return e.app.test_client().post(f'/api/invites/{invite["code"]}/accept', headers=e.candidates[0].headers)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(submit, invites))
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert sorted(i["uses"] for i in e.db.invites.find()) == [0, 1]
    assert all(i["pending_uses"] == 0 for i in e.db.invites.find())


@pytest.mark.parametrize("race", ["expires", "revoked", "exhausted"])
def test_claim_rechecks_invite_state_after_preview(environment, monkeypatch, race):
    e = environment
    invite = create_invite(e)
    claim = invite_model.claim_use
    def racing_claim(*args):
        if race == "expires":
            invite_model.expire_by_code(invite["code"], datetime.now(timezone.utc) - timedelta(seconds=1))
        elif race == "revoked":
            invite_model.delete_by_code(invite["code"])
        else:
            e.db.invites.update_one({"_id": invite["_id"]}, {"$set": {"uses": 1}})
        return claim(*args)
    monkeypatch.setattr(invite_model, "claim_use", racing_claim)
    response = e.client.post(f'/api/invites/{invite["code"]}/accept', headers=e.candidates[0].headers)
    assert response.status_code == (404 if race == "revoked" else 410)
    assert not server_model.is_member(e.server, e.candidates[0].id)


def test_already_member_does_not_spend_a_use(environment):
    e = environment
    invite = create_invite(e)
    assert e.client.post(f'/api/invites/{invite["code"]}/accept', headers=e.owner.headers).status_code == 409
    assert e.db.invites.find_one()["uses"] == 0


def test_sweeper_does_not_remove_last_slot_before_a_duplicate_claim_is_refunded(environment, monkeypatch):
    e = environment
    invite = create_invite(e)
    def duplicate(*args):
        assert invite_service.sweep_stale_invites() == 0
        assert e.db.invites.find_one()["pending_uses"] == 1
        return False
    monkeypatch.setattr(server_model, "add_member", duplicate)
    response = e.client.post(f'/api/invites/{invite["code"]}/accept', headers=e.candidates[0].headers)
    assert response.status_code == 409
    assert e.db.invites.find_one()["uses"] == 0
    assert invite_service.get_invite(invite["code"])["uses"] == 0


@pytest.mark.parametrize("committed", [False, True])
def test_uncertain_membership_failure_cannot_free_a_spent_use(environment, monkeypatch, committed):
    e = environment
    invite = create_invite(e)
    adding = server_model.add_member
    def failure(*args):
        if committed:
            adding(*args)
        raise ConnectionError("database acknowledgement lost")
    monkeypatch.setattr(server_model, "add_member", failure)
    with pytest.raises(ConnectionError):
        invite_service.accept_invite(invite["code"], e.candidates[0].id)
    assert e.db.invites.find_one()["uses"] == 1
    assert e.db.invites.find_one()["pending_uses"] == 0
    assert e.client.post(f'/api/invites/{invite["code"]}/accept', headers=e.candidates[1].headers).status_code == 410


def test_code_collision_is_retried_using_the_unique_index(environment, monkeypatch):
    e = environment
    codes = iter(["samecode", "samecode", "new-code"])
    monkeypatch.setattr(invite_model, "_generate_code", lambda: next(codes))
    first, second = create_invite(e), create_invite(e)
    assert first["code"] == "samecode" and second["code"] == "new-code"
    assert first["_id"] != second["_id"]


@pytest.mark.parametrize("body", [
    {"max_uses": -1}, {"max_uses": True}, {"max_uses": 2**63},
    {"expires_in_hours": -1}, {"expires_in_hours": True}, {"expires_in_hours": 2**63},
    {"max_uses": 1.5}, {"expires_in_hours": 1.5},
])
def test_invalid_invite_limits_and_expiry_are_rejected(environment, body):
    e = environment
    response = e.client.post(f"/api/servers/{e.server}/invites", headers=e.owner.headers, json=body)
    assert response.status_code in (400, 422)
    assert e.db.invites.count_documents({}) == 0


def test_legacy_negative_limit_is_unusable_instead_of_unlimited(environment):
    e = environment
    invite = create_invite(e, -1)
    assert e.client.get(f'/api/invites/{invite["code"]}').status_code == 410
    assert e.client.post(f'/api/invites/{invite["code"]}/accept', headers=e.candidates[0].headers).status_code == 410


def test_preview_of_an_orphan_invite_returns_not_found(environment):
    e = environment
    invite = create_invite(e)
    server_model.delete(e.server)
    assert e.client.get(f'/api/invites/{invite["code"]}').status_code == 404


def populate(e):
    own_message = message_model.create(e.text, e.owner.id, "private server message")
    # Simulate a message created before the new server_id field existed.
    e.db.messages.update_one({"_id": ObjectId(own_message)}, {"$unset": {"server_id": ""}})
    other_message = message_model.create(e.other_text, e.other_owner.id, "other message")
    invite = create_invite(e)
    other_invite = invite_model.create(e.other_server, e.other_owner.id)
    role_model.create("custom", ["speak"], e.server)
    e.bus.publish(e.text, {"type": "message", "data": {"id": own_message}})
    e.bus.publish(e.other_text, {"type": "message", "data": {"id": other_message}})
    e.db.realtime_streams.insert_one({"_id": f"dm:{e.owner.id}:{e.other_owner.id}", "revision": 1})
    e.db.direct_messages.insert_one({"_id": ObjectId(), "content": "private DM"})
    e.db.friend_requests.insert_one({"_id": ObjectId(), "sender_id": ObjectId(e.owner.id)})
    e.presence.update(e.server, {"members": [{"id": e.owner.id, "username": "owner"}], "voice_channels": {}})
    with e.app.app_context():
        voice = voice_service.join_channel(e.server, e.voice_channel, e.owner.id, 0)
    e.media.connect(voice["token"])
    other_room = f"synth_{e.other_server}_{e.other_text}"
    e.media.create_room(other_room)
    return SimpleNamespace(invite=invite, other_invite=other_invite, other_message=other_message,
                           voice=voice, other_room=other_room)


def assert_deleted(e):
    oid = ObjectId(e.server)
    assert e.db.servers.find_one({"_id": oid}) is None
    for collection in ("channels", "roles", "user_roles", "invites", "voice_sessions"):
        assert e.db[collection].count_documents({"server_id": oid}) == 0, collection
    assert e.db.messages.count_documents({"channel_id": ObjectId(e.text)}) == 0
    assert e.db.realtime_streams.find_one({"_id": f"channel:{e.text}"}) is None
    assert e.presence.get(e.server) is None


def test_server_deletion_cascades_only_its_data_and_active_rooms(environment):
    e = environment
    data = populate(e)
    assert e.client.delete(f"/api/servers/{e.server}", headers=e.owner.headers).status_code == 200
    assert_deleted(e)
    assert data.voice["room"] not in e.media.rooms
    assert data.other_room in e.media.rooms
    assert server_model.find_by_id(e.other_server) is not None
    assert e.db.messages.find_one({"_id": ObjectId(data.other_message)}) is not None
    assert e.db.invites.find_one({"_id": data.other_invite["_id"]}) is not None
    assert e.db.roles.count_documents({"server_id": ObjectId(e.other_server)}) == 3
    assert e.db.user_roles.count_documents({"server_id": ObjectId(e.other_server)}) == 1
    assert e.db.direct_messages.count_documents({}) == 1 and e.db.friend_requests.count_documents({}) == 1
    assert e.db.users.count_documents({}) == 18
    assert e.db.realtime_streams.find_one({"_id": f"channel:{e.other_text}"}) is not None
    assert e.db.realtime_streams.count_documents({"_id": {"$regex": "^dm:"}}) == 1
    job = e.db.server_deletions.find_one({"_id": ObjectId(e.server)})
    assert set(job["channel_ids"]) == {ObjectId(e.text), ObjectId(e.voice_channel)}
    assert "name" not in job and "members" not in job
    for path in (f"/api/servers/{e.server}", f"/api/servers/{e.server}/channels",
                 f"/api/servers/{e.server}/roles", f'/api/invites/{data.invite["code"]}'):
        assert e.client.get(path, headers=e.owner.headers).status_code == 404


def test_nonowner_and_default_server_deletion_are_rejected_without_cleanup(environment):
    e = environment
    populate(e)
    assert e.client.delete(f"/api/servers/{e.server}", headers=e.other_owner.headers).status_code == 403
    e.db.servers.update_one({"_id": ObjectId(e.server)}, {"$set": {"is_default": True}})
    assert e.client.delete(f"/api/servers/{e.server}", headers=e.owner.headers).status_code == 403
    assert e.db.server_deletions.count_documents({}) == 0
    assert e.db.messages.count_documents({"channel_id": ObjectId(e.text)}) == 1


def test_owner_can_retry_deletion_and_other_users_cannot(environment):
    e = environment
    populate(e)
    for _ in range(2):
        assert e.client.delete(f"/api/servers/{e.server}", headers=e.owner.headers).status_code == 200
    assert e.client.delete(f"/api/servers/{e.server}", headers=e.other_owner.headers).status_code == 404
    assert_deleted(e)


def test_parallel_deletion_requests_are_idempotent(environment, monkeypatch):
    e = environment
    populate(e)
    mark = server_model.mark_deleting
    barrier = threading.Barrier(2)
    def racing_mark(*args):
        barrier.wait(timeout=5)
        return mark(*args)
    monkeypatch.setattr(server_model, "mark_deleting", racing_mark)
    def submit(_):
        return e.app.test_client().delete(f"/api/servers/{e.server}", headers=e.owner.headers)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(submit, range(2)))
    assert [r.status_code for r in responses] == [200, 200]
    assert_deleted(e)


def test_interrupted_cleanup_keeps_server_inaccessible_and_retries(environment, monkeypatch):
    e = environment
    populate(e)
    deleting_messages = e.db.messages.delete_many
    def failure(*args, **kwargs):
        raise ConnectionError("temporary database failure")
    monkeypatch.setattr(e.db.messages, "delete_many", failure)
    assert e.client.delete(f"/api/servers/{e.server}", headers=e.owner.headers).status_code == 200
    assert e.db.servers.find_one({"_id": ObjectId(e.server)})["deleting"] is True
    assert server_model.find_by_id(e.server) is None and not server_model.is_member(e.server, e.owner.id)
    assert e.client.get(f"/api/servers/{e.server}", headers=e.owner.headers).status_code == 404
    assert e.client.post(f"/api/servers/{e.server}/join", headers=e.candidates[0].headers).status_code == 404
    assert all(s["id"] != e.server for s in e.client.get("/api/servers?all=true", headers=e.owner.headers).get_json()["servers"])
    assert e.client.post("/api/servers", headers=e.owner.headers, json={"name": "First server"}).status_code == 409
    monkeypatch.setattr(e.db.messages, "delete_many", deleting_messages)
    server_cleanup.sweep_deleted_servers()
    assert_deleted(e)


def test_sweeper_recovers_interruption_before_job_recording(environment, monkeypatch):
    e = environment
    populate(e)
    recording = server_cleanup.record
    def failure(server):
        raise ConnectionError("interrupted before recording job")
    monkeypatch.setattr(server_cleanup, "record", failure)
    with pytest.raises(ConnectionError):
        server_service.delete_server(e.server, e.owner.id)
    assert e.db.server_deletions.count_documents({}) == 0
    assert server_model.find_by_id(e.server) is None
    monkeypatch.setattr(server_cleanup, "record", recording)
    server_cleanup.sweep_deleted_servers()
    assert_deleted(e)


def test_sweeper_recovers_orphans_created_by_previous_server_deletion(environment):
    e = environment
    data = populate(e)
    global_role = e.db.roles.insert_one({"name": "legacy global role", "permissions": ["speak"]}).inserted_id
    server_model.delete(e.server)  # old behavior left every child behind
    server_cleanup.sweep_deleted_servers()
    assert_deleted(e)
    assert data.voice["room"] not in e.media.rooms and data.other_room in e.media.rooms
    assert e.db.roles.find_one({"_id": global_role}) is not None


@pytest.mark.parametrize("default", [False, True])
def test_cleanup_rejects_an_active_or_default_parent_even_with_a_job(environment, default):
    e = environment
    data = populate(e)
    if default:
        e.db.servers.update_one({"_id": ObjectId(e.server)}, {"$set": {"is_default": True, "deleting": True}})
    server_cleanup.record(e.db.servers.find_one({"_id": ObjectId(e.server)}))
    with pytest.raises(RuntimeError, match="server cleanup operation"):
        server_cleanup.sweep_deleted_servers()
    assert e.db.messages.count_documents({"channel_id": ObjectId(e.text)}) == 1
    assert data.voice["room"] in e.media.rooms


def test_media_failure_does_not_preserve_database_data_or_block_other_rooms(environment):
    e = environment
    data = populate(e)
    stale_room = f"synth_{e.server}_{ObjectId()}"
    e.media.create_room(stale_room)  # a room whose channel no longer exists
    e.media.fail_delete.add(data.voice["room"])
    e.media.fail_remove = True
    server_service.delete_server(e.server, e.owner.id)
    assert_deleted(e)
    assert data.voice["room"] in e.media.rooms and stale_room not in e.media.rooms
    assert e.db.voice_revocations.count_documents({}) == 1
    e.media.fail_remove = False
    e.media.fail_delete.clear()
    server_cleanup.sweep_deleted_servers()
    voice_access.enforce_once()
    assert data.voice["room"] not in e.media.rooms
    assert e.db.voice_revocations.count_documents({}) == 0
    assert data.other_room in e.media.rooms


def test_late_database_writes_and_recreated_rooms_are_cleaned_on_the_next_sweep(environment):
    e = environment
    data = populate(e)
    server_service.delete_server(e.server, e.owner.id)
    oid, late_channel = ObjectId(e.server), ObjectId()
    e.db.channels.insert_one({"_id": late_channel, "server_id": oid, "name": "late", "type": "text"})
    e.db.messages.insert_one({"channel_id": late_channel, "content": "legacy late message"})
    e.db.messages.insert_one({"channel_id": ObjectId(e.text), "content": "late in old channel"})
    e.db.messages.insert_one({"channel_id": ObjectId(), "server_id": oid, "content": "late after channel removed"})
    e.db.roles.insert_one({"server_id": oid, "name": "late role"})
    e.db.user_roles.insert_one({"server_id": oid, "role_id": ObjectId(), "user_id": ObjectId(e.owner.id)})
    create_invite(e)
    e.bus.publish(e.text, {"type": "resync", "data": {}})
    e.media.connect(data.voice["token"])
    server_cleanup.sweep_deleted_servers()
    assert_deleted(e)
    assert e.db.messages.count_documents({}) == 1  # other server only
    assert data.voice["room"] not in e.media.rooms


@pytest.mark.parametrize("kind", ["channel", "message", "role", "invite", "assignment"])
def test_creating_related_data_during_deletion_returns_not_found(environment, monkeypatch, kind):
    e = environment
    def delete_server():
        server_service.delete_server(e.server, e.owner.id)
    if kind == "channel":
        create = channel_model.create
        def racing(*args, **kwargs):
            delete_server()
            return create(*args, **kwargs)
        monkeypatch.setattr(channel_model, "create", racing)
        operation = lambda: channel_service.create_channel(e.server, e.owner.id, "late")
        error = channel_service.ChannelError
    elif kind == "message":
        create = message_model.create
        def racing(*args, **kwargs):
            delete_server()
            return create(*args, **kwargs)
        monkeypatch.setattr(message_model, "create", racing)
        operation = lambda: message_service.send_message(e.text, e.owner.id, "late")
        error = message_service.MessageError
    elif kind == "role":
        create = role_model.create
        def racing(*args, **kwargs):
            delete_server()
            return create(*args, **kwargs)
        monkeypatch.setattr(role_model, "create", racing)
        operation = lambda: role_service.create_role("late", ["speak"], e.server)
        error = role_service.RoleError
    elif kind == "invite":
        create = invite_model.create
        def racing(*args, **kwargs):
            delete_server()
            return create(*args, **kwargs)
        monkeypatch.setattr(invite_model, "create", racing)
        operation = lambda: invite_service.create_invite(e.server, e.owner.id)
        error = invite_service.InviteError
    else:
        role = role_model.get_default_role(e.server)
        assign = role_model.assign_role
        def racing(*args, **kwargs):
            result = assign(*args, **kwargs)
            delete_server()
            return result
        monkeypatch.setattr(role_model, "assign_role", racing)
        operation = lambda: role_service.assign_role_to_user(e.owner.id, str(role["_id"]), e.server)
        error = role_service.RoleError
    with pytest.raises(error) as raised:
        operation()
    assert raised.value.status_code == 404
    server_cleanup.sweep_deleted_servers()
    assert_deleted(e)


def test_invite_acceptance_cannot_join_a_server_deleted_after_claim(environment, monkeypatch):
    e = environment
    invite = create_invite(e)
    add = server_model.add_member
    def racing_add(*args):
        server_service.delete_server(e.server, e.owner.id)
        return add(*args)
    monkeypatch.setattr(server_model, "add_member", racing_add)
    assert e.client.post(f'/api/invites/{invite["code"]}/accept', headers=e.candidates[0].headers).status_code == 404
    assert_deleted(e)


@pytest.mark.parametrize("kind", ["members", "channel"])
def test_server_deletion_closes_open_streams_before_sending_data(environment, monkeypatch, kind):
    e = environment
    path = f"/api/servers/{e.server}/members/stream" if kind == "members" else f"/api/channels/{e.text}/messages/events"
    response = e.client.get(path, headers=e.owner.headers, buffered=False)
    frames = iter(response.response)
    next(frames)
    if kind == "channel":
        sub = e.bus._listeners[e.text][0]
        def empty(timeout):
            raise queue.Empty
        monkeypatch.setattr(sub, "get", empty)
    server_service.delete_server(e.server, e.owner.id)
    try:
        with pytest.raises(StopIteration):
            next(frames)
    finally:
        response.close()
    assert not e.bus._listeners and e.presence.watched_server_ids() == []


@pytest.mark.parametrize("code", [None, "not_found", "permission_denied"])
def test_livekit_room_deletion_is_idempotent_but_preserves_other_errors(monkeypatch, code):
    captured = {}
    class FakeAPI:
        def __init__(self, *args, **kwargs):
            self.room = self
        async def delete_room(self, request):
            captured["room"] = request.room
            if code:
                raise lk.TwirpError(code, "test error", status=404 if code == "not_found" else 403)
        async def aclose(self):
            captured["closed"] = True
    monkeypatch.setattr(lk, "LiveKitAPI", FakeAPI)
    adapter = LiveKitAdapter("test-key", "test-secret", "ws://mock.test")
    if code == "permission_denied":
        with pytest.raises(lk.TwirpError):
            adapter.delete_room("test-room")
    else:
        adapter.delete_room("test-room")
    assert captured == {"room": "test-room", "closed": True}
