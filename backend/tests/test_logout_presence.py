"""Presence logout and worker races, using only isolated in-memory data."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import mongomock
import pytest
from bson import ObjectId
from flask import Flask
from flask_jwt_extended import create_access_token, decode_token
from flask_smorest import Api

from app.extensions import jwt, mongo
from app.models import user
from app.services import presence_service


@pytest.fixture
def environment(monkeypatch):
    db = mongomock.MongoClient(tz_aware=True).logout_presence_tests
    monkeypatch.setattr(mongo, "db", db)
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="logout-presence-tests-signing-key-32-bytes",
                      API_TITLE="Tests", API_VERSION="v1", OPENAPI_VERSION="3.0.3")
    jwt.init_app(app)
    from app.routes import presence
    Api(app).register_blueprint(presence.blp)
    uid = user.create("owner", "owner@example.test", "private-hash")

    def login_token(version=0):
        with app.app_context():
            token = create_access_token(identity=uid, additional_claims={"session_version": version})
            claims = decode_token(token)
        return SimpleNamespace(headers={"Authorization": f"Bearer {token}"}, claims=claims)

    client, auth = app.test_client(), login_token()
    lease = str(uuid4())

    def post(action, session=lease, token=auth):
        payload = {} if session is None else {"session_id": session}
        return client.post(f"/api/presence/{action}", headers=token.headers, json=payload)

    return SimpleNamespace(db=db, client=client, uid=uid, auth=auth, lease=lease,
                           post=post, login_token=login_token, document=lambda: user.find_by_id(uid))


@pytest.mark.parametrize("beat_first", [True, False])
def test_logout_closes_a_lease_even_before_its_first_heartbeat(environment, beat_first):
    e = environment
    if beat_first:
        assert e.post("heartbeat").get_json()["user"]["is_online"] is True
    assert e.post("offline").status_code == 200
    revision = e.document()["presence_revision"]
    for _ in range(2):
        response = e.post("heartbeat")
        assert response.status_code == 200
        assert response.get_json()["user"]["is_online"] is False
    assert e.document()["presence_revision"] == revision
    assert e.document()["presence_sessions"][0]["closed"] is True


@pytest.mark.parametrize("new_token", [False, True])
def test_delayed_cleanup_cannot_mark_a_new_tab_or_login_offline(environment, new_token):
    e = environment
    assert e.post("heartbeat").status_code == 200
    auth = e.login_token() if new_token else e.auth
    lease = e.lease if new_token else str(uuid4())
    assert e.post("heartbeat", lease, auth).status_code == 200
    assert e.post("offline").status_code == 200
    assert e.document()["is_online"] is True
    assert e.post("heartbeat").get_json()["user"]["is_online"] is True
    assert sum(not item["closed"] for item in e.document()["presence_sessions"]) == 1
    assert e.post("offline", lease, auth).status_code == 200
    assert e.document()["is_online"] is False


def test_effect_restart_uses_a_fresh_lease_after_cleanup(environment):
    e = environment
    e.post("heartbeat")
    e.post("offline")
    assert e.post("heartbeat", str(uuid4())).get_json()["user"]["is_online"] is True


def test_presence_leases_are_scoped_to_the_authenticated_user(environment):
    e = environment
    e.post("heartbeat")
    other = user.create("other", "other@example.test", "private-hash")
    with e.client.application.app_context():
        token = create_access_token(identity=other)
    response = e.client.post("/api/presence/offline", json={"session_id": e.lease},
                             headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert e.document()["is_online"] is True


def test_offline_wins_over_a_heartbeat_already_authenticated_on_another_worker(environment, monkeypatch):
    e = environment
    e.post("heartbeat")
    original = e.db.users.find_one_and_update
    pending = True

    def interleave(*args, **kwargs):
        nonlocal pending
        if pending:
            pending = False
            presence_service.go_offline(e.uid, e.auth.claims, e.lease)
        return original(*args, **kwargs)

    monkeypatch.setattr(e.db.users, "find_one_and_update", interleave)
    assert e.post("heartbeat").get_json()["user"]["is_online"] is False
    assert e.document()["presence_sessions"][0]["closed"] is True


def test_concurrent_new_lease_is_not_lost_by_old_cleanup(environment, monkeypatch):
    e = environment
    e.post("heartbeat")
    original = e.db.users.find_one_and_update
    pending = True
    fresh_lease = str(uuid4())

    def interleave(*args, **kwargs):
        nonlocal pending
        if pending:
            pending = False
            presence_service.heartbeat(e.uid, e.auth.claims, fresh_lease)
        return original(*args, **kwargs)

    monkeypatch.setattr(e.db.users, "find_one_and_update", interleave)
    assert e.post("offline").status_code == 200
    assert e.document()["is_online"] is True
    assert len(e.document()["presence_sessions"]) == 2


@pytest.mark.parametrize("action", ["heartbeat", "offline"])
def test_a_password_reset_between_authentication_and_write_rejects_stale_presence(environment, monkeypatch, action):
    e = environment
    e.post("heartbeat")
    original = e.db.users.find_one_and_update
    pending = True

    def interleave(*args, **kwargs):
        nonlocal pending
        if pending:
            pending = False
            e.db.users.update_one({"_id": ObjectId(e.uid)},
                                  {"$inc": {"session_version": 1}, "$set": {"is_online": False}})
        return original(*args, **kwargs)

    monkeypatch.setattr(e.db.users, "find_one_and_update", interleave)
    assert e.post(action).status_code == 401
    assert e.document()["is_online"] is False
    fresh = e.login_token(version=1)
    assert e.post("heartbeat", str(uuid4()), fresh).get_json()["user"]["is_online"] is True
    assert all(lease["session_version"] == 1 for lease in e.document()["presence_sessions"])


@pytest.mark.parametrize("action", ["heartbeat", "offline"])
@pytest.mark.parametrize("session", ["", "bad-id", "x" * 100, 42, [], {}])
def test_malformed_presence_session_ids_return_bad_request_without_writes(environment, action, session):
    e = environment
    before = e.document()
    assert e.post(action, session).status_code == 400
    assert e.document() == before


@pytest.mark.parametrize("payload", ["[]", "null", "123", "{broken"])
def test_non_object_json_is_rejected(environment, payload):
    e = environment
    response = e.client.post("/api/presence/heartbeat", headers=e.auth.headers,
                             data=payload, content_type="application/json")
    assert response.status_code == 400


def test_stale_other_leases_do_not_keep_user_online_or_extend_last_seen(environment):
    e = environment
    e.post("heartbeat")
    stale = datetime.now(timezone.utc) - timedelta(minutes=2)
    e.db.users.update_one({"_id": ObjectId(e.uid)}, {"$set": {
        "presence_sessions.0.last_seen": stale, "last_seen": stale}})
    assert e.post("offline", str(uuid4())).status_code == 200
    assert e.document()["is_online"] is False


def test_session_storage_is_bounded_and_expired_slots_are_reclaimed(environment, monkeypatch):
    e = environment
    monkeypatch.setattr(presence_service, "MAX_PRESENCE_SESSIONS", 2)
    e.post("heartbeat")
    e.post("offline")
    second = str(uuid4())
    assert e.post("heartbeat", second).status_code == 200
    assert e.post("heartbeat", str(uuid4())).status_code == 429
    assert e.post("offline", second).status_code == 200
    e.db.users.update_one({"_id": ObjectId(e.uid)}, {"$set": {
        "presence_sessions.0.expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}})
    assert e.post("heartbeat", str(uuid4())).status_code == 200
    assert len(e.document()["presence_sessions"]) == 2


def test_legacy_tokens_and_clients_still_work(environment):
    e = environment
    e.db.users.update_one({"_id": ObjectId(e.uid)}, {"$unset": {"session_version": ""}})
    for action in ("heartbeat", "offline", "heartbeat"):
        response = e.post(action, None)
        assert response.status_code == 200
        assert e.document()["is_online"] is (action == "heartbeat")


def test_internal_presence_fields_are_not_serialized(environment):
    response = environment.post("heartbeat").get_json()["user"]
    assert "presence_sessions" not in response
    assert "presence_revision" not in response
    assert "session_version" not in response


def test_contention_returns_a_retryable_error_without_mutating_presence(environment, monkeypatch):
    e = environment
    monkeypatch.setattr(e.db.users, "find_one_and_update", lambda *args, **kwargs: None)
    assert e.post("heartbeat").status_code == 503
    assert e.document()["is_online"] is False
