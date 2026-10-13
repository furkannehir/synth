"""Renewal, logout and password-reset regressions with an isolated database."""
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import bcrypt
import mongomock
import pytest
from bson import ObjectId
from flask import Flask
from flask_jwt_extended import decode_token
from flask_smorest import Api

from app.extensions import jwt, mongo
from app.models import desktop_session, user
from app.services import auth_service


@pytest.fixture
def env(monkeypatch):
    db = mongomock.MongoClient(tz_aware=True).desktop_session_tests
    monkeypatch.setattr(mongo, "db", db)
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="desktop-tests-signing-key-32-bytes-long",
                      API_TITLE="Tests", API_VERSION="v1", OPENAPI_VERSION="3.0.3",
                      JWT_ACCESS_TOKEN_EXPIRES=timedelta(hours=24))
    jwt.init_app(app)
    from app.routes.auth import blp
    Api(app).register_blueprint(blp)
    user.ensure_indexes()
    desktop_session.ensure_indexes()
    salt = bcrypt.gensalt(rounds=4)
    monkeypatch.setattr(auth_service.bcrypt, "gensalt", lambda: salt)
    uid = user.create("tester", "test@example.com", bcrypt.hashpw(b"test-password", salt).decode())
    client = app.test_client()
    def login(persistent=True):
        result = client.post("/api/auth/login", json={
            "email": "test@example.com", "password": "test-password", "persistent": persistent,
        })
        assert result.status_code == 200
        return result.get_json()
    return SimpleNamespace(app=app, db=db, client=client, uid=uid, login=login)


def pair(token):
    return {"refresh_token": token, "next_refresh_token": f'{token.split(".")[0]}.{secrets.token_urlsafe(32)}'}


def headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_browser_login_retains_existing_lifetime_and_contract(env):
    data = env.login(False)
    assert "refresh_token" not in data and "revocation_token" not in data
    with env.app.app_context():
        claims = decode_token(data["access_token"])
    assert claims["exp"] - claims["iat"] == 86400
    assert "desktop_session" not in claims


def test_desktop_session_uses_short_access_tokens_and_hashed_credentials(env):
    data = env.login()
    with env.app.app_context():
        claims = decode_token(data["access_token"])
    assert claims["exp"] - claims["iat"] == 900
    saved = env.db.desktop_sessions.find_one({"_id": claims["desktop_session"]})
    assert saved["refresh_hash"] != data["refresh_token"]
    assert saved["revocation_hash"] != data["revocation_token"]
    assert data["refresh_token"] not in str(saved)
    assert env.client.get("/api/auth/me", headers=headers(data["access_token"])).status_code == 200


def test_rotation_can_recover_the_exact_request_after_a_lost_response(env):
    data = env.login()
    request = pair(data["refresh_token"])
    for _ in range(2):
        result = env.client.post("/api/auth/refresh", json=request)
        assert result.status_code == 200
        assert result.get_json()["refresh_token"] == request["next_refresh_token"]
    result = env.client.post("/api/auth/refresh", json=pair(request["next_refresh_token"]))
    assert result.status_code == 200


def test_replaying_consumed_token_with_a_different_replacement_revokes_session(env):
    data = env.login()
    assert env.client.post("/api/auth/refresh", json=pair(data["refresh_token"])).status_code == 200
    assert env.client.post("/api/auth/refresh", json=pair(data["refresh_token"])).status_code == 401
    assert env.client.get("/api/auth/me", headers=headers(data["access_token"])).status_code == 401


def test_random_wrong_secret_cannot_revoke_someone_elses_session(env):
    data = env.login()
    wrong = pair(data["refresh_token"])["next_refresh_token"]
    assert env.client.post("/api/auth/refresh", json=pair(wrong)).status_code == 401
    assert env.client.post("/api/auth/logout", json={"revocation_token": wrong}).status_code == 200
    assert env.client.get("/api/auth/me", headers=headers(data["access_token"])).status_code == 200


def test_logout_revokes_access_and_refresh_without_affecting_another_login(env):
    first, second = env.login(), env.login()
    assert env.client.post("/api/auth/logout", json={"revocation_token": first["revocation_token"]}).status_code == 200
    assert env.client.get("/api/auth/me", headers=headers(first["access_token"])).status_code == 401
    assert env.client.post("/api/auth/refresh", json=pair(first["refresh_token"])).status_code == 401
    assert env.client.get("/api/auth/me", headers=headers(second["access_token"])).status_code == 200


@pytest.mark.parametrize("field", ["expires_at", "absolute_expires_at"])
def test_expired_persistent_session_rejects_access_and_renewal(env, field):
    data = env.login()
    env.db.desktop_sessions.update_many({}, {"$set": {field: datetime.now(timezone.utc) - timedelta(seconds=1)}})
    assert env.client.post("/api/auth/refresh", json=pair(data["refresh_token"])).status_code == 401
    assert env.client.get("/api/auth/me", headers=headers(data["access_token"])).status_code == 401


def test_password_reset_invalidates_persistent_sessions(env):
    data = env.login()
    env.db.users.update_one({"_id": ObjectId(env.uid)}, {"$inc": {"session_version": 1}})
    assert env.client.post("/api/auth/refresh", json=pair(data["refresh_token"])).status_code == 401
    assert env.client.get("/api/auth/me", headers=headers(data["access_token"])).status_code == 401


def test_reset_during_token_minting_cannot_renew_into_the_new_password_session(env, monkeypatch):
    data = env.login()
    from app.routes import auth
    mint = auth.create_access_token
    def reset_then_mint(*args, **kwargs):
        env.db.users.update_one({"_id": ObjectId(env.uid)}, {"$inc": {"session_version": 1}})
        return mint(*args, **kwargs)
    monkeypatch.setattr(auth, "create_access_token", reset_then_mint)
    response = env.client.post("/api/auth/refresh", json=pair(data["refresh_token"]))
    assert response.status_code == 200
    renewed = response.get_json()["access_token"]
    with env.app.app_context():
        assert decode_token(renewed)["session_version"] == 0
    assert env.client.get("/api/auth/me", headers=headers(renewed)).status_code == 401


def test_renewal_never_extends_the_absolute_session_lifetime(env):
    data = env.login()
    absolute = datetime.now(timezone.utc) + timedelta(hours=2)
    env.db.desktop_sessions.update_many({}, {"$set": {"absolute_expires_at": absolute}})
    assert env.client.post("/api/auth/refresh", json=pair(data["refresh_token"])).status_code == 200
    saved = env.db.desktop_sessions.find_one()
    assert saved["expires_at"] == saved["absolute_expires_at"]


def test_parallel_identical_renewals_are_idempotent_across_workers(env):
    data = env.login()
    request = pair(data["refresh_token"])
    def renew(_):
        with env.app.app_context():
            return desktop_session.rotate(**{ "refresh": request["refresh_token"], "next_refresh": request["next_refresh_token"] })["refresh_hash"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(renew, range(8)))
    assert len(set(results)) == 1


@pytest.mark.parametrize("token", ["", "garbage", "../credentials", "a" * 200])
def test_malformed_refresh_credentials_do_not_raise_internal_errors(env, token):
    assert env.client.post("/api/auth/refresh", json={"refresh_token": token, "next_refresh_token": token}).status_code in (401, 422)
