"""Smoke tests for the voice module.

Uses a lightweight **MockMediaServer** that satisfies the
MediaServerPort ABC so tests run without a real LiveKit instance.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app.ports.media_server import (
    MediaServerPort,
    ParticipantInfo,
    RoomInfo,
    TrackInfo,
)

# ── Mock adapter ────────────────────────────────────────────


class MockMediaServer(MediaServerPort):
    """In-memory media-server implementation for tests."""

    def __init__(self):
        self.rooms: dict[str, RoomInfo] = {}
        self.participants: dict[str, list[ParticipantInfo]] = {}

    def generate_token(self, room_name, identity, name="", *, can_publish=True, can_subscribe=True):
        return f"mock-jwt-{room_name}-{identity}"

    def create_room(self, name, *, empty_timeout=300, max_participants=0):
        if name not in self.rooms:
            self.rooms[name] = RoomInfo(
                name=name, sid=f"sid-{name}", max_participants=max_participants
            )
        return self.rooms[name]

    def delete_room(self, name):
        self.rooms.pop(name, None)
        self.participants.pop(name, None)

    def list_rooms(self):
        return list(self.rooms.values())

    def list_participants(self, room_name):
        return self.participants.get(room_name, [])

    def remove_participant(self, room_name, identity):
        if room_name in self.participants:
            self.participants[room_name] = [
                p for p in self.participants[room_name] if p.identity != identity
            ]

    def mute_participant(self, room_name, identity, track_sid, *, muted=True):
        for p in self.participants.get(room_name, []):
            if p.identity == identity:
                for t in p.tracks:
                    if t.sid == track_sid:
                        t.muted = muted

    # ── test helpers ───────────────────────────────────────

    def add_fake_participant(self, room_name, identity, name="", tracks=None):
        """Simulate a user already being in a room."""
        if room_name not in self.rooms:
            self.create_room(room_name)
        if room_name not in self.participants:
            self.participants[room_name] = []
        self.participants[room_name].append(
            ParticipantInfo(
                identity=identity,
                name=name or identity,
                sid=f"sid-{identity}",
                state="ACTIVE",
                tracks=tracks or [],
            )
        )


# ── Bootstrap ──────────────────────────────────────────────

mock_media = MockMediaServer()

# Patch the adapter BEFORE importing the app so the factory doesn't
# try to create a real LiveKit adapter.
os.environ["LIVEKIT_API_KEY"] = "testkey"
os.environ["LIVEKIT_API_SECRET"] = "testsecret"

from app import create_app
from app.extensions import mongo
import app.extensions as ext

app = create_app("development")
ext.media_server = mock_media  # override with the mock

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


def give_permission(user_id, server_id, *perms):
    """Give a user a temporary role with the given permissions in a server."""
    with app.app_context():
        from app.models import role as role_model
        role_name = f"_test_{'_'.join(perms)}_{user_id[-4:]}"
        existing = role_model.find_by_name(role_name)
        if existing:
            role_id = str(existing["_id"])
        else:
            role_id = role_model.create(role_name, list(perms))
        role_model.assign_role(user_id, role_id, server_id)
    return role_id


# ── Setup ───────────────────────────────────────────────────

with app.app_context():
    mongo.db.users.delete_many({"email": {"$regex": r"^voice_test"}})
    mongo.db.servers.delete_many({"name": {"$regex": r"^VoiceTest"}})
    mongo.db.channels.delete_many({})
    mongo.db.roles.delete_many({"name": {"$regex": r"^_test_"}})
    mongo.db.user_roles.delete_many({})

owner, owner_token = make_user("voice_owner", "voice_test_owner@test.com")
member, member_token = make_user("voice_member", "voice_test_member@test.com")
outsider, outsider_token = make_user("voice_outsider", "voice_test_outsider@test.com")

# Create server
r = client.post("/api/servers", json={"name": "VoiceTestServer"}, headers=auth(owner_token))
assert r.status_code == 201, f"Server creation failed: {r.get_json()}"
server = r.get_json()["server"]
server_id = server["id"]

# Member joins
r = client.post(f"/api/servers/{server_id}/join", headers=auth(member_token))
assert r.status_code == 200

# Owner already has admin role (auto-assigned on server creation)
# Member already has 'member' role with join_channel + speak (auto-assigned on join)

# Create a voice channel
r = client.post(
    f"/api/servers/{server_id}/channels",
    json={"name": "VoiceRoom", "type": "voice", "user_limit": 3},
    headers=auth(owner_token),
)
assert r.status_code == 201, f"Channel creation failed: {r.get_json()}"
voice_channel = r.get_json()["channel"]
channel_id = voice_channel["id"]

# Create a text channel (to test rejection)
r = client.post(
    f"/api/servers/{server_id}/channels",
    json={"name": "TextRoom", "type": "text"},
    headers=auth(owner_token),
)
assert r.status_code == 201
text_channel = r.get_json()["channel"]
text_channel_id = text_channel["id"]

VOICE_BASE = f"/api/servers/{server_id}/channels/{channel_id}/voice"
TEXT_VOICE = f"/api/servers/{server_id}/channels/{text_channel_id}/voice"

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
print("1) POST /join — owner joins voice channel")
print("=" * 60)
mock_media.rooms.clear()
mock_media.participants.clear()
r = client.post(f"{VOICE_BASE}/join", headers=auth(owner_token))
data = r.get_json()
print(f"   Status: {r.status_code}")
check("Status 200", r.status_code == 200)
check("Has token", "token" in data)
check("Has url", "url" in data)
check("Has room", "room" in data)
check("Token contains room+identity", owner["id"] in data.get("token", ""))

# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("2) POST /join — member joins voice channel")
print("=" * 60)
r = client.post(f"{VOICE_BASE}/join", headers=auth(member_token))
data = r.get_json()
print(f"   Status: {r.status_code}")
check("Status 200", r.status_code == 200)
check("Has token", "token" in data)

# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("3) POST /join — outsider rejected (not server member)")
print("=" * 60)
# Outsider has no server-scoped permissions — not a member of this server
r = client.post(f"{VOICE_BASE}/join", headers=auth(outsider_token))
print(f"   Status: {r.status_code}")
check("Status 403", r.status_code == 403)

# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("4) POST /join — text channel rejected")
print("=" * 60)
r = client.post(f"{TEXT_VOICE}/join", headers=auth(owner_token))
print(f"   Status: {r.status_code}")
data = r.get_json()
check("Status 400", r.status_code == 400)
check("Error mentions 'not a voice channel'", "not a voice channel" in data.get("error", ""))

# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("5) POST /join — channel full (user_limit reached)")
print("=" * 60)
mock_media.rooms.clear()
mock_media.participants.clear()
room_name = f"synth_{server_id}_{channel_id}"
mock_media.create_room(room_name, max_participants=3)
for i in range(3):
    mock_media.add_fake_participant(room_name, f"user_{i}")
r = client.post(f"{VOICE_BASE}/join", headers=auth(owner_token))
print(f"   Status: {r.status_code}")
data = r.get_json()
check("Status 403", r.status_code == 403)
check("Error mentions 'full'", "full" in data.get("error", "").lower())

# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("6) GET /participants — list participants")
print("=" * 60)
mock_media.rooms.clear()
mock_media.participants.clear()
mock_media.create_room(room_name)
mock_media.add_fake_participant(room_name, owner["id"], "voice_owner")
mock_media.add_fake_participant(room_name, member["id"], "voice_member")
r = client.get(f"{VOICE_BASE}/participants", headers=auth(owner_token))
data = r.get_json()
print(f"   Status: {r.status_code}")
check("Status 200", r.status_code == 200)
check("2 participants", len(data.get("participants", [])) == 2)

# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("7) POST /leave — owner leaves voice channel")
print("=" * 60)
r = client.post(f"{VOICE_BASE}/leave", headers=auth(owner_token))
print(f"   Status: {r.status_code}")
data = r.get_json()
check("Status 200", r.status_code == 200)
check("Success message", "Left" in data.get("message", ""))
# Verify removed
remaining = mock_media.list_participants(room_name)
check("Owner no longer in participants", all(p.identity != owner["id"] for p in remaining))

# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("8) DELETE /participants/<id> — kick a participant")
print("=" * 60)
mock_media.rooms.clear()
mock_media.participants.clear()
mock_media.create_room(room_name)
mock_media.add_fake_participant(room_name, member["id"], "voice_member")
r = client.delete(
    f"{VOICE_BASE}/participants/{member['id']}",
    headers=auth(owner_token),
)
print(f"   Status: {r.status_code}")
data = r.get_json()
check("Status 200", r.status_code == 200)
check("Removed message", "removed" in data.get("message", "").lower())
remaining = mock_media.list_participants(room_name)
check("Member removed", all(p.identity != member["id"] for p in remaining))

# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("9) DELETE /participants/<id> — member (no kick_user) → 403")
print("=" * 60)
mock_media.add_fake_participant(room_name, owner["id"], "voice_owner")
r = client.delete(
    f"{VOICE_BASE}/participants/{owner['id']}",
    headers=auth(member_token),
)
print(f"   Status: {r.status_code}")
check("Status 403", r.status_code == 403)

# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("10) POST /participants/<id>/mute — mute a track")
print("=" * 60)
mock_media.rooms.clear()
mock_media.participants.clear()
mock_media.create_room(room_name)
track = TrackInfo(sid="TR_audio_001", name="microphone", kind="audio", muted=False)
mock_media.add_fake_participant(room_name, member["id"], "voice_member", tracks=[track])
r = client.post(
    f"{VOICE_BASE}/participants/{member['id']}/mute",
    json={"track_sid": "TR_audio_001", "muted": True},
    headers=auth(owner_token),
)
print(f"   Status: {r.status_code}")
data = r.get_json()
check("Status 200", r.status_code == 200)
check("Muted message", "muted" in data.get("message", "").lower())
# Verify the mock track is now muted
p = mock_media.list_participants(room_name)[0]
check("Track muted in mock", p.tracks[0].muted is True)

# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("11) POST /participants/<id>/mute — member (no mute_user) → 403")
print("=" * 60)
r = client.post(
    f"{VOICE_BASE}/participants/{owner['id']}/mute",
    json={"track_sid": "TR_audio_001", "muted": True},
    headers=auth(member_token),
)
print(f"   Status: {r.status_code}")
check("Status 403", r.status_code == 403)

# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("12) POST /join — unauthenticated → 401")
print("=" * 60)
r = client.post(f"{VOICE_BASE}/join")
print(f"   Status: {r.status_code}")
check("Status 401", r.status_code == 401)

# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("13) GET /participants — text channel → 400")
print("=" * 60)
r = client.get(f"{TEXT_VOICE}/participants", headers=auth(owner_token))
print(f"   Status: {r.status_code}")
check("Status 400", r.status_code == 400)

# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("14) POST /leave — idempotent (already left)")
print("=" * 60)
mock_media.rooms.clear()
mock_media.participants.clear()
r = client.post(f"{VOICE_BASE}/leave", headers=auth(owner_token))
print(f"   Status: {r.status_code}")
check("Status 200 (idempotent)", r.status_code == 200)


# ════════════════════════════════════════════════════════════
# Summary
# ════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print(f"Voice tests: {passed}/{total} passed")
print("=" * 60)

if passed < total:
    sys.exit(1)
