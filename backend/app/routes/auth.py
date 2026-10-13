from datetime import timedelta
from flask import current_app, jsonify
from flask_smorest import Blueprint
from flask_jwt_extended import create_access_token

from app.services.auth_service import (
    AuthError, register, login, forgot_password, reset_password,
)
from app.middleware.auth_middleware import auth_required
from app.models import user as user_model
from app.models import desktop_session
from app.schemas import (
    RegisterSchema, LoginSchema,
    AuthResponseSchema, UserResponseSchema,
    ForgotPasswordSchema, ResetPasswordSchema,
    RefreshSessionSchema, RevokeSessionSchema,
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
        result = register(
            username=data.get("username", "").strip(),
            email=data.get("email", "").strip(),
            password=data.get("password", ""),
        )
    except AuthError as exc:
        return jsonify({"error": exc.message}), exc.status_code

    token = create_access_token(identity=result.user["id"],
                                additional_claims={"session_version": result.session_version})

    return jsonify({"user": result.user, "access_token": token}), 201


# ── POST /api/auth/login ───────────────────────────────────
@blp.route("/login", methods=["POST"])
@blp.arguments(LoginSchema)
@blp.response(200, AuthResponseSchema)
@blp.alt_response(401, description="Invalid credentials")
def login_route(data):
    try:
        result = login(
            email=data.get("email", "").strip(),
            password=data.get("password", ""),
        )
    except AuthError as exc:
        return jsonify({"error": exc.message}), exc.status_code

    if data.get("persistent"):
        try:
            session, refresh, revocation = desktop_session.create(result.user["id"], result.session_version)
        except desktop_session.DesktopSessionError as exc:
            return jsonify({"error": str(exc), "code": "session_revoked"}), 401
        return jsonify(_desktop_tokens(session, refresh, revocation, result.user)), 200

    token = create_access_token(identity=result.user["id"],
                                additional_claims={"session_version": result.session_version})

    return jsonify({"user": result.user, "access_token": token}), 200


def _desktop_tokens(session, refresh=None, revocation=None, user=None):
    lifetime = timedelta(minutes=current_app.config.get("DESKTOP_ACCESS_TOKEN_MINUTES", 15))
    token = create_access_token(identity=str(session["user_id"]), expires_delta=lifetime,
                                additional_claims={"session_version": session["session_version"],
                                                   "desktop_session": session["_id"]})
    data = {"access_token": token, "expires_in": int(lifetime.total_seconds())}
    if user is not None:
        data["user"] = user
    if refresh is not None:
        data["refresh_token"] = refresh
    if revocation is not None:
        data["revocation_token"] = revocation
    return data


@blp.route("/refresh", methods=["POST"])
@blp.arguments(RefreshSessionSchema)
@blp.response(200, AuthResponseSchema)
def refresh_session(data):
    try:
        session = desktop_session.rotate(data["refresh_token"], data["next_refresh_token"])
    except desktop_session.DesktopSessionError as exc:
        return jsonify({"error": str(exc), "code": "session_revoked"}), 401
    return jsonify(_desktop_tokens(session, data["next_refresh_token"])), 200


@blp.route("/logout", methods=["POST"])
@blp.arguments(RevokeSessionSchema)
def revoke_session(data):
    try:
        desktop_session.revoke(data["revocation_token"])
    except desktop_session.DesktopSessionError:
        pass  # Idempotent; never reveal whether a credential or account exists.
    return jsonify({"message": "Signed out."}), 200


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
