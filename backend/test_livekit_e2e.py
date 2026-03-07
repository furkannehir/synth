"""
End-to-end test: Flask backend + real LiveKit server (no frontend).

Prerequisites
─────────────
1. LiveKit running locally via Docker:
     docker run -d --name synth-livekit ^
       -p 7880:7880 -p 7881:7881 -p 7882:7882/udp ^
       -e LIVEKIT_KEYS="devkey: devsecret" ^
       livekit/livekit-server

2. Flask running:
     cd backend && python run.py

Usage
─────
     cd backend && python test_livekit_e2e.py
"""

import sys
import json
import time

try:
    import requests
except ImportError:
    print("Install 'requests' first:  pip install requests")
    sys.exit(1)

FLASK_URL = "http://localhost:5000"
LIVEKIT_HTTP = "http://localhost:7880"


# ── Helpers ─────────────────────────────────────────────────

def header(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def step(n, desc):
    print(f"\n{'='*60}")
    print(f"  Step {n}: {desc}")
    print(f"{'='*60}")


passed = 0
total = 0


def check(label, ok, detail=""):
    global passed, total
    total += 1
    if ok:
        passed += 1
        print(f"  ✅ {label}")
    else:
        print(f"  ❌ {label}  {detail}")


# ── Pre-flight checks ──────────────────────────────────────

def preflight():
    """Make sure Flask and LiveKit are reachable before running tests."""
    print("Pre-flight checks …")

    try:
        r = requests.get(f"{FLASK_URL}/health", timeout=3)
        assert r.status_code == 200
        print(f"  ✅ Flask is running at {FLASK_URL}")
    except Exception:
        print(f"  ❌ Flask is NOT reachable at {FLASK_URL}")
        print("     Start it with:  python run.py")
        sys.exit(1)

    try:
        requests.get(LIVEKIT_HTTP, timeout=3)
        print(f"  ✅ LiveKit is running at {LIVEKIT_HTTP}")
    except Exception:
        print(f"  ❌ LiveKit is NOT reachable at {LIVEKIT_HTTP}")
        print('     Start it with:  docker run -d --name synth-livekit '
              '-p 7880:7880 -p 7881:7881 -p 7882:7882/udp '
              '-e LIVEKIT_KEYS="devkey: devsecret" livekit/livekit-server')
        sys.exit(1)


# ── Tests ───────────────────────────────────────────────────

def main():
    preflight()

    ts = int(time.time())

    # ── 1. Register two users ───────────────────────────────
    step(1, "Register two users")

    r = requests.post(f"{FLASK_URL}/api/auth/register", json={
        "username": f"alice_{ts}", "email": f"alice_{ts}@e2e.test",
        "password": "password123",
    })
    check("Alice registered", r.status_code == 201, r.text)
    alice = r.json()
    alice_token = alice["access_token"]
    alice_id = alice["user"]["id"]
    print(f"     Alice id: {alice_id}")

    r = requests.post(f"{FLASK_URL}/api/auth/register", json={
        "username": f"bob_{ts}", "email": f"bob_{ts}@e2e.test",
        "password": "password123",
    })
    check("Bob registered", r.status_code == 201, r.text)
    bob = r.json()
    bob_token = bob["access_token"]
    bob_id = bob["user"]["id"]
    print(f"     Bob   id: {bob_id}")

    # ── 2. Create a server ──────────────────────────────────
    step(2, "Create a server and have Bob join")

    # First, give Alice the admin role so she can manage roles & channels.
    # The "admin" role is seeded on first boot with all permissions.
    r = requests.get(f"{FLASK_URL}/api/roles", headers=header(alice_token))
    roles = r.json()["roles"]
    admin_role = next(ro for ro in roles if ro["name"] == "admin")
    admin_role_id = admin_role["id"]

    # assign_roles requires the assign_roles permission, but we can't
    # get that via the API alone.  Use the default-server owner shortcut:
    # directly hit the DB to bootstrap Alice as admin (same as test helpers).
    # Instead, we rely on the fact that the "member" default role has
    # join_channel + speak already — so we only need to create a server
    # (no permission required) and assign admin via a lightweight helper.
    from pymongo import MongoClient
    from bson import ObjectId
    import os
    mongo_uri = os.getenv("MONGO_URI",
                          "mongodb+srv://synth:rkPVSgyT8rhsCJyp@cluster0.ivy3rlu.mongodb.net/synth?appName=Cluster0")
    _mc = MongoClient(mongo_uri)
    _db = _mc.get_default_database()
    # Give Alice the admin role directly in the DB (bootstrap)
    _db.user_roles.update_one(
        {"user_id": ObjectId(alice_id), "role_id": ObjectId(admin_role_id)},
        {"$set": {"user_id": ObjectId(alice_id), "role_id": ObjectId(admin_role_id)}},
        upsert=True,
    )
    _mc.close()
    print(f"     Bootstrapped Alice with admin role ({admin_role_id})")

    r = requests.post(f"{FLASK_URL}/api/servers",
                       json={"name": f"E2EServer_{ts}"},
                       headers=header(alice_token))
    check("Server created", r.status_code == 201, r.text)
    server_id = r.json()["server"]["id"]
    print(f"     Server id: {server_id}")

    r = requests.post(f"{FLASK_URL}/api/servers/{server_id}/join",
                       headers=header(bob_token))
    check("Bob joined server", r.status_code == 200, r.text)

    # ── 3. Give permissions ─────────────────────────────────
    step(3, "Give both users join_channel permission")

    # Create a role with join_channel
    r = requests.post(f"{FLASK_URL}/api/roles",
                       json={"name": f"e2e_voice_{ts}",
                             "permissions": ["join_channel", "kick_user", "mute_user"]},
                       headers=header(alice_token))
    check("Voice role created", r.status_code == 201, r.text)
    role_id = r.json()["role"]["id"]

    for uid, name in [(alice_id, "Alice"), (bob_id, "Bob")]:
        r = requests.post(f"{FLASK_URL}/api/roles/assign",
                           json={"user_id": uid, "role_id": role_id},
                           headers=header(alice_token))
        check(f"Role assigned to {name}", r.status_code == 200, r.text)

    # ── 4. Create a voice channel ───────────────────────────
    step(4, "Create a voice channel")

    # Need manage_channels permission
    r = requests.post(f"{FLASK_URL}/api/roles",
                       json={"name": f"e2e_manage_{ts}",
                             "permissions": ["manage_channels"]},
                       headers=header(alice_token))
    manage_role_id = r.json()["role"]["id"]
    requests.post(f"{FLASK_URL}/api/roles/assign",
                  json={"user_id": alice_id, "role_id": manage_role_id},
                  headers=header(alice_token))

    r = requests.post(f"{FLASK_URL}/api/servers/{server_id}/channels",
                       json={"name": "voice-lounge", "type": "voice", "user_limit": 10},
                       headers=header(alice_token))
    check("Voice channel created", r.status_code == 201, r.text)
    channel_id = r.json()["channel"]["id"]
    print(f"     Channel id: {channel_id}")

    voice_base = f"{FLASK_URL}/api/servers/{server_id}/channels/{channel_id}/voice"

    # ── 5. Alice joins the voice channel ────────────────────
    step(5, "Alice joins the voice channel")

    r = requests.post(f"{voice_base}/join", headers=header(alice_token))
    check("Alice got 200", r.status_code == 200, r.text)
    alice_join = r.json()
    check("Response has 'token'", "token" in alice_join)
    check("Response has 'url'",   "url" in alice_join)
    check("Response has 'room'",  "room" in alice_join)
    alice_lk_token = alice_join.get("token", "")
    room_name = alice_join.get("room", "")
    print(f"     Room:  {room_name}")
    print(f"     Token: {alice_lk_token[:60]}…")

    # ── 6. Bob joins the same channel ───────────────────────
    step(6, "Bob joins the same voice channel")

    r = requests.post(f"{voice_base}/join", headers=header(bob_token))
    check("Bob got 200", r.status_code == 200, r.text)
    bob_lk_token = r.json().get("token", "")
    check("Bob got a different token", bob_lk_token != alice_lk_token)

    # ── 7. List participants via Flask ──────────────────────
    step(7, "List participants via API")

    # Give LiveKit a moment to register the room
    time.sleep(1)

    r = requests.get(f"{voice_base}/participants", headers=header(alice_token))
    check("Participants endpoint 200", r.status_code == 200, r.text)
    participants = r.json().get("participants", [])
    print(f"     Participants: {json.dumps(participants, indent=2)}")

    # ── 8. Alice leaves ─────────────────────────────────────
    step(8, "Alice leaves the voice channel")

    r = requests.post(f"{voice_base}/leave", headers=header(alice_token))
    check("Leave returned 200", r.status_code == 200, r.text)
    check("Message says 'Left'", "Left" in r.json().get("message", ""))

    # ── 9. Leave is idempotent ──────────────────────────────
    step(9, "Leaving again is idempotent")

    r = requests.post(f"{voice_base}/leave", headers=header(alice_token))
    check("Second leave also 200", r.status_code == 200, r.text)

    # ── 10. Unauthenticated is rejected ─────────────────────
    step(10, "Unauthenticated request → 401")

    r = requests.post(f"{voice_base}/join")
    check("No token → 401", r.status_code == 401)

    # ── Summary ─────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  Results: {passed}/{total} checks passed")
    print(f"{'='*60}")

    if passed == total:
        print(f"""
  🎉 All checks passed!

  ── Try real audio ──────────────────────────────────────

  Install the LiveKit CLI:
    pip install livekit-cli
      — or —
    https://github.com/livekit/livekit-cli/releases

  Then open two terminals:

  Terminal 1 (Alice):
    lk room join --url ws://localhost:7880 --token {alice_lk_token}

  Terminal 2 (Bob):
    lk room join --url ws://localhost:7880 --token {bob_lk_token}

  Speak into your mic in one terminal — the other will play it.
""")
    else:
        print(f"\n  ⚠️  {total - passed} check(s) failed — see output above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
