"""Scoped channel cursors and complete history across timestamp ties."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import mongomock
import pytest
from bson import ObjectId
from flask import Flask
from flask_jwt_extended import create_access_token
from flask_smorest import Api

from app.extensions import jwt, mongo
from app.models import channel as channel_model, message as message_model
from app.models import role as role_model, user as user_model
from app.services import server_service


@pytest.fixture
def environment(monkeypatch):
    db = mongomock.MongoClient(tz_aware=True).channel_pagination_tests
    monkeypatch.setattr(mongo, "db", db)
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="channel-pagination-test-signing-key-32-bytes",
                      API_TITLE="Tests", API_VERSION="v1", OPENAPI_VERSION="3.0.3")
    jwt.init_app(app)
    from app.routes import messages
    Api(app).register_blueprint(messages.blp)
    role_model.ensure_indexes()
    message_model.ensure_indexes()

    def make_user(name):
        uid = user_model.create(name, f"{name}@example.test", "private-hash")
        with app.app_context():
            token = create_access_token(identity=uid)
        return SimpleNamespace(id=uid, headers={"Authorization": f"Bearer {token}"})

    owner, member, outsider = [make_user(name) for name in ("owner", "member", "outsider")]
    server = server_service.create_server("First server", owner.id)["id"]
    other_server = server_service.create_server("Private server", outsider.id)["id"]
    server_service.join_server(server, member.id)
    channel = channel_model.create("chat", server, "text")
    sibling = channel_model.create("other chat", server, "text")
    private = channel_model.create("private chat", other_server, "text")
    voice = channel_model.create("voice", server, "voice")
    return SimpleNamespace(db=db, client=app.test_client(), owner=owner, member=member, outsider=outsider,
                           server=server, channel=channel, sibling=sibling, private=private, voice=voice,
                           base=f"/api/channels/{channel}/messages")


def insert_history(e, groups):
    base = datetime(2026, 10, 13, 12, 0, 0, 123000, tzinfo=timezone.utc)
    total = sum(count for _, count in groups)
    docs = []
    for milliseconds, count in groups:
        for _ in range(count):
            # IDs deliberately run opposite to creation time, and insertion
            # order is reversed too, so neither can stand in for the sort.
            docs.append({"_id": ObjectId(f"{total - len(docs):024x}"),
                         "channel_id": ObjectId(e.channel), "server_id": ObjectId(e.server),
                         "author_id": ObjectId(e.owner.id), "content": f"message {len(docs)}",
                         "created_at": base + timedelta(milliseconds=milliseconds), "edited_at": None})
    e.db.messages.insert_many(reversed(docs))
    return [str(doc["_id"]) for doc in sorted(docs, key=lambda doc: (doc["created_at"], doc["_id"]))]


def read_page(e, before=None, **kwargs):
    query = {} if before is None else {"before": before}
    response = e.client.get(e.base, headers=e.member.headers, query_string=query, **kwargs)
    assert response.status_code == 200
    return response.get_json()["messages"]


@pytest.mark.parametrize("groups", [[(0, 107)], [(0, 40), (1, 75), (2, 20)]])
def test_pagination_returns_every_message_once_across_timestamp_ties(environment, groups):
    e = environment
    expected = insert_history(e, groups)
    received, before, sizes = [], None, []
    for _ in range(5):
        page = read_page(e, before)
        sizes.append(len(page))
        assert len(page) <= message_model.PAGE_SIZE
        assert all(message["channel_id"] == e.channel for message in page)
        if not page:
            break
        received = [message["id"] for message in page] + received
        before = page[0]["id"]
    assert received == expected
    assert len(received) == len(set(received))
    assert sizes == [50, 50, len(expected) - 100, 0]


def test_initial_page_is_latest_messages_in_chronological_order(environment):
    e = environment
    expected = insert_history(e, [(0, 40), (1, 75), (2, 20)])
    page = read_page(e)
    assert [message["id"] for message in page] == expected[-50:]
    assert all(message["author_username"] == "owner" for message in page)
    assert all("server_id" not in message and "password_hash" not in message for message in page)


@pytest.mark.parametrize("cursor", ["", "bad-id", "g" * 24, "0" * 23, "0" * 25])
def test_malformed_cursors_return_bad_request(environment, cursor):
    e = environment
    response = e.client.get(e.base, headers=e.member.headers, query_string={"before": cursor})
    assert response.status_code == 400
    assert response.get_json() == {"error": "Invalid pagination cursor."}


@pytest.mark.parametrize("source", ["missing", "deleted", "sibling", "private"])
def test_missing_deleted_and_foreign_cursors_share_the_same_not_found_error(environment, source):
    e = environment
    if source == "missing":
        cursor = str(ObjectId())
    else:
        channel = e.channel if source == "deleted" else getattr(e, source)
        cursor = message_model.create(channel, e.owner.id, "foreign private content")
        if source == "deleted":
            message_model.delete(cursor)
    response = e.client.get(e.base, headers=e.member.headers, query_string={"before": cursor})
    assert response.status_code == 404
    assert response.get_json() == {"error": "Pagination cursor not found in this channel."}
    assert "foreign private content" not in response.get_data(as_text=True)


def test_authorization_runs_before_looking_up_a_cursor(environment, monkeypatch):
    e = environment
    cursor = message_model.create(e.channel, e.owner.id, "private")
    def forbidden_lookup(*args, **kwargs):
        raise AssertionError("Unauthorized request looked up a pagination cursor")
    monkeypatch.setattr(e.db.messages, "find_one", forbidden_lookup)
    for before in (cursor, "bad-id"):
        response = e.client.get(e.base, headers=e.outsider.headers, query_string={"before": before})
        assert response.status_code == 403
    assert e.client.get(e.base, query_string={"before": cursor}).status_code == 401


def test_member_who_left_cannot_fetch_the_next_page(environment):
    e = environment
    page = insert_history(e, [(0, 60)])
    server_service.leave_server(e.server, e.member.id)
    assert e.client.get(e.base, headers=e.member.headers, query_string={"before": page[-50]}).status_code == 403


@pytest.mark.parametrize("channel_id", ["bad-id", "0" * 24])
def test_unknown_or_malformed_channels_return_not_found(environment, channel_id):
    e = environment
    response = e.client.get(f"/api/channels/{channel_id}/messages", headers=e.member.headers)
    assert response.status_code == 404


def test_voice_channels_cannot_serve_text_history(environment):
    e = environment
    response = e.client.get(f"/api/channels/{e.voice}/messages", headers=e.member.headers)
    assert response.status_code == 400


def test_uppercase_channel_and_cursor_ids_resolve_to_the_same_page(environment):
    e = environment
    older = message_model.create(e.channel, e.owner.id, "older")
    cursor = message_model.create(e.channel, e.owner.id, "cursor")
    timestamp = datetime(2026, 10, 13, tzinfo=timezone.utc)
    e.db.messages.update_many({}, {"$set": {"created_at": timestamp}})
    response = e.client.get(f"/api/channels/{e.channel.upper()}/messages", headers=e.member.headers,
                            query_string={"before": cursor.upper()})
    assert response.status_code == 200
    assert [message["id"] for message in response.get_json()["messages"]] == [older]


def test_new_messages_between_pages_do_not_shift_older_page_boundaries(environment):
    e = environment
    expected = insert_history(e, [(0, 107)])
    latest = read_page(e)
    now = datetime(2026, 10, 13, 12, 0, 0, 123000, tzinfo=timezone.utc)
    e.db.messages.insert_many([
        {"_id": ObjectId(f"{108 + n:024x}"), "channel_id": ObjectId(e.channel),
         "author_id": ObjectId(e.owner.id), "content": "arrived later",
         "created_at": now + timedelta(milliseconds=n), "edited_at": None}
        for n in range(2)
    ])
    older = read_page(e, latest[0]["id"])
    oldest = read_page(e, older[0]["id"])
    assert [message["id"] for message in oldest + older + latest] == expected
    assert not read_page(e, oldest[0]["id"])


def test_cursor_deleted_after_lookup_still_uses_its_captured_boundary(environment, monkeypatch):
    e = environment
    expected = insert_history(e, [(0, 107)])
    cursor = expected[-50]
    lookup = e.db.messages.find_one
    def deleting_lookup(query, *args, **kwargs):
        pivot = lookup(query, *args, **kwargs)
        if query.get("_id") == ObjectId(cursor) and query.get("channel_id") == ObjectId(e.channel):
            e.db.messages.delete_one({"_id": ObjectId(cursor)})
        return pivot
    monkeypatch.setattr(e.db.messages, "find_one", deleting_lookup)
    assert [message["id"] for message in read_page(e, cursor)] == expected[7:57]


def test_empty_channel_and_earliest_cursor_return_empty_pages(environment):
    e = environment
    assert read_page(e) == []
    cursor = message_model.create(e.channel, e.owner.id, "first")
    assert read_page(e, cursor) == []
