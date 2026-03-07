"""Smoke tests for the presence module."""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(__file__))

from app import create_app
from app.extensions import mongo

app = create_app("development")
client = app.test_client()

# ── Helpers ─────────────────────────────────────────────────

def make_user(username, email, password="password123"):
    r = client.post("/api/auth/register", json={
        "username": username, "email": email, "password": password,
    })
    data = r.get_json()
    return data["user"], data["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ── Setup ───────────────────────────────────────────────────

with app.app_context():
    mongo.db.users.delete_many({"email": {"$regex": r"^pres_test"}})

user, token = make_user("pres_user", "pres_test@test.com")
user_id = user["id"]

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
print("1) After login, user is marked online")
print("=" * 60)
r = client.post("/api/auth/login", json={
    "email": "pres_test@test.com", "password": "password123",
})
login_user = r.get_json()["user"]
print(f"   is_online: {login_user['is_online']}")
# Note: login calls set_online(True) but to_dict is called before the update
# So check via /me
r = client.get("/api/auth/me", headers=auth(token))
me = r.get_json()["user"]
check("is_online = True after login", me["is_online"] == True)

# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("2) POST /api/presence/heartbeat — updates last_seen")
print("=" * 60)
old_last_seen = me["last_seen"]
time.sleep(1)  # ensure timestamp changes
r = client.post("/api/presence/heartbeat", headers=auth(token))
print(f"   Status: {r.status_code}")
hb_user = r.get_json()["user"]
check("Status 200", r.status_code == 200)
check("is_online = True", hb_user["is_online"] == True)
check("last_seen updated", hb_user["last_seen"] > old_last_seen)

# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("3) POST /api/presence/heartbeat — no token → 401")
print("=" * 60)
r = client.post("/api/presence/heartbeat")
print(f"   Status: {r.status_code}")
check("Status 401", r.status_code == 401)

# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("4) POST /api/presence/offline — mark self offline")
print("=" * 60)
r = client.post("/api/presence/offline", headers=auth(token))
print(f"   Status: {r.status_code}")
check("Status 200", r.status_code == 200)

r = client.get("/api/auth/me", headers=auth(token))
me = r.get_json()["user"]
check("is_online = False after offline", me["is_online"] == False)

# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("5) Heartbeat brings user back online")
print("=" * 60)
r = client.post("/api/presence/heartbeat", headers=auth(token))
hb_user = r.get_json()["user"]
check("is_online = True after heartbeat", hb_user["is_online"] == True)

# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("6) Sweep — stale users get marked offline")
print("=" * 60)
# Manually set last_seen to 2 minutes ago to simulate a stale user
from datetime import datetime, timezone, timedelta
with app.app_context():
    from bson import ObjectId
    mongo.db.users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"last_seen": datetime.now(timezone.utc) - timedelta(minutes=2)}},
    )
    from app.services.presence_service import sweep_stale_users
    swept = sweep_stale_users()
    print(f"   Swept: {swept}")
    check("At least 1 user swept", swept >= 1)

r = client.get("/api/auth/me", headers=auth(token))
me = r.get_json()["user"]
check("User is offline after sweep", me["is_online"] == False)

# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("7) Sweep — fresh user is NOT swept")
print("=" * 60)
r = client.post("/api/presence/heartbeat", headers=auth(token))
with app.app_context():
    swept = sweep_stale_users()
    print(f"   Swept: {swept}")
    check("0 users swept (user is fresh)", swept == 0)

r = client.get("/api/auth/me", headers=auth(token))
me = r.get_json()["user"]
check("User still online", me["is_online"] == True)

# ── Cleanup ─────────────────────────────────────────────────
with app.app_context():
    mongo.db.users.delete_many({"email": {"$regex": r"^pres_test"}})
    mongo.db.user_roles.delete_many({"user_id": {"$exists": True}})

print("\n🧹 Test data cleaned up")
print(f"\n🎉 {passed}/{total} TESTS PASSED!" if passed == total
      else f"\n⚠️  {passed}/{total} tests passed — some failed")
