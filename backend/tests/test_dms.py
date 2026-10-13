"""DM authorization, pagination, and truthful read receipts without live services."""
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import mongomock
import pytest
from bson import ObjectId
from flask import Flask
from flask_jwt_extended import create_access_token
from flask_smorest import Api

from app.extensions import jwt, mongo
from app.models import direct_message as dm_model
from app.models import user as user_model
from app.realtime import DMEventBus


@pytest.fixture
def dm_environment(monkeypatch):
    db = mongomock.MongoClient(tz_aware=True).dm_tests
    monkeypatch.setattr(mongo, "db", db)
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="dm-tests-signing-key-at-least-32-bytes",
                      API_TITLE="Tests", API_VERSION="v1", OPENAPI_VERSION="3.0.3")
    jwt.init_app(app)
    from app.routes import dms
    Api(app).register_blueprint(dms.blp)
    bus = DMEventBus()
    monkeypatch.setattr(dms, "dm_event_bus", bus)
    dm_model.ensure_indexes()

    def make_user(name):
        user_id = user_model.create(name, f"{name}@example.test", "unused-password-hash")
        with app.app_context():
            token = create_access_token(identity=user_id)
        return SimpleNamespace(id=user_id, headers={"Authorization": f"Bearer {token}"})

    alice, bob, carol, outsider = [make_user(name) for name in ("alice", "bob", "carol", "outsider")]
    user_model.add_friend(alice.id, bob.id)
    user_model.add_friend(alice.id, carol.id)
    return SimpleNamespace(db=db, app=app, client=app.test_client(), bus=bus,
                           alice=alice, bob=bob, carol=carol, outsider=outsider,
                           base=f"/api/dms/{bob.id}/messages")


@pytest.mark.parametrize("method,suffix,kwargs", [
    ("get", "", {}), ("post", "", {"json": {"content": "hello"}}),
    ("get", "/events", {}), ("post", "/read", {}),
    ("patch", "/000000000000000000000000", {"json": {"content": "edit"}}),
    ("delete", "/000000000000000000000000", {}),
])
def test_invalid_friend_ids_return_client_errors(dm_environment, method, suffix, kwargs):
    e = dm_environment
    response = getattr(e.client, method)("/api/dms/not-an-id/messages" + suffix,
                                         headers=e.alice.headers, **kwargs)
    assert response.status_code == 400
    assert e.db.direct_messages.count_documents({}) == 0
    assert e.db.realtime_streams.count_documents({}) == 0


@pytest.mark.parametrize("method,kwargs", [
    ("patch", {"json": {"content": "edit"}}), ("delete", {}),
])
def test_invalid_message_ids_return_not_found(dm_environment, method, kwargs):
    e = dm_environment
    response = getattr(e.client, method)(e.base + "/bad-id", headers=e.alice.headers, **kwargs)
    assert response.status_code == 404


@pytest.mark.parametrize("method,kwargs", [
    ("patch", {"json": {"content": "stolen edit"}}), ("delete", {}),
])
@pytest.mark.parametrize("viewer", ["alice", "bob", "outsider"])
def test_messages_cannot_be_mutated_via_another_conversation(dm_environment, method, kwargs, viewer):
    e = dm_environment
    dm_id = dm_model.create(e.alice.id, e.bob.id, "private with bob")
    route = f"/api/dms/{e.carol.id}/messages/{dm_id}"
    response = getattr(e.client, method)(route, headers=getattr(e, viewer).headers, **kwargs)
    assert response.status_code == 404
    assert dm_model.find_by_id(dm_id)["content"] == "private with bob"
    assert e.db.realtime_streams.count_documents({}) == 0


@pytest.mark.parametrize("method,kwargs", [
    ("patch", {"json": {"content": "unauthorized"}}), ("delete", {}),
])
def test_recipient_cannot_edit_or_delete_senders_message(dm_environment, method, kwargs):
    e = dm_environment
    dm_id = dm_model.create(e.alice.id, e.bob.id, "original")
    response = getattr(e.client, method)(f"/api/dms/{e.alice.id}/messages/{dm_id}",
                                         headers=e.bob.headers, **kwargs)
    assert response.status_code == 403
    assert dm_model.find_by_id(dm_id)["content"] == "original"


def test_sender_can_remove_own_message_after_unfriending(dm_environment):
    e = dm_environment
    dm_id = dm_model.create(e.alice.id, e.bob.id, "original")
    user_model.remove_friend(e.alice.id, e.bob.id)
    response = e.client.delete(e.base + f"/{dm_id}", headers=e.alice.headers)
    assert response.status_code == 200
    assert dm_model.find_by_id(dm_id) is None


def test_uppercase_user_ids_share_the_same_conversation(dm_environment):
    e = dm_environment
    sent = e.client.post(f"/api/dms/{e.bob.id.upper()}/messages", headers=e.alice.headers,
                         json={"content": "hello"})
    assert sent.status_code == 201
    message_id = sent.get_json()["message"]["id"]
    history = e.client.get(e.base, headers=e.alice.headers).get_json()["messages"]
    assert [m["id"] for m in history] == [message_id]
    edited = e.client.patch(f"/api/dms/{e.bob.id.upper()}/messages/{message_id.upper()}",
                            headers=e.alice.headers, json={"content": "edited"})
    assert edited.status_code == 200
    assert edited.get_json()["message"]["content"] == "edited"
    deleted = e.client.delete(f"/api/dms/{e.bob.id.upper()}/messages/{message_id.upper()}",
                              headers=e.alice.headers)
    assert deleted.status_code == 200
    key = dm_model.make_conversation_key(e.alice.id, e.bob.id)
    event = e.db.realtime_streams.find_one({"_id": f"dm:{key}"})["events"][-1]
    assert event == {"type": "dm_delete", "data": {"id": message_id}}


@pytest.mark.parametrize("cursor,expected", [("bad-id", 400), ("000000000000000000000000", 404)])
def test_invalid_or_missing_history_cursors_are_rejected(dm_environment, cursor, expected):
    e = dm_environment
    response = e.client.get(e.base + f"?before={cursor}", headers=e.alice.headers)
    assert response.status_code == expected


def test_history_cannot_use_a_cursor_from_another_conversation(dm_environment):
    e = dm_environment
    foreign = dm_model.create(e.alice.id, e.carol.id, "private with carol")
    response = e.client.get(e.base + f"?before={foreign}", headers=e.alice.headers)
    assert response.status_code == 404
    assert "private with carol" not in response.get_data(as_text=True)


def test_history_paginates_every_message_with_the_same_timestamp(dm_environment):
    e = dm_environment
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ids = [dm_model.create(e.alice.id, e.bob.id, f"message {n}") for n in range(105)]
    e.db.direct_messages.update_many({}, {"$set": {"created_at": timestamp}})
    received, before = [], None
    for _ in range(4):
        url = e.base + (f"?before={before}" if before else "")
        page = e.client.get(url, headers=e.alice.headers).get_json()["messages"]
        if not page:
            break
        received = [m["id"] for m in page] + received
        before = page[0]["id"]
    assert received == ids
    assert len(received) == len(set(received))


@pytest.mark.parametrize("query", ["offset=oops", "offset=-1", "offset=999999999999999999999",
                                    "limit=oops", "limit=0", "limit=-1", "limit=1000"])
def test_conversation_pagination_rejects_invalid_values(dm_environment, query):
    e = dm_environment
    response = e.client.get("/api/dms/conversations?" + query, headers=e.alice.headers)
    assert response.status_code == 422


def test_recent_conversations_and_unread_counts_are_private(dm_environment):
    e = dm_environment
    dm_model.create(e.bob.id, e.alice.id, "for alice")
    dm_model.create(e.carol.id, e.alice.id, "also for alice")
    dm_model.create(e.outsider.id, e.bob.id, "not for alice")
    response = e.client.get("/api/dms/conversations", headers=e.alice.headers)
    assert response.status_code == 200
    conversations = response.get_json()["conversations"]
    assert {c["friend"]["id"] for c in conversations} == {e.bob.id, e.carol.id}
    assert sum(c["unread_count"] for c in conversations) == 2
    assert "not for alice" not in response.get_data(as_text=True)
    assert all("email" not in c["friend"] and "friends" not in c["friend"] for c in conversations)
    assert e.client.get("/api/dms/unread_count", headers=e.alice.headers).get_json()["unread_count"] == 2


def test_recent_conversations_choose_latest_message_at_tied_timestamps(dm_environment):
    e = dm_environment
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    older = dm_model.create(e.bob.id, e.alice.id, "older with bob")
    newer = dm_model.create(e.bob.id, e.alice.id, "newer with bob")
    latest = dm_model.create(e.carol.id, e.alice.id, "newest with carol")
    e.db.direct_messages.update_many({}, {"$set": {"created_at": timestamp}})
    first = e.client.get("/api/dms/conversations?limit=1", headers=e.alice.headers)
    second = e.client.get("/api/dms/conversations?offset=1&limit=1", headers=e.alice.headers)
    assert first.get_json()["conversations"][0]["last_message"]["id"] == latest
    assert second.get_json()["conversations"][0]["last_message"]["id"] == newer
    assert second.get_json()["conversations"][0]["last_message"]["id"] != older


def test_read_receipts_name_only_messages_actually_marked_read(dm_environment, monkeypatch):
    e = dm_environment
    incoming = dm_model.create(e.bob.id, e.alice.id, "already delivered")
    outgoing = dm_model.create(e.alice.id, e.bob.id, "sent to bob")
    other = dm_model.create(e.carol.id, e.alice.id, "other conversation")
    events, newer = [], []
    def publish_with_new_message(topic, event):
        newer.append(dm_model.create(e.bob.id, e.alice.id, "arrived after read"))
        events.append(event)
    monkeypatch.setattr(e.bus, "publish", publish_with_new_message)
    response = e.client.post(e.base + "/read", headers=e.alice.headers)
    assert response.status_code == 200
    assert events[0]["type"] == "dm_read"
    assert events[0]["data"]["message_ids"] == [incoming]
    assert dm_model.find_by_id(incoming)["is_read"] is True
    assert all(dm_model.find_by_id(i)["is_read"] is False for i in [outgoing, other, newer[0]])
    assert e.client.post(e.base + "/read", headers=e.alice.headers).status_code == 200
    assert events[-1]["data"]["message_ids"] == [newer[0]]


def test_repeated_read_requests_do_not_duplicate_receipts(dm_environment, monkeypatch):
    e = dm_environment
    dm_id = dm_model.create(e.bob.id, e.alice.id, "incoming")
    events = []
    monkeypatch.setattr(e.bus, "publish", lambda topic, event: events.append(event))
    for _ in range(2):
        assert e.client.post(e.base + "/read", headers=e.alice.headers).status_code == 200
    assert len(events) == 1
    assert events[0]["data"]["message_ids"] == [dm_id]
    history = e.client.get(e.base, headers=e.alice.headers).get_json()["messages"]
    assert history[0]["is_read"] is True
    assert "read_receipt_id" not in history[0]


def test_large_read_batch_marks_all_messages_and_requests_resync(dm_environment):
    e = dm_environment
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    key = dm_model.make_conversation_key(e.alice.id, e.bob.id)
    e.db.direct_messages.insert_many([
        {"sender_id": ObjectId(e.bob.id), "recipient_id": ObjectId(e.alice.id),
         "conversation_key": key, "content": "incoming", "created_at": timestamp, "is_read": False}
        for _ in range(dm_model.MAX_READ_RECEIPT_IDS + 1)
    ])
    assert e.client.post(e.base + "/read", headers=e.alice.headers).status_code == 200
    assert e.db.direct_messages.count_documents({"is_read": False}) == 0
    events = e.db.realtime_streams.find_one({"_id": f"dm:{key}"})["events"]
    assert events == [{"type": "resync", "data": {}}]


@pytest.mark.parametrize("method,suffix,kwargs", [
    ("get", "", {}), ("post", "", {"json": {"content": "hello"}}),
    ("get", "/events", {}), ("post", "/read", {}),
    ("patch", "/000000000000000000000000", {"json": {"content": "edit"}}),
    ("delete", "/000000000000000000000000", {}),
])
def test_dm_endpoints_require_authentication(dm_environment, method, suffix, kwargs):
    e = dm_environment
    assert getattr(e.client, method)(e.base + suffix, **kwargs).status_code == 401


@pytest.mark.parametrize("method,suffix,kwargs", [
    ("get", "", {}), ("post", "", {"json": {"content": "hello"}}), ("get", "/events", {}),
])
def test_strangers_cannot_send_read_or_subscribe_to_dms(dm_environment, method, suffix, kwargs):
    e = dm_environment
    url = f"/api/dms/{e.outsider.id}/messages{suffix}"
    assert getattr(e.client, method)(url, headers=e.alice.headers, **kwargs).status_code == 403
    assert e.db.direct_messages.count_documents({}) == 0
    assert e.db.realtime_streams.count_documents({}) == 0


def test_edit_racing_with_deletion_returns_not_found(dm_environment, monkeypatch):
    e = dm_environment
    dm_id = dm_model.create(e.alice.id, e.bob.id, "original")
    real_update = dm_model.update_content
    def delete_before_update(*args, **kwargs):
        e.db.direct_messages.delete_one({"_id": ObjectId(dm_id)})
        return real_update(*args, **kwargs)
    monkeypatch.setattr(dm_model, "update_content", delete_before_update)
    response = e.client.patch(e.base + f"/{dm_id}", headers=e.alice.headers, json={"content": "edited"})
    assert response.status_code == 404
    assert e.db.realtime_streams.count_documents({}) == 0


def test_deletion_racing_with_another_deletion_returns_not_found(dm_environment, monkeypatch):
    e = dm_environment
    dm_id = dm_model.create(e.alice.id, e.bob.id, "original")
    real_delete = dm_model.delete
    def competing_delete(*args, **kwargs):
        e.db.direct_messages.delete_one({"_id": ObjectId(dm_id)})
        return real_delete(*args, **kwargs)
    monkeypatch.setattr(dm_model, "delete", competing_delete)
    assert e.client.delete(e.base + f"/{dm_id}", headers=e.alice.headers).status_code == 404
    assert e.db.realtime_streams.count_documents({}) == 0


def test_unrelated_message_references_cannot_expose_another_dm(dm_environment):
    e = dm_environment
    private_id = dm_model.create(e.alice.id, e.carol.id, "private with carol")
    topic = dm_model.make_conversation_key(e.alice.id, e.bob.id)
    e.bus.publish(topic, {"type": "dm_edit", "data": {"id": private_id}})
    stream = e.client.get(e.base + "/events", headers={**e.alice.headers, "Last-Event-ID": "0"}, buffered=False)
    try:
        frames = iter(stream.response)
        next(frames)
        frame = next(frames).decode()
        assert "private with carol" not in frame
        assert json.loads(frame.split("data: ", 1)[1])["type"] == "dm_delete"
    finally:
        stream.close()
