"""Smoke test for roles & permissions endpoints (server-scoped)."""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app import create_app
from app.extensions import mongo

app = create_app("development")
client = app.test_client()

# -- Cleanup previous test data --
with app.app_context():
    mongo.db.users.delete_many({"email": {"$in": [
        "admin@test.com", "mod@test.com", "member@test.com",
    ]}})
    mongo.db.servers.delete_many({"name": "RoleTestServer"})
    mongo.db.user_roles.delete_many({})

# -- Helper --
def register(username, email, password):
    r = client.post("/api/auth/register", json={
        "username": username, "email": email, "password": password,
    })
    assert r.status_code == 201, f"Register failed: {r.get_json()}"
    return r.get_json()

def login(email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"Login failed: {r.get_json()}"
    return r.get_json()["access_token"]

def headers(token):
    return {"Authorization": f"Bearer {token}"}


# -- Setup: create users and a server --
reg_owner = register("roleowner", "admin@test.com", "password123")
owner_token = reg_owner["access_token"]
owner_id = reg_owner["user"]["id"]

reg_member = register("rolemember", "member@test.com", "password123")
member_token = reg_member["access_token"]
member_id = reg_member["user"]["id"]

# Create a server (owner gets admin role automatically)
r = client.post("/api/servers", json={"name": "RoleTestServer"}, headers=headers(owner_token))
assert r.status_code == 201, f"Server creation failed: {r.get_json()}"
server_id = r.get_json()["server"]["id"]

# Member joins (gets default 'member' role)
r = client.post(f"/api/servers/{server_id}/join", headers=headers(member_token))
assert r.status_code == 200

ROLES_BASE = f"/api/servers/{server_id}/roles"


# ====================================================================
print("=" * 60)
print("1) Member joins server -> auto-assigned 'member' role")
print("=" * 60)
r = client.get(f"{ROLES_BASE}/user/{member_id}", headers=headers(owner_token))
user_roles = r.get_json()["roles"]
print(f"   Roles: {[rl['name'] for rl in user_roles]}")
assert len(user_roles) == 1, f"Expected 1 role, got {len(user_roles)}"
assert user_roles[0]["name"] == "member"
print("   OK: Member auto-assigned 'member' role in server")
print()

# ====================================================================
print("=" * 60)
print("2) GET roles -> list all roles (as member)")
print("=" * 60)
r = client.get(ROLES_BASE, headers=headers(member_token))
print(f"   Status: {r.status_code}")
roles = r.get_json()["roles"]
role_names = [rl["name"] for rl in roles]
print(f"   Roles: {role_names}")
assert r.status_code == 200
assert "admin" in role_names
assert "moderator" in role_names
assert "member" in role_names
print("   OK: All 3 default roles present")
print()

# Save role IDs
admin_role_id = next(rl["id"] for rl in roles if rl["name"] == "admin")
mod_role_id = next(rl["id"] for rl in roles if rl["name"] == "moderator")
member_role_id = next(rl["id"] for rl in roles if rl["name"] == "member")

# ====================================================================
print("=" * 60)
print("3) POST roles -> create role (member -> should fail 403)")
print("=" * 60)
r = client.post(ROLES_BASE, headers=headers(member_token), json={
    "name": "vip", "permissions": ["join_channel", "speak"],
})
print(f"   Status: {r.status_code}")
assert r.status_code == 403
print("   OK: Member correctly denied manage_roles")
print()

# ====================================================================
print("=" * 60)
print("4) Owner has admin role -> can create roles")
print("=" * 60)
r = client.get(f"{ROLES_BASE}/user/{owner_id}", headers=headers(owner_token))
owner_roles = [rl["name"] for rl in r.get_json()["roles"]]
print(f"   Owner roles in server: {owner_roles}")
assert "admin" in owner_roles
print("   OK: Owner has admin role in server")
print()

# ====================================================================
print("=" * 60)
print("5) POST roles -> create role (as owner/admin)")
print("=" * 60)
r = client.post(ROLES_BASE, headers=headers(owner_token), json={
    "name": "vip",
    "permissions": ["join_channel", "speak", "join_any_channel"],
})
print(f"   Status: {r.status_code}")
assert r.status_code == 201
vip_role_id = r.get_json()["role"]["id"]
print("   OK: Admin created 'vip' role")
print()

# ====================================================================
print("=" * 60)
print("6) PUT roles/<id> -> update role (as admin)")
print("=" * 60)
r = client.put(f"{ROLES_BASE}/{vip_role_id}", headers=headers(owner_token), json={
    "permissions": ["join_channel", "speak", "join_any_channel", "mute_user"],
})
print(f"   Status: {r.status_code}")
assert r.status_code == 200
assert "mute_user" in r.get_json()["role"]["permissions"]
print("   OK: VIP role updated with mute_user permission")
print()

# ====================================================================
print("=" * 60)
print("7) POST roles/assign -> assign mod role to member in this server")
print("=" * 60)
r = client.post(f"{ROLES_BASE}/assign", headers=headers(owner_token), json={
    "user_id": member_id,
    "role_id": mod_role_id,
})
print(f"   Status: {r.status_code}")
assert r.status_code == 200
print("   OK: Moderator role assigned to member in this server")
print()

# ====================================================================
print("=" * 60)
print("8) GET roles/user/<id> -> check user has 2 roles in this server")
print("=" * 60)
r = client.get(f"{ROLES_BASE}/user/{member_id}", headers=headers(owner_token))
user_role_names = [rl["name"] for rl in r.get_json()["roles"]]
print(f"   Roles: {user_role_names}")
assert "member" in user_role_names
assert "moderator" in user_role_names
print("   OK: User has both member and moderator roles")
print()

# ====================================================================
print("=" * 60)
print("9) POST roles/revoke -> revoke mod role (as admin)")
print("=" * 60)
r = client.post(f"{ROLES_BASE}/revoke", headers=headers(owner_token), json={
    "user_id": member_id,
    "role_id": mod_role_id,
})
print(f"   Status: {r.status_code}")
assert r.status_code == 200
r2 = client.get(f"{ROLES_BASE}/user/{member_id}", headers=headers(owner_token))
remaining = [rl["name"] for rl in r2.get_json()["roles"]]
print(f"   Remaining roles: {remaining}")
assert "moderator" not in remaining
print("   OK: Moderator role revoked successfully")
print()

# ====================================================================
print("=" * 60)
print("10) DELETE roles/<id> -> delete custom role (as admin)")
print("=" * 60)
r = client.delete(f"{ROLES_BASE}/{vip_role_id}", headers=headers(owner_token))
print(f"   Status: {r.status_code}")
assert r.status_code == 200
print("   OK: VIP role deleted")
print()

# ====================================================================
print("=" * 60)
print("11) DELETE built-in role -> should fail 403")
print("=" * 60)
r = client.delete(f"{ROLES_BASE}/{admin_role_id}", headers=headers(owner_token))
print(f"   Status: {r.status_code}")
assert r.status_code == 403
print("   OK: Cannot delete built-in 'admin' role")
print()

# ====================================================================
print("=" * 60)
print("12) GET roles/permissions -> list all valid permissions")
print("=" * 60)
r = client.get(f"{ROLES_BASE}/permissions", headers=headers(member_token))
print(f"   Status: {r.status_code}")
perms = r.get_json()["permissions"]
print(f"   Permissions: {perms}")
assert r.status_code == 200
assert "manage_channels" in perms
print("   OK: Permission list returned")
print()

# -- Cleanup --
with app.app_context():
    mongo.db.users.delete_many({"email": {"$in": [
        "admin@test.com", "mod@test.com", "member@test.com",
    ]}})
    mongo.db.servers.delete_many({"name": "RoleTestServer"})
    mongo.db.user_roles.delete_many({})
    mongo.db.roles.delete_many({"name": "vip"})
    print("Cleaned up")

print()
print("ALL 12 TESTS PASSED!")
