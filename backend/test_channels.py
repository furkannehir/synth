"""Smoke tests for the channels module."""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app import create_app
from app.extensions import mongo
from flask_jwt_extended import create_access_token

app = create_app("development")
client = app.test_client()

# ── Helpers ─────────────────────────────────────────────────

def make_user(username, email, password="password123"):
    """Register a user and return (user_dict, token)."""
    r = client.post("/api/auth/register", json={
        "username": username, "email": email, "password": password,
    })
    data = r.get_json()
    return data["user"], data["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def give_permission(user_id, server_id, *perms):
    """Give a user a temporary role with the given permissions in a server."""
    with app.app_context():
        from app.models import role as role_model
        role_name = f"_test_{'_'.join(perms)}_{user_id[-4:]}"
        # Reuse existing test role if it already exists
        existing = role_model.find_by_name(role_name)
        if existing:
            role_id = str(existing["_id"])
        else:
            role_id = role_model.create(role_name, list(perms))
        role_model.assign_role(user_id, role_id, server_id)
    return role_id


# ── Setup ───────────────────────────────────────────────────

with app.app_context():
    # Clean previous test data
    test_users = [u["_id"] for u in mongo.db.users.find({"email": {"$regex": r"^chan_test"}}, {"_id": 1})]
    test_servers = [s["_id"] for s in mongo.db.servers.find({"name": {"$regex": r"^ChanTest"}}, {"_id": 1})]
    mongo.db.user_roles.delete_many({"user_id": {"$in": test_users}})
    mongo.db.channels.delete_many({"server_id": {"$in": test_servers}})
    mongo.db.users.delete_many({"email": {"$regex": r"^chan_test"}})
    mongo.db.servers.delete_many({"name": {"$regex": r"^ChanTest"}})
    mongo.db.roles.delete_many({"name": {"$regex": r"^_test_"}})

# Create two users
owner, owner_token = make_user("chan_owner", "chan_test_owner@test.com")
member, member_token = make_user("chan_member", "chan_test_member@test.com")

# Create a server
r = client.post("/api/servers", json={"name": "ChanTestServer"}, headers=auth(owner_token))
assert r.status_code == 201, f"Server creation failed: {r.get_json()}"
server = r.get_json()["server"]
server_id = server["id"]

# Member joins the server
r = client.post(f"/api/servers/{server_id}/join", headers=auth(member_token))
assert r.status_code == 200

# Owner already has admin role (auto-assigned on server creation)

BASE = f"/api/servers/{server_id}/channels"

passed = 0
total = 0


def check(label, condition):
    global passed, total
    total += 1
    if condition:
        passed += 1
        print(f"   ✅ {label}")
    else:
        print(f"   ❌ {label}")


# ════════════════════════════════════════════════════════════
print("=" * 60)
print("1) GET channels — empty server → empty list")
print("=" * 60)
r = client.get(BASE, headers=auth(owner_token))
print(f"   Status: {r.status_code}")
channels = r.get_json()["channels"]
check("Status 200", r.status_code == 200)
check("Empty list", len(channels) == 0)

# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("2) POST channel — create 'Lobby' voice channel")
print("=" * 60)
r = client.post(BASE, json={"name": "Lobby"}, headers=auth(owner_token))
print(f"   Status: {r.status_code}")
print(f"   Body:   {r.get_json()}")
check("Status 201", r.status_code == 201)
lobby = r.get_json()["channel"]
lobby_id = lobby["id"]
check("Name is Lobby", lobby["name"] == "Lobby")
check("Type is voice", lobby["type"] == "voice")
check("Server ID matches", lobby["server_id"] == server_id)

# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("3) POST channel — duplicate name → 409")
print("=" * 60)
r = client.post(BASE, json={"name": "Lobby"}, headers=auth(owner_token))
print(f"   Status: {r.status_code}")
check("Status 409", r.status_code == 409)

# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("4) POST channel — member without manage_channels → 403")
print("=" * 60)
r = client.post(BASE, json={"name": "Secret"}, headers=auth(member_token))
print(f"   Status: {r.status_code}")
check("Status 403", r.status_code == 403)

# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("5) POST channel — create 'Gaming' with user_limit=10")
print("=" * 60)
r = client.post(BASE, json={
    "name": "Gaming", "type": "voice", "user_limit": 10,
}, headers=auth(owner_token))
print(f"   Status: {r.status_code}")
gaming = r.get_json()["channel"]
gaming_id = gaming["id"]
check("Status 201", r.status_code == 201)
check("user_limit is 10", gaming["user_limit"] == 10)
check("Position auto-assigned to 1", gaming["position"] == 1)

# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("6) GET channels — list shows 2 channels, sorted by position")
print("=" * 60)
r = client.get(BASE, headers=auth(owner_token))
channels = r.get_json()["channels"]
names = [c["name"] for c in channels]
print(f"   Channels: {names}")
check("2 channels", len(channels) == 2)
check("Lobby first, Gaming second", names == ["Lobby", "Gaming"])

# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("7) GET channel by ID")
print("=" * 60)
r = client.get(f"{BASE}/{lobby_id}", headers=auth(owner_token))
print(f"   Status: {r.status_code}")
check("Status 200", r.status_code == 200)
check("Correct channel returned", r.get_json()["channel"]["id"] == lobby_id)

# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("8) PUT channel — rename Lobby → Main Lobby")
print("=" * 60)
r = client.put(f"{BASE}/{lobby_id}", json={"name": "Main Lobby"}, headers=auth(owner_token))
print(f"   Status: {r.status_code}")
check("Status 200", r.status_code == 200)
check("Name updated", r.get_json()["channel"]["name"] == "Main Lobby")

# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("9) PUT channel — member without permission → 403")
print("=" * 60)
r = client.put(f"{BASE}/{lobby_id}", json={"name": "Hacked"}, headers=auth(member_token))
print(f"   Status: {r.status_code}")
check("Status 403", r.status_code == 403)

# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("10) PUT channel — invalid type → 400")
print("=" * 60)
r = client.put(f"{BASE}/{gaming_id}", json={"type": "video"}, headers=auth(owner_token))
print(f"   Status: {r.status_code}")
check("Status 400", r.status_code == 400)

# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("11) POST channel — short name → 400")
print("=" * 60)
r = client.post(BASE, json={"name": "X"}, headers=auth(owner_token))
print(f"   Status: {r.status_code}")
check("Status 400", r.status_code == 400)

# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("12) DELETE channel — member without permission → 403")
print("=" * 60)
r = client.delete(f"{BASE}/{gaming_id}", headers=auth(member_token))
print(f"   Status: {r.status_code}")
check("Status 403", r.status_code == 403)

# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("13) DELETE channel — owner deletes Gaming")
print("=" * 60)
r = client.delete(f"{BASE}/{gaming_id}", headers=auth(owner_token))
print(f"   Status: {r.status_code}")
check("Status 200", r.status_code == 200)

# Verify only 1 channel remains
r = client.get(BASE, headers=auth(owner_token))
channels = r.get_json()["channels"]
check("1 channel remaining", len(channels) == 1)
check("Main Lobby is the one left", channels[0]["name"] == "Main Lobby")

# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("14) Default channel protection — seed & try to delete")
print("=" * 60)
with app.app_context():
    from app.models.channel import seed_default_for_server, find_by_server
    seed_default_for_server(server_id)
    defaults = [c for c in find_by_server(server_id) if c.get("is_default")]
    default_id = str(defaults[0]["_id"]) if defaults else None

if default_id:
    r = client.delete(f"{BASE}/{default_id}", headers=auth(owner_token))
    print(f"   Status: {r.status_code}")
    check("Cannot delete default channel (403)", r.status_code == 403)
else:
    print("   ⚠️  No default channel found, skipping")
    check("Default channel seeded", False)

# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("15) GET channel — non-existent → 404")
print("=" * 60)
r = client.get(f"{BASE}/000000000000000000000000", headers=auth(owner_token))
print(f"   Status: {r.status_code}")
check("Status 404", r.status_code == 404)

# ════════════════════════════════════════════════════════════
# SECURITY TESTS
# ════════════════════════════════════════════════════════════

# Create a third user who is NOT a member of ChanTestServer
outsider, outsider_token = make_user("chan_outsider", "chan_test_outsider@test.com")

print("\n" + "=" * 60)
print("16) SECURITY — non-member cannot list channels")
print("=" * 60)
r = client.get(BASE, headers=auth(outsider_token))
print(f"   Status: {r.status_code}")
check("Status 403", r.status_code == 403)

print("\n" + "=" * 60)
print("17) SECURITY — non-member cannot view a channel")
print("=" * 60)
# Main Lobby still exists from earlier tests
r2 = client.get(BASE, headers=auth(owner_token))
some_channel_id = r2.get_json()["channels"][0]["id"]
r = client.get(f"{BASE}/{some_channel_id}", headers=auth(outsider_token))
print(f"   Status: {r.status_code}")
check("Status 403", r.status_code == 403)

# Create a second server + channel to test cross-server access
r = client.post("/api/servers", json={"name": "ChanTestServer2"}, headers=auth(owner_token))
server2 = r.get_json()["server"]
server2_id = server2["id"]
# Owner auto-gets admin role for server2 on creation
r = client.post(f"/api/servers/{server2_id}/channels", json={"name": "Secret Room"}, headers=auth(owner_token))
assert r.status_code == 201, f"Channel creation in server2 failed: {r.get_json()}"
other_channel_id = r.get_json()["channel"]["id"]

print("\n" + "=" * 60)
print("18) SECURITY — channel from server2 via server1 URL → 404")
print("=" * 60)
# Try to access a channel that belongs to server2 using server1's URL
r = client.get(f"{BASE}/{other_channel_id}", headers=auth(owner_token))
print(f"   Status: {r.status_code}")
check("Cross-server GET returns 404", r.status_code == 404)

print("\n" + "=" * 60)
print("19) SECURITY — update channel from server2 via server1 URL → 404")
print("=" * 60)
r = client.put(f"{BASE}/{other_channel_id}", json={"name": "Hacked"}, headers=auth(owner_token))
print(f"   Status: {r.status_code}")
check("Cross-server PUT returns 404", r.status_code == 404)

print("\n" + "=" * 60)
print("20) SECURITY — delete channel from server2 via server1 URL → 404")
print("=" * 60)
r = client.delete(f"{BASE}/{other_channel_id}", headers=auth(owner_token))
print(f"   Status: {r.status_code}")
check("Cross-server DELETE returns 404", r.status_code == 404)

# Verify the channel in server2 is still untouched
r = client.get(f"/api/servers/{server2_id}/channels/{other_channel_id}", headers=auth(owner_token))
check("Channel in server2 still exists", r.status_code == 200)
check("Name unchanged", r.get_json()["channel"]["name"] == "Secret Room")

# ── Cleanup ─────────────────────────────────────────────────
with app.app_context():
    test_users = [u["_id"] for u in mongo.db.users.find({"email": {"$regex": r"^chan_test"}}, {"_id": 1})]
    test_servers = [s["_id"] for s in mongo.db.servers.find({"name": {"$regex": r"^ChanTest"}}, {"_id": 1})]
    mongo.db.user_roles.delete_many({"user_id": {"$in": test_users}})
    mongo.db.channels.delete_many({"server_id": {"$in": test_servers}})
    mongo.db.users.delete_many({"email": {"$regex": r"^chan_test"}})
    mongo.db.servers.delete_many({"name": {"$regex": r"^ChanTest"}})
    mongo.db.roles.delete_many({"name": {"$regex": r"^_test_"}})

print("\n🧹 Test data cleaned up")
print(f"\n🎉 {passed}/{total} TESTS PASSED!" if passed == total
      else f"\n⚠️  {passed}/{total} tests passed — some failed")
