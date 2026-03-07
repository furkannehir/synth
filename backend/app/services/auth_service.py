import bcrypt
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
