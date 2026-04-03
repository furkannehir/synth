"""Smoke tests for the invite system."""
import sys
import os
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))

from app import create_app
from app.extensions import mongo

app = create_app("development")
client = app.test_client()

# ── Cleanup ─────────────────────────────────────────────────
INV_TEST_EMAILS = ["inv_owner@test.com", "inv_joiner@test.com", "inv_other@test.com"]

with app.app_context():
    test_users = [u["_id"] for u in mongo.db.users.find({"email": {"$in": INV_TEST_EMAILS}}, {"_id": 1})]
    test_servers = [s["_id"] for s in mongo.db.servers.find({"name": "InviteTestServer"}, {"_id": 1})]
    mongo.db.user_roles.delete_many({"user_id": {"$in": test_users}})
    mongo.db.invites.delete_many({"server_id": {"$in": test_servers}})
    mongo.db.users.delete_many({"email": {"$in": INV_TEST_EMAILS}})
    mongo.db.servers.delete_many({"name": "InviteTestServer"})


# ── Helpers ─────────────────────────────────────────────────
def register(username, email, password):
    r = client.post("/api/auth/register", json={
        "username": username, "email": email, "password": password,
    })
    assert r.status_code == 201, f"Register failed: {r.get_json()}"
    return r.get_json()


def headers(token):
    return {"Authorization": f"Bearer {token}"}


def set_invite_expiry(code, expires_at):
    with app.app_context():
        mongo.db.invites.update_one({"code": code}, {"$set": {"expires_at": expires_at}})


def cleanup_user(email):
    with app.app_context():
        user_ids = [u["_id"] for u in mongo.db.users.find({"email": email}, {"_id": 1})]
        if user_ids:
            mongo.db.user_roles.delete_many({"user_id": {"$in": user_ids}})
        mongo.db.users.delete_many({"email": email})


# ── Setup users ─────────────────────────────────────────────
owner = register("inv_owner", "inv_owner@test.com", "password123")
owner_token = owner["access_token"]

joiner = register("inv_joiner", "inv_joiner@test.com", "password123")
joiner_token = joiner["access_token"]

other = register("inv_other", "inv_other@test.com", "password123")
other_token = other["access_token"]

# ── Create a test server ────────────────────────────────────
r = client.post("/api/servers", headers=headers(owner_token), json={
    "name": "InviteTestServer",
})
assert r.status_code == 201
server = r.get_json()["server"]
server_id = server["id"]

passed = 0
failed = 0


def test(name, fn):
    global passed, failed
    print(f"{'=' * 60}")
    print(f"  {name}")
    print(f"{'=' * 60}")
    try:
        fn()
        print("  ✅ PASSED")
        passed += 1
    except AssertionError as e:
        print(f"  ❌ FAILED: {e}")
        failed += 1
    print()


# ═══════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════

invite_code = None


def test_create_invite():
    global invite_code
    r = client.post(
        f"/api/servers/{server_id}/invites",
        headers=headers(owner_token),
        json={},
    )
    assert r.status_code == 201, f"Expected 201 got {r.status_code}: {r.get_json()}"
    data = r.get_json()
    assert "invite" in data
    inv = data["invite"]
    assert inv["server_id"] == server_id
    assert inv["code"]
    assert inv["uses"] == 0
    invite_code = inv["code"]
    print(f"   Invite code: {invite_code}")

test("1) Owner creates invite", test_create_invite)


def test_preview_invite():
    r = client.get(f"/api/invites/{invite_code}")
    assert r.status_code == 200, f"Expected 200 got {r.status_code}"
    data = r.get_json()["invite"]
    assert data["server_name"] == "InviteTestServer"
    assert data["member_count"] is not None
    print(f"   Server: {data['server_name']}, Members: {data['member_count']}")

test("2) Preview invite (no auth needed)", test_preview_invite)


def test_preview_invalid_code():
    r = client.get("/api/invites/INVALID_CODE_XYZ")
    assert r.status_code == 404

test("3) Preview invalid code → 404", test_preview_invalid_code)


def test_accept_invite():
    r = client.post(
        f"/api/invites/{invite_code}/accept",
        headers=headers(joiner_token),
    )
    assert r.status_code == 200, f"Expected 200 got {r.status_code}: {r.get_json()}"
    data = r.get_json()
    assert "server" in data
    assert data["server"]["name"] == "InviteTestServer"
    print(f"   Joined: {data['server']['name']}")

test("4) Accept invite — join server", test_accept_invite)


def test_accept_invite_already_member():
    r = client.post(
        f"/api/invites/{invite_code}/accept",
        headers=headers(joiner_token),
    )
    assert r.status_code == 409, f"Expected 409 got {r.status_code}"

test("5) Accept same invite again → 409 already member", test_accept_invite_already_member)


def test_invite_uses_incremented():
    r = client.get(f"/api/invites/{invite_code}")
    assert r.status_code == 200
    assert r.get_json()["invite"]["uses"] == 1
    print(f"   Uses: {r.get_json()['invite']['uses']}")

test("6) Invite uses incremented after accept", test_invite_uses_incremented)


def test_list_invites():
    r = client.get(
        f"/api/servers/{server_id}/invites",
        headers=headers(owner_token),
    )
    assert r.status_code == 200
    invites = r.get_json()["invites"]
    assert len(invites) >= 1
    print(f"   Count: {len(invites)}")

test("7) List server invites", test_list_invites)


def test_list_invites_non_member():
    r = client.get(
        f"/api/servers/{server_id}/invites",
        headers=headers(other_token),
    )
    assert r.status_code == 403

test("8) List invites as non-member → 403", test_list_invites_non_member)


def test_create_invite_non_member():
    r = client.post(
        f"/api/servers/{server_id}/invites",
        headers=headers(other_token),
        json={},
    )
    assert r.status_code == 403, f"Expected 403 got {r.status_code}"

test("9) Create invite as non-member → 403", test_create_invite_non_member)


one_use_code = None


def test_max_uses():
    global one_use_code
    # Create invite with max_uses=1
    r = client.post(
        f"/api/servers/{server_id}/invites",
        headers=headers(owner_token),
        json={"max_uses": 1},
    )
    assert r.status_code == 201
    one_use_code = r.get_json()["invite"]["code"]

    # Accept with other user
    r = client.post(
        f"/api/invites/{one_use_code}/accept",
        headers=headers(other_token),
    )
    assert r.status_code == 200

    # Register a 4th user and try to use the exhausted invite
    r4 = register("inv_fourth", "inv_fourth@test.com", "password123")
    r = client.post(
        f"/api/invites/{one_use_code}/accept",
        headers=headers(r4["access_token"]),
    )
    assert r.status_code == 410, f"Expected 410 got {r.status_code}: {r.get_json()}"

    # Exhausted invite should also fail preview.
    r = client.get(f"/api/invites/{one_use_code}")
    assert r.status_code == 410, f"Expected 410 got {r.status_code}: {r.get_json()}"

    # Cleanup 4th user
    cleanup_user("inv_fourth@test.com")

test("10) Invite with max_uses=1 expires after one use", test_max_uses)


def test_delete_invite_by_owner():
    # Create a new invite
    r = client.post(
        f"/api/servers/{server_id}/invites",
        headers=headers(owner_token),
        json={},
    )
    assert r.status_code == 201
    code = r.get_json()["invite"]["code"]

    # Delete it
    r = client.delete(f"/api/invites/{code}", headers=headers(owner_token))
    assert r.status_code == 200

    # Verify it's gone
    r = client.get(f"/api/invites/{code}")
    assert r.status_code == 404

test("11) Owner can delete an invite", test_delete_invite_by_owner)


def test_delete_invite_unauthorized():
    # Create invite as owner
    r = client.post(
        f"/api/servers/{server_id}/invites",
        headers=headers(owner_token),
        json={},
    )
    code = r.get_json()["invite"]["code"]

    # Try to delete as joiner (not creator, not owner)
    r = client.delete(f"/api/invites/{code}", headers=headers(joiner_token))
    assert r.status_code == 403

    # Cleanup
    client.delete(f"/api/invites/{code}", headers=headers(owner_token))

test("12) Non-creator/non-owner cannot delete invite → 403", test_delete_invite_unauthorized)


def test_create_invite_with_expiry():
    r = client.post(
        f"/api/servers/{server_id}/invites",
        headers=headers(owner_token),
        json={"expires_in_hours": 24},
    )
    assert r.status_code == 201
    inv = r.get_json()["invite"]
    assert inv["expires_at"] is not None
    print(f"   Expires: {inv['expires_at']}")
    # Cleanup
    client.delete(f"/api/invites/{inv['code']}", headers=headers(owner_token))

test("13) Create invite with expiry", test_create_invite_with_expiry)


def test_create_invite_uses_backend_default_ttl_when_null():
    r = client.post(
        f"/api/servers/{server_id}/invites",
        headers=headers(owner_token),
        json={"max_uses": 0, "expires_in_hours": None},
    )
    assert r.status_code == 201, f"Expected 201 got {r.status_code}: {r.get_json()}"
    inv = r.get_json()["invite"]
    configured_default = app.config.get("INVITE_DEFAULT_EXPIRES_HOURS", 24)
    if configured_default > 0:
        assert inv["expires_at"] is not None
    else:
        assert inv["expires_at"] is None
    client.delete(f"/api/invites/{inv['code']}", headers=headers(owner_token))

test("14) Null expires_in_hours uses backend default TTL", test_create_invite_uses_backend_default_ttl_when_null)


def test_expired_invite_preview_and_accept():
    r = client.post(
        f"/api/servers/{server_id}/invites",
        headers=headers(owner_token),
        json={"expires_in_hours": 24},
    )
    assert r.status_code == 201
    code = r.get_json()["invite"]["code"]

    set_invite_expiry(code, datetime.now(timezone.utc) - timedelta(seconds=1))

    r = client.get(f"/api/invites/{code}")
    assert r.status_code == 410, f"Expected 410 got {r.status_code}: {r.get_json()}"

    expired_user = register("inv_expired_user", "inv_expired_user@test.com", "password123")
    r = client.post(
        f"/api/invites/{code}/accept",
        headers=headers(expired_user["access_token"]),
    )
    assert r.status_code == 410, f"Expected 410 got {r.status_code}: {r.get_json()}"

    cleanup_user("inv_expired_user@test.com")
    client.delete(f"/api/invites/{code}", headers=headers(owner_token))

test("15) Expired invite blocks preview and accept (410)", test_expired_invite_preview_and_accept)


def test_invite_expiry_boundary():
    r = client.post(
        f"/api/servers/{server_id}/invites",
        headers=headers(owner_token),
        json={"expires_in_hours": 24},
    )
    assert r.status_code == 201
    code = r.get_json()["invite"]["code"]

    # Slightly future expiry should still be accepted by preview.
    set_invite_expiry(code, datetime.now(timezone.utc) + timedelta(seconds=2))
    r = client.get(f"/api/invites/{code}")
    assert r.status_code == 200, f"Expected 200 got {r.status_code}: {r.get_json()}"

    # Move expiry to the past and ensure it is immediately blocked.
    set_invite_expiry(code, datetime.now(timezone.utc) - timedelta(seconds=1))
    r = client.get(f"/api/invites/{code}")
    assert r.status_code == 410, f"Expected 410 got {r.status_code}: {r.get_json()}"

    client.delete(f"/api/invites/{code}", headers=headers(owner_token))

test("16) Invite expiry boundary around current time", test_invite_expiry_boundary)


def test_single_active_invite_per_creator_per_server():
    r = client.post(
        f"/api/servers/{server_id}/invites",
        headers=headers(owner_token),
        json={},
    )
    assert r.status_code == 201
    first_code = r.get_json()["invite"]["code"]

    r = client.post(
        f"/api/servers/{server_id}/invites",
        headers=headers(owner_token),
        json={},
    )
    assert r.status_code == 201
    second_code = r.get_json()["invite"]["code"]
    assert second_code != first_code

    # Older invite should be expired immediately.
    r = client.get(f"/api/invites/{first_code}")
    assert r.status_code == 410, f"Expected 410 got {r.status_code}: {r.get_json()}"

    # New invite should be active.
    r = client.get(f"/api/invites/{second_code}")
    assert r.status_code == 200, f"Expected 200 got {r.status_code}: {r.get_json()}"

    # List endpoint should only return active invite links.
    r = client.get(f"/api/servers/{server_id}/invites", headers=headers(owner_token))
    assert r.status_code == 200
    codes = [inv["code"] for inv in r.get_json()["invites"]]
    assert second_code in codes
    assert first_code not in codes

    client.delete(f"/api/invites/{first_code}", headers=headers(owner_token))
    client.delete(f"/api/invites/{second_code}", headers=headers(owner_token))

test("17) Creator has only one active invite per server", test_single_active_invite_per_creator_per_server)


def test_list_filters_expired_and_exhausted_invites():
    # Exhausted invite (max_uses=1)
    r = client.post(
        f"/api/servers/{server_id}/invites",
        headers=headers(owner_token),
        json={"max_uses": 1},
    )
    assert r.status_code == 201
    exhausted_code = r.get_json()["invite"]["code"]

    list_consumer = register("inv_list_consumer", "inv_list_consumer@test.com", "password123")
    r = client.post(
        f"/api/invites/{exhausted_code}/accept",
        headers=headers(list_consumer["access_token"]),
    )
    assert r.status_code == 200, f"Expected 200 got {r.status_code}: {r.get_json()}"

    # Expired invite
    r = client.post(
        f"/api/servers/{server_id}/invites",
        headers=headers(owner_token),
        json={"expires_in_hours": 24},
    )
    assert r.status_code == 201
    expired_code = r.get_json()["invite"]["code"]
    set_invite_expiry(expired_code, datetime.now(timezone.utc) - timedelta(seconds=1))

    # Active invite
    r = client.post(
        f"/api/servers/{server_id}/invites",
        headers=headers(owner_token),
        json={},
    )
    assert r.status_code == 201
    active_code = r.get_json()["invite"]["code"]

    r = client.get(f"/api/servers/{server_id}/invites", headers=headers(owner_token))
    assert r.status_code == 200
    codes = [inv["code"] for inv in r.get_json()["invites"]]
    assert active_code in codes
    assert exhausted_code not in codes
    assert expired_code not in codes

    cleanup_user("inv_list_consumer@test.com")
    client.delete(f"/api/invites/{exhausted_code}", headers=headers(owner_token))
    client.delete(f"/api/invites/{expired_code}", headers=headers(owner_token))
    client.delete(f"/api/invites/{active_code}", headers=headers(owner_token))

test("18) List endpoint filters expired and exhausted invites", test_list_filters_expired_and_exhausted_invites)


def test_mongo_uri_uses_tz_aware_datetimes():
    assert "tz_aware=true" in app.config["MONGO_URI"].lower(), app.config["MONGO_URI"]

test("19) Mongo URI enables tz-aware datetime decoding", test_mongo_uri_uses_tz_aware_datetimes)


def test_accept_invite_no_auth():
    r = client.post(f"/api/invites/{invite_code}/accept")
    assert r.status_code == 401

test("20) Accept invite without auth → 401", test_accept_invite_no_auth)


# ═══════════════════════════════════════════════════════════
# Cleanup
# ═══════════════════════════════════════════════════════════
with app.app_context():
    test_users = [u["_id"] for u in mongo.db.users.find({"email": {"$in": INV_TEST_EMAILS}}, {"_id": 1})]
    test_servers = [s["_id"] for s in mongo.db.servers.find({"name": "InviteTestServer"}, {"_id": 1})]
    mongo.db.user_roles.delete_many({"user_id": {"$in": test_users}})
    mongo.db.invites.delete_many({"server_id": {"$in": test_servers}})
    mongo.db.users.delete_many({"email": {"$in": INV_TEST_EMAILS}})
    mongo.db.servers.delete_many({"name": "InviteTestServer"})

print("=" * 60)
print(f"RESULTS: {passed} passed, {failed} failed out of {passed + failed}")
print("=" * 60)

assert failed == 0, f"{failed} test(s) failed!"
