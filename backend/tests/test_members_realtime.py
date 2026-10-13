"""Member privacy and delivery between independent workers, without live services."""
import json
import queue
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import mongomock
import pytest
from bson import ObjectId
from flask import Flask
from flask_jwt_extended import create_access_token
from flask_smorest import Api
from pymongo.errors import DuplicateKeyError, PyMongoError

from app import extensions
from app.extensions import jwt, mongo
from app.models import channel as channel_model
from app.models import direct_message as dm_model
from app.models import message as message_model
from app.models import role as role_model
from app.models import user as user_model
from app.realtime import ChannelEventBus, DMEventBus
from app.services import server_service


PUBLIC_FIELDS = {"id", "username", "avatar", "is_online", "last_seen"}


@pytest.fixture
def database(monkeypatch):
    db = mongomock.MongoClient(tz_aware=True).member_realtime_tests
    monkeypatch.setattr(mongo, "db", db)
    return db


@pytest.fixture
def environment(database, monkeypatch):
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="member-realtime-tests-signing-key",
                      API_TITLE="Tests", API_VERSION="v1", OPENAPI_VERSION="3.0.3")
    jwt.init_app(app)
    api = Api(app)
    from app.routes import auth, servers, messages, dms
    for module in (auth, servers, messages, dms):
        api.register_blueprint(module.blp)

    channel_bus, dm_bus = ChannelEventBus(), DMEventBus()
    presence = extensions.PresenceCache()
    monkeypatch.setattr(messages, "channel_event_bus", channel_bus)
    monkeypatch.setattr(dms, "dm_event_bus", dm_bus)
    monkeypatch.setattr(extensions, "presence_cache", presence)
    monkeypatch.setattr(presence, "wait_for_update", lambda server_id: None)
    role_model.ensure_indexes()

    def make_user(name):
        user_id = user_model.create(name, f"{name}@example.test", "private-password-hash")
        database.users.update_one({"_id": ObjectId(user_id)}, {"$set": {
            "friends": [ObjectId()], "reset_token_hash": "private-reset-token",
            "future_private_field": "private-future-data",
        }})
        with app.app_context():
            token = create_access_token(identity=user_id)
        return SimpleNamespace(id=user_id, headers={"Authorization": f"Bearer {token}"})

    owner, member, outsider = [make_user(name) for name in ("owner", "member", "outsider")]
    server = server_service.create_server("Private server", owner.id)["id"]
    server_service.join_server(server, member.id)
    server_service.create_server("Other server", outsider.id)
    channel = channel_model.create("chat", server, "text")
    user_model.add_friend(owner.id, member.id)
    user_model.add_friend(owner.id, outsider.id)
    return SimpleNamespace(app=app, client=app.test_client(), db=database,
                           owner=owner, member=member, outsider=outsider,
                           server=server, channel=channel, presence=presence,
                           channel_bus=channel_bus, dm_bus=dm_bus,
                           message_routes=messages, dm_routes=dms)


@pytest.mark.parametrize("suffix", ["members", "members/stream"])
def test_nonmember_cannot_read_members_or_presence(environment, suffix):
    e = environment
    # A private cache must not become a way around endpoint authorization.
    e.presence.update(e.server, {"members": [{"email": "private@example.test"}], "voice_channels": {}})
    response = e.client.get(f"/api/servers/{e.server}/{suffix}", headers=e.outsider.headers)
    assert response.status_code == 403
    assert "members" not in response.get_json()
    assert "private@example.test" not in response.get_data(as_text=True)
    assert e.presence.watched_server_ids() == []


@pytest.mark.parametrize("suffix", ["members", "members/stream"])
def test_member_endpoints_require_authentication(environment, suffix):
    e = environment
    assert e.client.get(f"/api/servers/{e.server}/{suffix}").status_code == 401


@pytest.mark.parametrize("server_id", ["invalid-id", "000000000000000000000000"])
@pytest.mark.parametrize("suffix", ["members", "members/stream"])
def test_missing_server_has_no_member_data(environment, server_id, suffix):
    e = environment
    response = e.client.get(f"/api/servers/{server_id}/{suffix}", headers=e.owner.headers)
    assert response.status_code == 404


@pytest.mark.parametrize("viewer", ["owner", "member"])
def test_member_rest_payload_has_only_public_fields(environment, viewer):
    e = environment
    response = e.client.get(f"/api/servers/{e.server}/members", headers=getattr(e, viewer).headers)
    assert response.status_code == 200
    members = response.get_json()["members"]
    assert {m["id"] for m in members} == {e.owner.id, e.member.id}
    assert all(set(member) == PUBLIC_FIELDS for member in members)
    assert "private-" not in response.get_data(as_text=True)
    assert all(set(member) == PUBLIC_FIELDS for member in server_service.get_presence_members(e.server))


def test_stream_filters_private_fields_even_from_old_cache(environment):
    e = environment
    cached = user_model.to_dict(user_model.find_by_id(e.member.id))
    cached.update(password_hash="private-password", reset_token_hash="private-reset",
                  future_private_field="private-future")
    e.presence.update(e.server, {"members": [cached], "voice_channels": {}})
    response = e.client.get(f"/api/servers/{e.server}/members/stream",
                            headers=e.owner.headers, buffered=False)
    try:
        frame = next(iter(response.response)).decode()
        payload = json.loads(frame.split("data: ", 1)[1])
        assert set(payload["members"][0]) == PUBLIC_FIELDS
        assert "private-" not in frame
        assert "email" not in frame and "friends" not in frame and "roles" not in frame
    finally:
        response.close()
    assert e.presence.watched_server_ids() == []


def test_member_stream_closes_after_leaving(environment):
    e = environment
    response = e.client.get(f"/api/servers/{e.server}/members/stream",
                            headers=e.member.headers, buffered=False)
    frames = iter(response.response)
    next(frames)
    server_service.leave_server(e.server, e.member.id)
    e.presence.update(e.server, {"members": [{"id": e.owner.id, "username": "owner"}], "voice_channels": {}})
    try:
        with pytest.raises(StopIteration):
            next(frames)
    finally:
        response.close()
    assert e.presence.watched_server_ids() == []


def test_member_stream_filters_every_update_and_heartbeats_when_quiet(environment):
    e = environment
    stream = e.client.get(f"/api/servers/{e.server}/members/stream",
                          headers=e.member.headers, buffered=False)
    frames = iter(stream.response)
    next(frames)
    try:
        assert next(frames).decode() == ": heartbeat\n\n"
        member = user_model.to_dict(user_model.find_by_id(e.owner.id))
        member["future_private_field"] = "private-data"
        e.presence.update(e.server, {"members": [member], "voice_channels": {}})
        frame = next(frames).decode()
        assert set(json.loads(frame.split("data: ", 1)[1])["members"][0]) == PUBLIC_FIELDS
        assert "email" not in frame and "friends" not in frame and "private-" not in frame
    finally:
        stream.close()


def test_own_account_still_contains_private_account_fields(environment):
    e = environment
    response = e.client.get("/api/auth/me", headers=e.owner.headers)
    assert response.status_code == 200
    account = response.get_json()["user"]
    assert account["email"] == "owner@example.test"
    assert account["friends"] and account["created_at"]
    assert "password_hash" not in account and "reset_token_hash" not in account


@pytest.mark.parametrize("bus_class,types", [
    (ChannelEventBus, ["message", "message_edit", "message_delete"]),
    (DMEventBus, ["dm", "dm_edit", "dm_delete", "dm_read"]),
])
def test_events_reach_subscribers_on_other_workers(database, bus_class, types):
    writer, worker_a, worker_b = bus_class(), bus_class(), bus_class()
    first = worker_a.subscribe("topic")
    second = worker_a.subscribe("topic")
    third = worker_b.subscribe("topic")
    for i, kind in enumerate(types):
        writer.publish("topic", {"type": kind, "data": {"n": i}})
    worker_a.poll_once()
    worker_b.poll_once()
    for subscription in (first, second, third):
        deliveries = [subscription.get(timeout=0) for _ in types]
        assert [d.event["type"] for d in deliveries] == types
        assert [d.revision for d in deliveries] == list(range(1, len(types) + 1))
    # Re-reading the same shared history never duplicates deliveries.
    worker_a.poll_once()
    with pytest.raises(queue.Empty):
        first.get(timeout=0)


def test_namespaces_topics_and_subscriptions_are_isolated(database):
    channel, dm = ChannelEventBus(), DMEventBus()
    first, other = channel.subscribe("same"), channel.subscribe("other")
    direct = dm.subscribe("same")
    channel.publish("same", {"type": "message", "data": {}})
    dm.publish("same", {"type": "dm", "data": {}})
    channel.poll_once()
    dm.poll_once()
    assert first.get(timeout=0).event["type"] == "message"
    assert direct.get(timeout=0).event["type"] == "dm"
    with pytest.raises(queue.Empty):
        other.get(timeout=0)
    channel.unsubscribe("same", first)
    channel.publish("same", {"type": "message", "data": {}})
    channel.poll_once()
    with pytest.raises(queue.Empty):
        first.get(timeout=0)
    assert "same" not in channel._listeners


def test_reconnect_to_different_worker_replays_retained_events(database):
    writer = ChannelEventBus()
    for n in range(6):
        writer.publish("topic", {"type": "message", "data": {"n": n}})
    resumed = ChannelEventBus().subscribe("topic", "2")
    assert resumed.initial_revision == 2
    deliveries = [resumed.get(timeout=0) for _ in range(4)]
    assert [d.revision for d in deliveries] == [3, 4, 5, 6]
    assert [d.event["data"]["n"] for d in deliveries] == [2, 3, 4, 5]


def test_future_cursor_requests_resync(database):
    writer = ChannelEventBus()
    writer.publish("topic", {"type": "message", "data": {}})
    resumed = ChannelEventBus().subscribe("topic", "100")
    delivery = resumed.get(timeout=0)
    assert delivery.revision == 1 and delivery.event["type"] == "resync"


def test_racing_first_publishers_retry_duplicate_key_without_losing_events(database, monkeypatch):
    writer, consumer = ChannelEventBus(), ChannelEventBus()
    subscription = consumer.subscribe("topic")
    real_update = database.realtime_streams.update_one
    def race(query, update, **kwargs):
        if kwargs.get("upsert"):
            competing_update = {"$inc": {"revision": 1}, "$push": {"events": {"type": "other", "data": {}}}}
            real_update(query, competing_update, upsert=True)
            raise DuplicateKeyError("competing worker inserted first")
        return real_update(query, update, **kwargs)
    monkeypatch.setattr(database.realtime_streams, "update_one", race)
    writer.publish("topic", {"type": "message", "data": {}})
    consumer.poll_once()
    assert [subscription.get(timeout=0).event["type"] for _ in range(2)] == ["other", "message"]


@pytest.mark.parametrize("last_id", [None, "bad", "-1", "9" * 100, "١"])
def test_invalid_or_missing_resume_cursor_starts_at_current_history(database, last_id):
    writer = ChannelEventBus()
    writer.publish("topic", {"type": "message", "data": {}})
    subscription = ChannelEventBus().subscribe("topic", last_id)
    assert subscription.initial_revision == 1
    with pytest.raises(queue.Empty):
        subscription.get(timeout=0)


def test_concurrent_publishers_cannot_leave_sequence_gaps(database):
    workers = [ChannelEventBus() for _ in range(4)]
    consumer = ChannelEventBus()
    subscription = consumer.subscribe("topic")
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda n: workers[n % 4].publish("topic", {"type": "message", "data": {"n": n}}), range(100)))
    consumer.poll_once()
    deliveries = [subscription.get(timeout=0) for _ in range(100)]
    assert [d.revision for d in deliveries] == list(range(1, 101))
    assert {d.event["data"]["n"] for d in deliveries} == set(range(100))


def test_publish_between_subscription_snapshot_and_registration_is_delivered(database, monkeypatch):
    writer, consumer = ChannelEventBus(), ChannelEventBus()
    real_find = database.realtime_streams.find_one
    def publish_after_snapshot(*args, **kwargs):
        snapshot = real_find(*args, **kwargs)
        writer.publish("topic", {"type": "message", "data": {"n": 1}})
        return snapshot
    with monkeypatch.context() as patch:
        patch.setattr(database.realtime_streams, "find_one", publish_after_snapshot)
        subscription = consumer.subscribe("topic")
    consumer.poll_once()
    assert subscription.get(timeout=0).event["data"]["n"] == 1


def test_gap_and_slow_subscriber_trigger_resync_instead_of_silent_loss(database):
    writer, consumer = ChannelEventBus(), ChannelEventBus()
    subscription = consumer.subscribe("topic")
    for n in range(writer.HISTORY_SIZE + 1):
        writer.publish("topic", {"type": "message", "data": {"n": n}})
    consumer.poll_once()
    delivery = subscription.get(timeout=0)
    assert delivery.event["type"] == "resync"
    assert delivery.revision == writer.HISTORY_SIZE + 1
    assert len(database.realtime_streams.find_one()["events"]) == writer.HISTORY_SIZE
    # Fill the local queue across multiple polls, then overflow it.
    for _ in range(3):
        for n in range(writer.HISTORY_SIZE):
            writer.publish("topic", {"type": "message", "data": {"n": n}})
        consumer.poll_once()
    assert subscription.get(timeout=0).event["type"] == "resync"
    with pytest.raises(queue.Empty):
        subscription.get(timeout=0)


def test_oversized_event_requests_history_reload(database):
    writer, consumer = ChannelEventBus(), ChannelEventBus()
    subscription = consumer.subscribe("topic")
    writer.publish("topic", {"type": "message", "data": {"name": "x" * writer.MAX_EVENT_BYTES}})
    consumer.poll_once()
    assert subscription.get(timeout=0).event["type"] == "resync"


def test_polling_recovers_after_database_error_without_losing_events(database, monkeypatch):
    writer, consumer = ChannelEventBus(), ChannelEventBus()
    subscription = consumer.subscribe("topic")
    writer.publish("topic", {"type": "message", "data": {"n": 1}})
    with monkeypatch.context() as patch:
        patch.setattr(database.realtime_streams, "find", lambda *a, **kw: (_ for _ in ()).throw(PyMongoError("offline")))
        with pytest.raises(PyMongoError):
            consumer.poll_once()
    writer.publish("topic", {"type": "message", "data": {"n": 2}})
    consumer.poll_once()
    assert [subscription.get(timeout=0).event["data"]["n"] for _ in range(2)] == [1, 2]


def test_running_remote_worker_polls_and_can_stop(database):
    writer, consumer = ChannelEventBus(), ChannelEventBus()
    consumer.POLL_INTERVAL = 0.01
    subscription = consumer.subscribe("topic")
    consumer.start(Flask("remote-worker"))
    try:
        writer.publish("topic", {"type": "message", "data": {"n": 1}})
        assert subscription.get(timeout=2).event["data"]["n"] == 1
    finally:
        consumer.stop()
    assert not consumer._thread.is_alive()


@pytest.mark.parametrize("kind", ["channel", "dm"])
def test_api_writes_on_another_worker_reach_sse_and_resume(environment, monkeypatch, kind):
    e = environment
    if kind == "channel":
        base = f"/api/channels/{e.channel}/messages"
        writer, consumer = ChannelEventBus(), e.channel_bus
        module, attribute, expected = e.message_routes, "channel_event_bus", ["message", "message_edit", "message_delete"]
    else:
        base = f"/api/dms/{e.member.id}/messages"
        writer, consumer = DMEventBus(), e.dm_bus
        module, attribute, expected = e.dm_routes, "dm_event_bus", ["dm", "dm_edit", "dm_read", "dm_delete"]
    stream = e.client.get(base + "/events", headers=e.owner.headers, buffered=False)
    frames = iter(stream.response)
    assert "id: 0" in next(frames).decode()
    received = []
    try:
        with monkeypatch.context() as patch:
            patch.setattr(module, attribute, writer)
            sent = e.client.post(base, headers=e.owner.headers, json={"content": "hello"})
            assert sent.status_code == 201
            message_id = sent.get_json()["message"]["id"]
            consumer.poll_once()
            received.append(next(frames).decode())
            assert json.loads(received[-1].split("data: ", 1)[1])["data"]["content"] == "hello"
            assert e.client.patch(base + f"/{message_id}", headers=e.owner.headers,
                                  json={"content": "edited"}).status_code == 200
            consumer.poll_once()
            received.append(next(frames).decode())
            assert json.loads(received[-1].split("data: ", 1)[1])["data"]["content"] == "edited"
            if kind == "dm":
                assert e.client.post(f"/api/dms/{e.owner.id}/messages/read", headers=e.member.headers).status_code == 200
                consumer.poll_once()
                received.append(next(frames).decode())
            assert e.client.delete(base + f"/{message_id}", headers=e.owner.headers).status_code == 200
        consumer.poll_once()
        received.append(next(frames).decode())
        assert [json.loads(frame.split("data: ", 1)[1])["type"] for frame in received] == expected
        assert all(f"id: {n}" in frame for n, frame in enumerate(received, 1))
        assert all("content" not in event["data"] for doc in e.db.realtime_streams.find()
                   for event in doc["events"])
    finally:
        stream.close()
    resumed = e.client.get(base + "/events", headers={**e.owner.headers, "Last-Event-ID": "1"}, buffered=False)
    try:
        frames = iter(resumed.response)
        assert "id: 1" in next(frames).decode()
        replay = next(frames).decode()
        assert json.loads(replay.split("data: ", 1)[1])["type"] == ("message_delete" if kind == "channel" else "dm_delete")
        assert "hello" not in replay and "edited" not in replay
    finally:
        resumed.close()


@pytest.mark.parametrize("method", ["patch", "delete"])
def test_wrong_dm_conversation_cannot_publish_private_content(environment, method):
    e = environment
    dm_id = dm_model.create(e.owner.id, e.member.id, "private with member")
    before = e.db.realtime_streams.count_documents({})
    kwargs = {"json": {"content": "edited private content"}} if method == "patch" else {}
    response = getattr(e.client, method)(f"/api/dms/{e.outsider.id}/messages/{dm_id}",
                                         headers=e.owner.headers, **kwargs)
    assert response.status_code == 404
    assert dm_model.find_by_id(dm_id)["content"] == "private with member"
    assert e.db.realtime_streams.count_documents({}) == before


@pytest.mark.parametrize("kind", ["channel", "dm"])
def test_queued_and_replayed_events_resolve_latest_message_content(environment, kind):
    e = environment
    base = (f"/api/channels/{e.channel}/messages" if kind == "channel"
            else f"/api/dms/{e.member.id}/messages")
    sent = e.client.post(base, headers=e.owner.headers, json={"content": "private old text"})
    message_id = sent.get_json()["message"]["id"]
    e.client.patch(base + f"/{message_id}", headers=e.owner.headers, json={"content": "current text"})
    stream = e.client.get(base + "/events", headers={**e.owner.headers, "Last-Event-ID": "0"}, buffered=False)
    frames = iter(stream.response)
    connected = next(frames).decode()
    assert json.loads(connected.split("data: ", 1)[1])["data"]["revision"] == 2
    try:
        for _ in range(2):
            replay = next(frames).decode()
            assert json.loads(replay.split("data: ", 1)[1])["data"]["content"] == "current text"
            assert "private old text" not in replay
        assert "private old text" not in repr(list(e.db.realtime_streams.find()))
    finally:
        stream.close()


@pytest.mark.parametrize("kind", ["channel", "dm"])
def test_stream_revocation_prevents_even_already_queued_events(environment, kind):
    e = environment
    if kind == "channel":
        base = f"/api/channels/{e.channel}/messages/events"
        consumer, writer, topic = e.channel_bus, ChannelEventBus(), e.channel
        message_id = message_model.create(e.channel, e.owner.id, "private")
        event_type = "message"
    else:
        base = f"/api/dms/{e.owner.id}/messages/events"
        consumer, writer = e.dm_bus, DMEventBus()
        topic = dm_model.make_conversation_key(e.owner.id, e.member.id)
        message_id = dm_model.create(e.owner.id, e.member.id, "private")
        event_type = "dm"
    stream = e.client.get(base, headers=e.member.headers, buffered=False)
    frames = iter(stream.response)
    next(frames)
    writer.publish(topic, {"type": event_type, "data": {"id": message_id, "content": "private"}})
    consumer.poll_once()
    if kind == "channel":
        server_service.leave_server(e.server, e.member.id)
    else:
        user_model.remove_friend(e.owner.id, e.member.id)
    try:
        with pytest.raises(StopIteration):
            next(frames)
    finally:
        stream.close()
    assert not consumer._listeners
