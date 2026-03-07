from flask import Blueprint as FlaskBlueprint, request, jsonify
from flask_smorest import Blueprint

from app.middleware.auth_middleware import auth_required, permission_required
from app.services.role_service import RoleError
from app.services import role_service
from app.models import role as role_model
from app.schemas import (
    CreateRoleSchema, UpdateRoleSchema, AssignRevokeSchema,
    RoleResponseSchema, RoleListSchema, PermissionListSchema,
    MessageSchema,
)

blp = Blueprint(
    "roles", __name__,
    url_prefix="/api/servers/<server_id>/roles",
    description="Roles & permissions — RBAC management (server-scoped)",
)

BEARER = [{"BearerAuth": []}]


# ── GET /api/servers/<server_id>/roles  —  list all roles ──
@blp.route("", methods=["GET"])
@blp.doc(security=BEARER)
@blp.response(200, RoleListSchema)
@auth_required
def list_roles(server_id, current_user=None):
    roles = role_service.list_roles()
    return jsonify({"roles": roles}), 200


# ── POST /api/servers/<server_id>/roles  —  create a role ──
@blp.route("", methods=["POST"])
@blp.doc(security=BEARER)
@blp.arguments(CreateRoleSchema)
@blp.response(201, RoleResponseSchema)
@blp.alt_response(403, description="Insufficient permissions")
@blp.alt_response(409, description="Role name taken")
@auth_required
@permission_required("manage_roles")
def create_role(data, server_id, current_user=None):
    try:
        role = role_service.create_role(
            name=data.get("name", "").strip(),
            permissions=data.get("permissions", []),
            is_default=data.get("is_default", False),
        )
    except RoleError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"role": role}), 201


# ── GET /api/servers/<server_id>/roles/permissions  —  list valid perms
@blp.route("/permissions", methods=["GET"])
@blp.doc(security=BEARER)
@blp.response(200, PermissionListSchema)
@auth_required
def list_permissions(server_id, current_user=None):
    return jsonify({"permissions": role_model.ALL_PERMISSIONS}), 200


# ── POST /api/servers/<server_id>/roles/assign  —  assign role to user
@blp.route("/assign", methods=["POST"])
@blp.doc(security=BEARER)
@blp.arguments(AssignRevokeSchema)
@blp.response(200, MessageSchema)
@blp.alt_response(403, description="Insufficient permissions")
@blp.alt_response(404, description="User or role not found")
@auth_required
@permission_required("assign_roles")
def assign_role(data, server_id, current_user=None):
    user_id = data.get("user_id", "")
    role_id = data.get("role_id", "")
    if not user_id or not role_id:
        return jsonify({"error": "user_id and role_id are required."}), 400
    try:
        role_service.assign_role_to_user(user_id, role_id, server_id)
    except RoleError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"message": "Role assigned."}), 200


# ── POST /api/servers/<server_id>/roles/revoke  —  revoke role from user
@blp.route("/revoke", methods=["POST"])
@blp.doc(security=BEARER)
@blp.arguments(AssignRevokeSchema)
@blp.response(200, MessageSchema)
@blp.alt_response(403, description="Insufficient permissions")
@auth_required
@permission_required("assign_roles")
def revoke_role(data, server_id, current_user=None):
    user_id = data.get("user_id", "")
    role_id = data.get("role_id", "")
    if not user_id or not role_id:
        return jsonify({"error": "user_id and role_id are required."}), 400
    try:
        role_service.revoke_role_from_user(user_id, role_id, server_id)
    except RoleError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"message": "Role revoked."}), 200


# ── GET /api/servers/<server_id>/roles/user/<user_id>  —  get user roles in server
@blp.route("/user/<user_id>", methods=["GET"])
@blp.doc(security=BEARER)
@blp.response(200, RoleListSchema)
@auth_required
def get_user_roles(server_id, user_id, current_user=None):
    try:
        roles = role_service.get_user_roles(user_id, server_id)
    except RoleError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"roles": roles}), 200


# ── GET /api/servers/<server_id>/roles/<id>  —  get one role
@blp.route("/<role_id>", methods=["GET"])
@blp.doc(security=BEARER)
@blp.response(200, RoleResponseSchema)
@blp.alt_response(404, description="Role not found")
@auth_required
def get_role(server_id, role_id, current_user=None):
    try:
        role = role_service.get_role(role_id)
    except RoleError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"role": role}), 200


# ── PUT /api/servers/<server_id>/roles/<id>  —  update a role
@blp.route("/<role_id>", methods=["PUT"])
@blp.doc(security=BEARER)
@blp.arguments(UpdateRoleSchema)
@blp.response(200, RoleResponseSchema)
@blp.alt_response(403, description="Insufficient permissions")
@auth_required
@permission_required("manage_roles")
def update_role(data, server_id, role_id, current_user=None):
    try:
        role = role_service.update_role(role_id, data)
    except RoleError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"role": role}), 200


# ── DELETE /api/servers/<server_id>/roles/<id>  —  delete a role
@blp.route("/<role_id>", methods=["DELETE"])
@blp.doc(security=BEARER)
@blp.response(200, MessageSchema)
@blp.alt_response(403, description="Cannot delete built-in or insufficient permissions")
@auth_required
@permission_required("manage_roles")
def delete_role(server_id, role_id, current_user=None):
    try:
        role_service.delete_role(role_id)
    except RoleError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"message": "Role deleted."}), 200
