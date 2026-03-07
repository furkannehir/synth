"""Smoke test for server endpoints."""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app import create_app
from app.extensions import mongo

app = create_app("development")
client = app.test_client()

# ── Cleanup ─────────────────────────────────────────────────
with app.app_context():
    mongo.db.users.delete_many({"email": {"$in": [
        "owner@test.com", "joiner@test.com",
    ]}})
    mongo.db.servers.delete_many({"name": {"$in": ["Test Gaming", "Renamed Gaming"]}})
    mongo.db.user_roles.delete_many({})

# ── Helpers ─────────────────────────────────────────────────
def register(username, email, password):
    r = client.post("/api/auth/register", json={
        "username": username, "email": email, "password": password,
    })
    assert r.status_code == 201, f"Register failed: {r.get_json()}"
    return r.get_json()

def headers(token):
    return {"Authorization": f"Bearer {token}"}


# ── Setup users ─────────────────────────────────────────────
owner = register("serverowner", "owner@test.com", "password123")
owner_token = owner["access_token"]
owner_id = owner["user"]["id"]

joiner = register("serverjoiner", "joiner@test.com", "password123")
joiner_token = joiner["access_token"]
joiner_id = joiner["user"]["id"]


# ═══════════════════════════════════════════════════════════
print("=" * 60)
print("1) Default 'Synth' server exists after startup")
print("=" * 60)
r = client.get("/api/servers?all=true", headers=headers(owner_token))
all_servers = r.get_json()["servers"]
default = [s for s in all_servers if s["is_default"]]
print(f"   Default servers: {[s['name'] for s in default]}")
assert len(default) == 1
assert default[0]["name"] == "Synth"
default_id = default[0]["id"]
print("   ✅ Default 'Synth' server seeded")
print()

# ═══════════════════════════════════════════════════════════
print("=" * 60)
print("2) POST /api/servers → create a new server")
print("=" * 60)
r = client.post("/api/servers", headers=headers(owner_token), json={
    "name": "Test Gaming",
})
print(f"   Status: {r.status_code}")
print(f"   Body:   {r.get_json()}")
assert r.status_code == 201
server = r.get_json()["server"]
server_id = server["id"]
assert server["name"] == "Test Gaming"
assert server["owner_id"] == owner_id
assert server["member_count"] == 1  # owner auto-joins
print("   ✅ Server created, owner auto-joined")
print()

# ═══════════════════════════════════════════════════════════
print("=" * 60)
print("3) POST /api/servers → duplicate name fails 409")
print("=" * 60)
r = client.post("/api/servers", headers=headers(owner_token), json={
    "name": "Test Gaming",
})
print(f"   Status: {r.status_code}")
assert r.status_code == 409
print("   ✅ Duplicate name rejected")
print()

# ═══════════════════════════════════════════════════════════
print("=" * 60)
print("4) GET /api/servers/<id> → get server details")
print("=" * 60)
r = client.get(f"/api/servers/{server_id}", headers=headers(owner_token))
print(f"   Status: {r.status_code}")
assert r.status_code == 200
assert r.get_json()["server"]["name"] == "Test Gaming"
print("   ✅ Server details returned")
print()

# ═══════════════════════════════════════════════════════════
print("=" * 60)
print("5) POST /api/servers/<id>/join → another user joins")
print("=" * 60)
r = client.post(f"/api/servers/{server_id}/join", headers=headers(joiner_token))
print(f"   Status: {r.status_code}")
assert r.status_code == 200
print("   ✅ Joiner joined the server")
print()

# ═══════════════════════════════════════════════════════════
print("=" * 60)
print("6) POST /api/servers/<id>/join → already a member → 409")
print("=" * 60)
r = client.post(f"/api/servers/{server_id}/join", headers=headers(joiner_token))
print(f"   Status: {r.status_code}")
assert r.status_code == 409
print("   ✅ Double-join rejected")
print()

# ═══════════════════════════════════════════════════════════
print("=" * 60)
print("7) GET /api/servers/<id>/members → list members")
print("=" * 60)
r = client.get(f"/api/servers/{server_id}/members", headers=headers(owner_token))
print(f"   Status: {r.status_code}")
members = r.get_json()["members"]
member_names = [m["username"] for m in members]
print(f"   Members: {member_names}")
assert len(members) == 2
assert "serverowner" in member_names
assert "serverjoiner" in member_names
print("   ✅ Both members listed")
print()

# ═══════════════════════════════════════════════════════════
print("=" * 60)
print("8) GET /api/servers → user's joined servers")
print("=" * 60)
r = client.get("/api/servers", headers=headers(joiner_token))
joined = r.get_json()["servers"]
joined_names = [s["name"] for s in joined]
print(f"   Joined: {joined_names}")
assert "Test Gaming" in joined_names
print("   ✅ Joiner sees their servers")
print()

# ═══════════════════════════════════════════════════════════
print("=" * 60)
print("9) PUT /api/servers/<id> → rename server (owner)")
print("=" * 60)
r = client.put(f"/api/servers/{server_id}", headers=headers(owner_token), json={
    "name": "Renamed Gaming",
})
print(f"   Status: {r.status_code}")
assert r.status_code == 200
assert r.get_json()["server"]["name"] == "Renamed Gaming"
print("   ✅ Server renamed")
print()

# ═══════════════════════════════════════════════════════════
print("=" * 60)
print("10) PUT /api/servers/<id> → non-owner → 403")
print("=" * 60)
r = client.put(f"/api/servers/{server_id}", headers=headers(joiner_token), json={
    "name": "Hacked Name",
})
print(f"   Status: {r.status_code}")
assert r.status_code == 403
print("   ✅ Non-owner cannot rename")
print()

# ═══════════════════════════════════════════════════════════
print("=" * 60)
print("11) POST /api/servers/<id>/leave → joiner leaves")
print("=" * 60)
r = client.post(f"/api/servers/{server_id}/leave", headers=headers(joiner_token))
print(f"   Status: {r.status_code}")
assert r.status_code == 200
r2 = client.get(f"/api/servers/{server_id}/members", headers=headers(owner_token))
assert len(r2.get_json()["members"]) == 1
print("   ✅ Joiner left, 1 member remaining")
print()

# ═══════════════════════════════════════════════════════════
print("=" * 60)
print("12) POST /api/servers/<id>/leave → owner can't leave")
print("=" * 60)
r = client.post(f"/api/servers/{server_id}/leave", headers=headers(owner_token))
print(f"   Status: {r.status_code}")
assert r.status_code == 403
print("   ✅ Owner correctly blocked from leaving")
print()

# ═══════════════════════════════════════════════════════════
print("=" * 60)
print("13) DELETE default server → 403")
print("=" * 60)
r = client.delete(f"/api/servers/{default_id}", headers=headers(owner_token))
print(f"   Status: {r.status_code}")
assert r.status_code == 403
print("   ✅ Cannot delete default server")
print()

# ═══════════════════════════════════════════════════════════
print("=" * 60)
print("14) DELETE /api/servers/<id> → owner deletes")
print("=" * 60)
r = client.delete(f"/api/servers/{server_id}", headers=headers(owner_token))
print(f"   Status: {r.status_code}")
assert r.status_code == 200
r2 = client.get(f"/api/servers/{server_id}", headers=headers(owner_token))
assert r2.status_code == 404
print("   ✅ Server deleted successfully")
print()

# ── Cleanup ─────────────────────────────────────────────────
with app.app_context():
    mongo.db.users.delete_many({"email": {"$in": [
        "owner@test.com", "joiner@test.com",
    ]}})
    mongo.db.servers.delete_many({"name": {"$in": ["Test Gaming", "Renamed Gaming"]}})
    mongo.db.user_roles.delete_many({})
    print("🧹 Test data cleaned up")

print()
print("🎉 ALL 14 TESTS PASSED!")
