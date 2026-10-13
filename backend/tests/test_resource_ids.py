"""Malformed route IDs must never reach BSON conversions or mutate data."""
from types import SimpleNamespace

import mongomock
import pytest
from bson import ObjectId
from flask import Flask
from flask_jwt_extended import create_access_token
from flask_smorest import Api

from app.extensions import jwt, mongo
from app.models import channel, friend_request, message, role, user
from app.realtime import ChannelEventBus
from app.services import channel_service, friendship_service, message_service, server_service


@pytest.fixture
def environment(monkeypatch):
    db = mongomock.MongoClient(tz_aware=True).resource_id_tests
    monkeypatch.setattr(mongo, "db", db)
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="resource-id-tests-signing-key-32-bytes",
                      API_TITLE="Tests", API_VERSION="v1", OPENAPI_VERSION="3.0.3")
    jwt.init_app(app)
    api = Api(app)
    from app.routes import channels, friends, invites, messages, roles, servers, voice
    for module in (channels, friends, invites, messages, roles, servers, voice):
        api.register_blueprint(module.blp)
    bus = ChannelEventBus()
    monkeypatch.setattr(messages, "channel_event_bus", bus)
    role.ensure_indexes()

    def make_user(name):
        uid = user.create(name, f"{name}@example.test", "private-hash")
        with app.app_context():
            token = create_access_token(identity=uid)
        return SimpleNamespace(id=uid, headers={"Authorization": f"Bearer {token}"})

    owner, member, outsider = [make_user(name) for name in ("owner", "member", "outsider")]
    sid = server_service.create_server("Server", owner.id)["id"]
    server_service.join_server(sid, member.id)
    cid = channel.create("chat", sid, "text")
    vid = channel.create("voice", sid, "voice")
    mid = message.create(cid, owner.id, "original")
    rid = role.create("Custom role", [], sid)
    req = friend_request.create(outsider.id, owner.id)
    return SimpleNamespace(db=db, app=app, client=app.test_client(), server=sid, channel=cid,
                           voice=vid, message=mid, role=rid, request=req, bus=bus,
                           owner=owner, member=member, outsider=outsider)


CASES = [
    ("GET", "/servers/{bad}", None),
    ("PUT", "/servers/{bad}", {"name": "Updated"}),
    ("DELETE", "/servers/{bad}", None),
    ("POST", "/servers/{bad}/join", None),
    ("POST", "/servers/{bad}/leave", None),
    ("GET", "/servers/{bad}/members", None),
    ("GET", "/servers/{bad}/members/stream", None),
    ("GET", "/servers/{bad}/channels", None),
    ("POST", "/servers/{bad}/channels", {"name": "new channel"}),
    ("GET", "/servers/{server}/channels/{bad}", None),
    ("PUT", "/servers/{server}/channels/{bad}", {"name": "Updated"}),
    ("DELETE", "/servers/{server}/channels/{bad}", None),
    ("GET", "/servers/{bad}/roles", None),
    ("POST", "/servers/{bad}/roles", {"name": "new role"}),
    ("GET", "/servers/{bad}/roles/permissions", None),
    ("GET", "/servers/{server}/roles/{bad}", None),
    ("PUT", "/servers/{server}/roles/{bad}", {"name": "Updated"}),
    ("DELETE", "/servers/{server}/roles/{bad}", None),
    ("GET", "/servers/{server}/roles/user/{bad}", None),
    ("GET", "/servers/{bad}/invites", None),
    ("POST", "/servers/{bad}/invites", {}),
    ("GET", "/channels/{bad}/messages", None),
    ("POST", "/channels/{bad}/messages", {"content": "hello"}),
    ("GET", "/channels/{bad}/messages/events", None),
    ("PATCH", "/channels/{bad}/messages/{message}", {"content": "updated"}),
    ("DELETE", "/channels/{bad}/messages/{message}", None),
    ("PATCH", "/channels/{channel}/messages/{bad}", {"content": "updated"}),
    ("DELETE", "/channels/{channel}/messages/{bad}", None),
    ("POST", "/friends/{bad}/accept", None),
    ("POST", "/friends/{bad}/reject", None),
    ("POST", "/friends/{bad}/cancel", None),
    ("DELETE", "/friends/{bad}", None),
    ("POST", "/servers/{server}/channels/{bad}/voice/join", None),
    ("POST", "/servers/{server}/channels/{bad}/voice/leave", None),
    ("GET", "/servers/{server}/channels/{bad}/voice/participants", None),
    ("DELETE", "/servers/{server}/channels/{bad}/voice/participants/opaque.identity", None),
    ("POST", "/servers/{server}/channels/{bad}/voice/participants/opaque.identity/mute",
     {"track_sid": "opaque-track"}),
]


@pytest.mark.parametrize("bad", ["not-an-id", "z" * 24, "000000000000000000000000"])
@pytest.mark.parametrize("method,path,payload", CASES)
def test_invalid_or_missing_resources_return_json_not_found_without_writes(environment, bad, method, path, payload):
    e = environment
    before = {name: list(e.db[name].find()) for name in e.db.list_collection_names()}
    url = "/api" + path.format(bad=bad, **vars(e))
    response = e.client.open(url, method=method, json=payload, headers=e.owner.headers)
    assert response.status_code == 404
    assert isinstance(response.get_json().get("error"), str)
    assert {name: list(e.db[name].find()) for name in e.db.list_collection_names()} == before


@pytest.mark.parametrize("action", ["assign", "revoke"])
@pytest.mark.parametrize("parameter", ["role_id", "user_id"])
def test_invalid_body_ids_are_controlled_not_found_errors(environment, action, parameter):
    e = environment
    payload = {"role_id": e.role, "user_id": e.member.id, parameter: "bad-id"}
    response = e.client.post(f"/api/servers/{e.server}/roles/{action}", json=payload, headers=e.owner.headers)
    assert response.status_code == 404


def test_authentication_precedes_id_validation(environment):
    response = environment.client.delete("/api/channels/bad-id/messages/bad-id")
    assert response.status_code == 401


def test_permissions_list_requires_a_real_server_and_membership(environment):
    e = environment
    assert e.client.get(f"/api/servers/{e.server}/roles/permissions", headers=e.outsider.headers).status_code == 403
    assert e.client.get(f"/api/servers/{e.server}/roles/permissions", headers=e.member.headers).status_code == 200


def test_uppercase_ids_resolve_and_publish_on_the_canonical_channel_topic(environment):
    e = environment
    response = e.client.get(f"/api/servers/{e.server.upper()}/channels/{e.channel.upper()}", headers=e.member.headers)
    assert response.status_code == 200
    assert response.get_json()["channel"]["id"] == e.channel
    response = e.client.patch(f"/api/channels/{e.channel.upper()}/messages/{e.message.upper()}",
                              json={"content": "updated"}, headers=e.owner.headers)
    assert response.status_code == 200
    journal = e.db.realtime_streams.find_one({"_id": f"channel:{e.channel}"})
    assert journal is not None
    assert response.get_json()["message"]["id"] == e.message
    response = e.client.delete(f"/api/channels/{e.channel.upper()}/messages/{e.message.upper()}", headers=e.owner.headers)
    assert response.status_code == 200
    assert message.find_by_id(e.message) is None


def test_uppercase_friend_ids_remove_both_sides(environment):
    e = environment
    user.add_friend(e.owner.id, e.member.id)
    response = e.client.delete(f"/api/friends/{e.member.id.upper()}", headers=e.owner.headers)
    assert response.status_code == 200
    assert not user.are_friends(e.owner.id, e.member.id)
    assert not user.are_friends(e.member.id, e.owner.id)


@pytest.mark.parametrize("lookup", [channel.find_by_id, message.find_by_id, user.find_by_id, friend_request.find_by_id])
@pytest.mark.parametrize("bad", [None, {}, "bad-id"])
def test_model_lookups_are_safe_for_service_callers(environment, lookup, bad):
    assert lookup(bad) is None


def test_services_validate_ids_without_route_decorators(environment):
    e = environment
    with pytest.raises(channel_service.ChannelError) as exc:
        channel_service.get_channel("bad-id", e.server, e.owner.id)
    assert exc.value.status_code == 404
    with pytest.raises(message_service.MessageError) as exc:
        message_service.edit_message("bad-id", e.channel, e.owner.id, "updated")
    assert exc.value.status_code == 404
    with pytest.raises(friendship_service.FriendshipError) as exc:
        friendship_service.remove_friend(e.owner.id, "bad-id")
    assert exc.value.status_code == 404
