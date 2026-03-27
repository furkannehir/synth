from flask import jsonify
from flask_smorest import Blueprint
from flask_jwt_extended import create_access_token

from app.services.auth_service import (
    AuthError, register, login, forgot_password, reset_password,
)
from app.middleware.auth_middleware import auth_required
from app.models import user as user_model
from app.schemas import (
    RegisterSchema, LoginSchema,
    AuthResponseSchema, UserResponseSchema,
    ForgotPasswordSchema, ResetPasswordSchema,
)

blp = Blueprint(
    "auth", __name__,
    url_prefix="/api/auth",
    description="Authentication — register, login, current user, password reset",
)


# ── POST /api/auth/register ────────────────────────────────
@blp.route("/register", methods=["POST"])
@blp.arguments(RegisterSchema)
@blp.response(201, AuthResponseSchema)
@blp.alt_response(400, description="Validation error")
@blp.alt_response(409, description="Duplicate email or username")
def register_route(data):
    try:
        user = register(
            username=data.get("username", "").strip(),
            email=data.get("email", "").strip(),
            password=data.get("password", ""),
        )
    except AuthError as exc:
        return jsonify({"error": exc.message}), exc.status_code

    token = create_access_token(identity=user["id"])

    return jsonify({"user": user, "access_token": token}), 201


# ── POST /api/auth/login ───────────────────────────────────
@blp.route("/login", methods=["POST"])
@blp.arguments(LoginSchema)
@blp.response(200, AuthResponseSchema)
@blp.alt_response(401, description="Invalid credentials")
def login_route(data):
    try:
        user = login(
            email=data.get("email", "").strip(),
            password=data.get("password", ""),
        )
    except AuthError as exc:
        return jsonify({"error": exc.message}), exc.status_code

    token = create_access_token(identity=user["id"])

    return jsonify({"user": user, "access_token": token}), 200


# ── GET /api/auth/me ────────────────────────────────────────
@blp.route("/me", methods=["GET"])
@blp.doc(security=[{"BearerAuth": []}])
@blp.response(200, UserResponseSchema)
@auth_required
def me_route(current_user=None):
    return jsonify({"user": user_model.to_dict(current_user)}), 200


# ── POST /api/auth/forgot-password ───────────────────────────────
@blp.route("/forgot-password", methods=["POST"])
@blp.arguments(ForgotPasswordSchema)
@blp.alt_response(400, description="Validation error")
def forgot_password_route(data):
    """Always returns 200 to prevent e-mail enumeration."""
    try:
        forgot_password(data.get("email", "").strip().lower())
    except Exception:
        pass  # Swallow ALL errors — never reveal whether the email exists
    return jsonify({"message": "If that email is registered, a reset link has been sent."}), 200


# ── POST /api/auth/reset-password ───────────────────────────────
@blp.route("/reset-password", methods=["POST"])
@blp.arguments(ResetPasswordSchema)
@blp.alt_response(400, description="Invalid or expired token")
def reset_password_route(data):
    try:
        reset_password(
            raw_token=data.get("token", ""),
            new_password=data.get("new_password", ""),
        )
    except AuthError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify({"message": "Password updated successfully."}), 200
