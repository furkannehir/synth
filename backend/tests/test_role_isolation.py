"""Role API and migration regressions using an isolated, in-memory database."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from types import SimpleNamespace

import mongomock
import pytest
from bson import ObjectId
from flask import Flask
from flask_jwt_extended import create_access_token
from flask_smorest import Api

from app.extensions import jwt, mongo
from app.models import role as role_model
from app.models import server as server_model
from app.models import user as user_model
from app.services import role_service, server_service


@pytest.fixture
def database(monkeypatch):
    db = mongomock.MongoClient(tz_aware=True).synth_role_tests
    monkeypatch.setattr(mongo, "db", db)
    return db


def make_user(app, name):
    user_id = user_model.create(name, f"{name}@example.test", "unused-test-hash")
    with app.app_context():
        token = create_access_token(identity=user_id)
    return SimpleNamespace(id=user_id, headers={"Authorization": f"Bearer {token}"})


@pytest.fixture
def environment(database):
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        JWT_SECRET_KEY="isolated-role-security-test-key-only",
        API_TITLE="Role security tests", API_VERSION="v1", OPENAPI_VERSION="3.0.3",
    )
    jwt.init_app(app)
    api = Api(app)
    from app.routes.auth import blp as auth_blp
    from app.routes.roles import blp as roles_blp
    from app.routes.servers import blp as servers_blp
    from app.routes.channels import blp as channels_blp
    from app.routes.invites import blp as invites_blp
    for blueprint in (auth_blp, roles_blp, servers_blp, channels_blp, invites_blp):
        api.register_blueprint(blueprint)

    user_model.ensure_indexes()
    server_model.ensure_indexes()
    role_model.ensure_indexes()
    owner_a = make_user(app, "owner_a")
    owner_b = make_user(app, "owner_b")
    member = make_user(app, "member")
    outsider = make_user(app, "outsider")
    a = server_service.create_server("Server A", owner_a.id)["id"]
    b = server_service.create_server("Server B", owner_b.id)["id"]
    server_service.join_server(a, member.id)
    server_service.join_server(b, member.id)
    return SimpleNamespace(
        app=app, client=app.test_client(), db=database,
        a=a, b=b, owner_a=owner_a, owner_b=owner_b, member=member, outsider=outsider,
    )


def roles_url(server_id):
    return f"/api/servers/{server_id}/roles"


def state(db):
    return (
        list(db.roles.find().sort("_id")),
        list(db.user_roles.find().sort("_id")),
    )


@pytest.mark.parametrize("role_name", ["member", "vip"])
@pytest.mark.parametrize("operation", ["read", "update", "delete", "assign", "revoke"])
def test_owner_cannot_access_another_servers_role(environment, role_name, operation):
    e = environment
    if role_name == "vip":
        role = role_service.create_role("vip", ["speak"], e.b)
        role_service.assign_role_to_user(e.member.id, role["id"], e.b)
        role_id = role["id"]
    else:
        role_id = str(role_model.find_by_name(role_name, e.b)["_id"])
    before = state(e.db)
    url = f"{roles_url(e.a)}/{role_id}"
    if operation == "read":
        response = e.client.get(url, headers=e.owner_a.headers)
    elif operation == "update":
        response = e.client.put(url, headers=e.owner_a.headers, json={
            "permissions": role_model.ALL_PERMISSIONS, "is_default": True,
        })
    elif operation == "delete":
        response = e.client.delete(url, headers=e.owner_a.headers)
    else:
        response = e.client.post(
            f"{roles_url(e.a)}/{operation}", headers=e.owner_a.headers,
            json={"user_id": e.member.id, "role_id": role_id},
        )
    assert response.status_code == 404
    assert state(e.db) == before


def test_role_names_and_lists_are_local(environment):
    e = environment
    first = role_service.create_role("vip", ["speak"], e.a)
    second = role_service.create_role("vip", ["mute_user"], e.b)
    assert first["id"] != second["id"]
    for server_id, owner, own, other in (
        (e.a, e.owner_a, first, second), (e.b, e.owner_b, second, first),
    ):
        response = e.client.get(roles_url(server_id), headers=owner.headers)
        assert response.status_code == 200
        roles = response.get_json()["roles"]
        assert all(role["server_id"] == server_id for role in roles)
        assert own["id"] in {role["id"] for role in roles}
        assert other["id"] not in {role["id"] for role in roles}
        duplicate = e.client.post(roles_url(server_id), headers=owner.headers,
                                  json={"name": "vip", "permissions": []})
        assert duplicate.status_code == 409


def test_editing_own_builtin_does_not_change_other_server(environment):
    e = environment
    role_id = str(role_model.find_by_name("member", e.a)["_id"])
    before_b = deepcopy(role_model.find_all(e.b))
    response = e.client.put(f"{roles_url(e.a)}/{role_id}", headers=e.owner_a.headers,
                            json={"permissions": ["join_channel", "manage_roles"]})
    assert response.status_code == 200
    assert "manage_roles" in role_model.get_user_permissions(e.member.id, e.a)
    assert "manage_roles" not in role_model.get_user_permissions(e.member.id, e.b)
    assert role_model.find_all(e.b) == before_b
    role_model.seed_defaults(e.a)
    assert "manage_roles" in role_model.get_user_permissions(e.member.id, e.a)


@pytest.mark.parametrize("default_operation", ["create", "update"])
@pytest.mark.parametrize("join_method", ["direct", "invite"])
def test_changing_default_affects_only_its_server(environment, default_operation, join_method):
    e = environment
    before_b = deepcopy(role_model.find_all(e.b))
    payload = {"name": "newcomer", "permissions": ["manage_roles"],
               "is_default": default_operation == "create"}
    response = e.client.post(roles_url(e.a), headers=e.owner_a.headers, json=payload)
    assert response.status_code == 201
    new_role = response.get_json()["role"]
    if default_operation == "update":
        response = e.client.put(f"{roles_url(e.a)}/{new_role['id']}",
                                headers=e.owner_a.headers, json={"is_default": True})
        assert response.status_code == 200
    assert str(role_model.get_default_role(e.a)["_id"]) == new_role["id"]
    assert role_model.find_all(e.b) == before_b

    joiner = make_user(e.app, "joiner")
    for server_id, owner in ((e.a, e.owner_a), (e.b, e.owner_b)):
        if join_method == "direct":
            response = e.client.post(f"/api/servers/{server_id}/join", headers=joiner.headers)
        else:
            invite = e.client.post(f"/api/servers/{server_id}/invites",
                                   headers=owner.headers, json={}).get_json()["invite"]
            response = e.client.post(f"/api/invites/{invite['code']}/accept",
                                     headers=joiner.headers)
        assert response.status_code == 200
    assert role_model.get_user_permissions(joiner.id, e.a) == {"manage_roles"}
    assert role_model.get_user_permissions(joiner.id, e.b) == {"join_channel", "speak", "send_messages"}


@pytest.mark.parametrize("operation", ["list", "read", "user_roles", "create", "assign", "revoke"])
def test_nonmember_cannot_use_roles_api(environment, operation):
    e = environment
    role_id = str(role_model.find_by_name("admin", e.a)["_id"])
    # Even a stale/corrupt local assignment must not bypass server membership.
    e.db.user_roles.insert_one({"user_id": ObjectId(e.outsider.id),
                               "role_id": ObjectId(role_id), "server_id": ObjectId(e.a)})
    url = roles_url(e.a)
    if operation == "list":
        response = e.client.get(url, headers=e.outsider.headers)
    elif operation == "read":
        response = e.client.get(f"{url}/{role_id}", headers=e.outsider.headers)
    elif operation == "user_roles":
        response = e.client.get(f"{url}/user/{e.member.id}", headers=e.outsider.headers)
    elif operation == "create":
        response = e.client.post(url, headers=e.outsider.headers,
                                 json={"name": "exploit", "permissions": []})
    else:
        response = e.client.post(f"{url}/{operation}", headers=e.outsider.headers,
                                 json={"user_id": e.member.id, "role_id": role_id})
    assert response.status_code == 403


@pytest.mark.parametrize("operation", ["assign", "revoke"])
def test_cannot_grant_roles_to_nonmembers(environment, operation):
    e = environment
    role_id = str(role_model.find_by_name("admin", e.a)["_id"])
    before = state(e.db)
    response = e.client.post(f"{roles_url(e.a)}/{operation}", headers=e.owner_a.headers,
                             json={"user_id": e.outsider.id, "role_id": role_id})
    assert response.status_code == 403
    assert state(e.db) == before


@pytest.mark.parametrize("legacy", [False, True])
def test_bad_assignments_never_import_permissions(environment, legacy):
    e = environment
    if legacy:
        role_id = e.db.roles.insert_one({"name": "legacy_admin", "permissions": role_model.ALL_PERMISSIONS}).inserted_id
    else:
        role_id = role_model.find_by_name("admin", e.b)["_id"]
    e.db.user_roles.insert_one({"user_id": ObjectId(e.member.id), "role_id": role_id,
                               "server_id": ObjectId(e.a)})
    assert role_model.get_user_permissions(e.member.id, e.a) == {"join_channel", "speak", "send_messages"}
    assert role_id not in {role["_id"] for role in role_model.get_user_roles(e.member.id)}
    response = e.client.post(roles_url(e.a), headers=e.member.headers,
                             json={"name": "exploit", "permissions": []})
    assert response.status_code == 403


def test_model_mutations_also_enforce_role_scope(environment):
    e = environment
    role_id = str(role_model.find_by_name("admin", e.b)["_id"])
    before = state(e.db)
    assert role_model.update(role_id, e.a, {"permissions": []}) is None
    role_model.delete(role_id, e.a)
    assert role_model.assign_role(e.member.id, role_id, e.a) is False
    role_model.revoke_role(e.member.id, role_id, e.a)
    assert state(e.db) == before


@pytest.mark.parametrize("method", ["post", "put"])
def test_api_payload_cannot_forge_role_scope_or_builtin_status(environment, method):
    e = environment
    url = roles_url(e.a)
    if method == "put":
        role = role_service.create_role("vip", ["speak"], e.a)
        url += f"/{role['id']}"
    before = state(e.db)
    response = getattr(e.client, method)(url, headers=e.owner_a.headers, json={
        "name": "forged", "permissions": [], "server_id": e.b, "is_builtin": True,
    })
    assert response.status_code == 422
    assert state(e.db) == before


def test_model_update_cannot_move_role_to_another_server(environment):
    e = environment
    role = role_service.create_role("vip", ["speak"], e.a)
    before = state(e.db)
    role_model.update(role["id"], e.a, {"server_id": ObjectId(e.b), "is_builtin": True})
    assert state(e.db) == before


def test_own_custom_role_lifecycle_still_works(environment):
    e = environment
    response = e.client.post(roles_url(e.a), headers=e.owner_a.headers,
                             json={"name": "vip", "permissions": ["mute_user"]})
    role_id = response.get_json()["role"]["id"]
    for operation in ("assign", "assign", "revoke", "assign"):
        response = e.client.post(f"{roles_url(e.a)}/{operation}", headers=e.owner_a.headers,
                                 json={"user_id": e.member.id, "role_id": role_id})
        assert response.status_code == 200
    assert "mute_user" in role_model.get_user_permissions(e.member.id, e.a)
    assert "mute_user" not in role_model.get_user_permissions(e.member.id, e.b)
    response = e.client.delete(f"{roles_url(e.a)}/{role_id}", headers=e.owner_a.headers)
    assert response.status_code == 200
    assert "mute_user" not in role_model.get_user_permissions(e.member.id, e.a)


@pytest.mark.parametrize("operation", ["rename", "delete"])
def test_builtin_identity_is_protected(environment, operation):
    e = environment
    role_id = str(role_model.find_by_name("admin", e.a)["_id"])
    url = f"{roles_url(e.a)}/{role_id}"
    if operation == "rename":
        response = e.client.put(url, headers=e.owner_a.headers, json={"name": "renamed"})
    else:
        response = e.client.delete(url, headers=e.owner_a.headers)
    assert response.status_code == 403


def legacy_state(db):
    owner, member, stranger = ObjectId(), ObjectId(), ObjectId()
    servers = [db.servers.insert_one({"name": name, "owner_id": owner,
                                     "members": [owner, member]}).inserted_id
               for name in ("A", "B", "C")]
    db.roles.create_index("name", unique=True)
    legacy_member = db.roles.insert_one({"name": "member", "permissions": role_model.ALL_PERMISSIONS,
                                        "is_default": False}).inserted_id
    legacy_admin = db.roles.insert_one({"name": "admin", "permissions": [], "is_default": False}).inserted_id
    legacy_custom = db.roles.insert_one({"name": "vip", "permissions": ["mute_user"],
                                        "is_default": True}).inserted_id
    for server_id in servers:
        db.user_roles.insert_many([
            {"user_id": member, "role_id": legacy_member, "server_id": server_id},
            {"user_id": owner, "role_id": legacy_admin, "server_id": server_id},
        ])
    for server_id in servers[:2]:
        db.user_roles.insert_one({"user_id": member, "role_id": legacy_custom, "server_id": server_id})
    db.user_roles.insert_one({"user_id": stranger, "role_id": legacy_custom, "server_id": servers[0]})
    return SimpleNamespace(servers=servers, member=member, owner=owner, stranger=stranger,
                           legacy_member=legacy_member, legacy_custom=legacy_custom)


def test_migration_preserves_assignments_and_rebuilds_safe_defaults(database):
    old = legacy_state(database)
    role_model.ensure_indexes()
    role_model.migrate_legacy_roles()
    assert "name_1" not in database.roles.index_information()
    for server_id in old.servers:
        sid = str(server_id)
        assert role_model.get_default_role(sid)["name"] == "member"
        assert set(role_model.find_by_name("member", sid)["permissions"]) == {"join_channel", "speak", "send_messages"}
        assert role_model.get_user_permissions(str(old.owner), sid) == set(role_model.ALL_PERMISSIONS)
        assert "manage_roles" not in role_model.get_user_permissions(str(old.member), sid)
    assert role_model.find_by_name("vip", str(old.servers[2])) is None
    first_vip = role_model.find_by_name("vip", str(old.servers[0]))
    second_vip = role_model.find_by_name("vip", str(old.servers[1]))
    assert first_vip["_id"] != second_vip["_id"]
    assert first_vip["permissions"] == ["mute_user"]
    assert role_model.get_user_permissions(str(old.stranger), str(old.servers[0])) == set()
    assert role_model.find_by_id(str(old.legacy_member), str(old.servers[0])) is None
    before = state(database)
    role_model.ensure_indexes()
    role_model.migrate_legacy_roles()
    assert state(database) == before


def test_interrupted_migration_is_retryable(database, monkeypatch):
    old = legacy_state(database)
    role_model.ensure_indexes()
    with monkeypatch.context() as patch:
        def interrupt(*args, **kwargs):
            raise RuntimeError("interrupted after copying assignment")
        patch.setattr(database.user_roles, "delete_one", interrupt)
        with pytest.raises(RuntimeError, match="interrupted"):
            role_model.migrate_legacy_roles()
    role_model.migrate_legacy_roles()
    for server_id in old.servers:
        role_id = role_model.find_by_name("member", str(server_id))["_id"]
        assert database.user_roles.count_documents({"user_id": old.member, "role_id": role_id,
                                                    "server_id": server_id}) == 1


def test_concurrent_seeding_creates_one_set_of_roles(database):
    server_id = str(ObjectId())
    role_model.ensure_indexes()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(role_model.seed_defaults, [server_id] * 20))
    assert len(role_model.find_all(server_id)) == 3
    assert database.roles.count_documents({"server_id": ObjectId(server_id), "is_default": True}) == 1


def test_factory_migrates_existing_database(database, monkeypatch):
    old = legacy_state(database)
    from app import create_app
    from app.config import TestingConfig
    monkeypatch.setattr(mongo, "init_app", lambda app: None)
    monkeypatch.setattr(TestingConfig, "MONGO_URI", "mongodb://localhost:27017/isolated_role_tests")
    monkeypatch.setattr("app.adapters.create_media_server_adapter", lambda app: None)
    monkeypatch.setattr("threading.Thread.start", lambda thread: None)
    app = create_app("testing")
    assert app.testing
    assert role_model.get_default_role(str(old.servers[0]))["name"] == "member"
    default_server = server_model.find_default()
    assert len(role_model.find_all(str(default_server["_id"]))) == 3
