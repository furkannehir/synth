"""Quick smoke test for auth endpoints using Flask test client."""
import sys
import os

# Ensure we can import the app
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app
from app.extensions import mongo

app = create_app("development")
client = app.test_client()

# Clean up any previous test data
with app.app_context():
    mongo.db.users.delete_many({"email": {"$in": ["test@example.com", "x@y.com"]}})

# ═══════════════════════════════════════════════════════════
print("=" * 60)
print("1) REGISTER  —  POST /api/auth/register")
print("=" * 60)
r = client.post("/api/auth/register", json={
    "username": "testuser",
    "email": "test@example.com",
    "password": "password123",
})
print(f"   Status: {r.status_code}")
print(f"   Body:   {r.get_json()}")
assert r.status_code == 201, f"Expected 201, got {r.status_code}"
token = r.get_json()["access_token"]
user_id = r.get_json()["user"]["id"]
# Roles are now assigned per-server, not on register
user_roles = r.get_json()["user"].get("roles", [])
assert len(user_roles) == 0, f"Expected 0 roles on register, got {len(user_roles)}"
print(f"   ✅ User created: {user_id} (no global roles)")
print()

print("=" * 60)
print("2) REGISTER DUPLICATE  —  should fail 409")
print("=" * 60)
r = client.post("/api/auth/register", json={
    "username": "testuser",
    "email": "test@example.com",
    "password": "password123",
})
print(f"   Status: {r.status_code}")
print(f"   Body:   {r.get_json()}")
assert r.status_code == 409, f"Expected 409, got {r.status_code}"
print(f"   ✅ Duplicate correctly rejected")
print()

print("=" * 60)
print("3) LOGIN  —  POST /api/auth/login")
print("=" * 60)
r = client.post("/api/auth/login", json={
    "email": "test@example.com",
    "password": "password123",
})
print(f"   Status: {r.status_code}")
print(f"   Body:   {r.get_json()}")
assert r.status_code == 200, f"Expected 200, got {r.status_code}"
login_token = r.get_json()["access_token"]
print(f"   ✅ Login successful")
print()

print("=" * 60)
print("4) LOGIN BAD PASSWORD  —  should fail 401")
print("=" * 60)
r = client.post("/api/auth/login", json={
    "email": "test@example.com",
    "password": "wrongpassword",
})
print(f"   Status: {r.status_code}")
print(f"   Body:   {r.get_json()}")
assert r.status_code == 401, f"Expected 401, got {r.status_code}"
print(f"   ✅ Bad password correctly rejected")
print()

print("=" * 60)
print("5) GET /api/auth/me  —  with valid token")
print("=" * 60)
r = client.get("/api/auth/me", headers={
    "Authorization": f"Bearer {login_token}",
})
print(f"   Status: {r.status_code}")
print(f"   Body:   {r.get_json()}")
assert r.status_code == 200, f"Expected 200, got {r.status_code}"
assert r.get_json()["user"]["username"] == "testuser"
print(f"   ✅ /me returned correct user")
print()

print("=" * 60)
print("6) GET /api/auth/me  —  without token (should fail 401)")
print("=" * 60)
r = client.get("/api/auth/me")
print(f"   Status: {r.status_code}")
print(f"   Body:   {r.get_json()}")
assert r.status_code == 401, f"Expected 401, got {r.status_code}"
print(f"   ✅ No-token correctly rejected")
print()

print("=" * 60)
print("7) VALIDATION  —  short username")
print("=" * 60)
r = client.post("/api/auth/register", json={
    "username": "ab",
    "email": "x@y.com",
    "password": "password123",
})
print(f"   Status: {r.status_code}")
print(f"   Body:   {r.get_json()}")
assert r.status_code == 400, f"Expected 400, got {r.status_code}"
print(f"   ✅ Short username rejected")
print()

print("=" * 60)
print("8) VALIDATION  —  short password")
print("=" * 60)
r = client.post("/api/auth/register", json={
    "username": "validuser",
    "email": "x@y.com",
    "password": "12345",
})
print(f"   Status: {r.status_code}")
print(f"   Body:   {r.get_json()}")
assert r.status_code == 400, f"Expected 400, got {r.status_code}"
print(f"   ✅ Short password rejected")
print()

# Cleanup test data
with app.app_context():
    mongo.db.users.delete_many({"email": {"$in": ["test@example.com", "x@y.com"]}})
    print("🧹 Test data cleaned up")

print()
print("🎉 ALL 8 TESTS PASSED!")
