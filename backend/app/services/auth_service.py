import bcrypt
import hashlib
import secrets
from datetime import datetime, timezone, timedelta

import resend
from flask import current_app
from pymongo.errors import DuplicateKeyError

from app.models import user as user_model
from app.models import role as role_model


class AuthError(Exception):
    """Custom auth exception with an HTTP status code."""
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def register(username: str, email: str, password: str) -> dict:
    """
    Register a new user.
    Returns the serialised user dict.
    Raises AuthError on validation / duplicate issues.
    """
    # ── Validation ──────────────────────────────────────────
    if not username or len(username) < 3:
        raise AuthError("Username must be at least 3 characters.")
    if not email or "@" not in email:
        raise AuthError("A valid email is required.")
    if not password or len(password) < 6:
        raise AuthError("Password must be at least 6 characters.")

    # ── Hash password ───────────────────────────────────────
    password_hash = bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")

    # ── Insert ──────────────────────────────────────────────
    try:
        user_id = user_model.create(username, email, password_hash)
    except DuplicateKeyError as exc:
        key = str(exc)
        if "email" in key:
            raise AuthError("Email already registered.", 409)
        raise AuthError("Username already taken.", 409)

    # Roles are now assigned per-server (on join), not globally.

    user = user_model.find_by_id(user_id)
    return user_model.to_dict(user)


def login(email: str, password: str) -> dict:
    """
    Authenticate by email + password.
    Returns the serialised user dict.
    Raises AuthError if credentials are invalid.
    """
    if not email or not password:
        raise AuthError("Email and password are required.")

    user = user_model.find_by_email(email)
    if user is None:
        raise AuthError("Invalid email or password.", 401)

    if not bcrypt.checkpw(password.encode("utf-8"),
                          user["password_hash"].encode("utf-8")):
        raise AuthError("Invalid email or password.", 401)

    # Mark user as online
    user_model.set_online(str(user["_id"]), True)

    return user_model.to_dict(user)


def forgot_password(email: str) -> None:
    """
    Generate a one-time reset token, persist its SHA-256 hash in the DB,
    and e-mail the raw token to the user.
    Always returns None — never reveal whether the email exists.
    """
    user = user_model.find_by_email(email)
    if not user:
        return  # Silent — prevents email enumeration

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expires = datetime.now(timezone.utc) + timedelta(hours=1)

    user_model.set_reset_token(str(user["_id"]), token_hash, expires)

    frontend_url = current_app.config.get("FRONTEND_URL", "http://localhost:5173")
    reset_link = f"{frontend_url}/reset-password?token={raw_token}"

    resend.api_key = current_app.config["RESEND_API_KEY"]
    resend.Emails.send({
        "from": current_app.config.get("MAIL_DEFAULT_SENDER", "Synth <onboarding@resend.dev>"),
        "to": [user["email"]],
        "subject": "Reset your Synth password",
        "text": (
            f"Hi {user['username']},\n\n"
            "Someone requested a password reset for your Synth account.\n"
            "Click the link below to choose a new password (expires in 1 hour):\n\n"
            f"{reset_link}\n\n"
            "If you didn't request this, you can safely ignore this email."
        ),
    })


def reset_password(raw_token: str, new_password: str) -> None:
    """
    Validate the reset token and update the user's password.
    Raises AuthError if the token is invalid / expired.
    """
    if not new_password or len(new_password) < 6:
        raise AuthError("Password must be at least 6 characters.")

    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    user = user_model.find_by_reset_token(token_hash)
    if not user:
        raise AuthError("Reset link is invalid or has expired.", 400)

    new_hash = bcrypt.hashpw(
        new_password.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")

    user_model.update_password_and_clear_token(str(user["_id"]), new_hash)
