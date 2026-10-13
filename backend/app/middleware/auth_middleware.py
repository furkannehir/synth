from functools import wraps
import time

from bson import ObjectId
from flask import jsonify, request
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity, get_jwt

from app.models import user as user_model
from app.models import role as role_model
from app.models import server as server_model
from app.models import desktop_session


class SessionError(Exception):
    pass


def ensure_session(user_id: str, claims: dict) -> dict:
    """Check a verified JWT against current account state, also during SSE."""
    version = claims.get("session_version", 0)  # pre-upgrade sessions are version 0
    expires = claims.get("exp", 0)
    if (not ObjectId.is_valid(user_id) or type(version) is not int
            or type(expires) is not int or expires <= time.time()):
        raise SessionError("Session expired. Please sign in again.")
    user = user_model.find_by_id(user_id)
    if user is None or user.get("session_version", 0) != version:
        raise SessionError("Session expired. Please sign in again.")
    if "desktop_session" in claims and not desktop_session.is_active(claims["desktop_session"], user_id, version):
        raise SessionError("Session expired. Please sign in again.")
    return user


def auth_required(fn):
    """
    Decorator that verifies the JWT and injects `current_user` dict.

    Accepts the token either as:
    - Authorization: Bearer <token>   (standard — used by all API calls)
    - ?token=<token>                  (query param — used by EventSource/SSE
                                       because the browser EventSource API
                                       cannot set custom headers)
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        # If the Authorization header is absent, try the ?token= query param.
        # We do this by temporarily injecting it into the request environ so
        # flask-jwt-extended's verify_jwt_in_request() finds it normally.
        qs_token = request.args.get("token")
        if qs_token and "Authorization" not in request.headers:
            request.environ["HTTP_AUTHORIZATION"] = f"Bearer {qs_token}"

        verify_jwt_in_request()
        user_id = get_jwt_identity()
        try:
            user = ensure_session(user_id, get_jwt())
        except SessionError as exc:
            return jsonify({"error": str(exc), "code": "session_revoked"}), 401
        # Validate resource IDs before any view or permission check converts
        # them, and use one spelling for comparisons and realtime topics.
        # DMs retain their conversation-specific validation/error contract.
        if request.blueprint != "dms":
            resources = {
                "server_id": "Server", "channel_id": "Channel",
                "message_id": "Message", "role_id": "Role",
                "user_id": "User", "friend_id": "User",
                "request_id": "Friend request",
            }
            for parameter, resource in resources.items():
                if parameter in kwargs:
                    if not ObjectId.is_valid(kwargs[parameter]):
                        return jsonify({"error": f"{resource} not found."}), 404
                    kwargs[parameter] = str(ObjectId(kwargs[parameter]))
        kwargs["current_user"] = user
        return fn(*args, **kwargs)
    return wrapper


def permission_required(*permissions):
    """
    Decorator that checks the authenticated user has ALL of the listed
    permissions **within the server** identified by the ``server_id``
    URL parameter.  Must be placed *after* @auth_required.

    Server owners automatically have every permission.

    Usage:
        @blp.route("/<server_id>/channels", methods=["POST"])
        @auth_required
        @permission_required("manage_channels")
        def create_channel(server_id, current_user=None):
            ...
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            current_user = kwargs.get("current_user")
            if current_user is None:
                return jsonify({"error": "Authentication required."}), 401

            user_id = str(current_user["_id"])

            # Resolve server_id from route kwargs or view args
            server_id = kwargs.get("server_id") or request.view_args.get("server_id")
            if not server_id:
                return jsonify({"error": "Server context required."}), 400

            if not ObjectId.is_valid(server_id):
                return jsonify({"error": "Server not found."}), 404
            server = server_model.find_by_id(server_id)
            if server is None:
                return jsonify({"error": "Server not found."}), 404
            # Server owners bypass permission checks.
            if str(server.get("owner_id")) == user_id:
                return fn(*args, **kwargs)
            if not server_model.is_member(server_id, user_id):
                return jsonify({"error": "You must be a member of this server."}), 403

            user_perms = role_model.get_user_permissions(user_id, server_id)

            missing = set(permissions) - user_perms
            if missing:
                return jsonify({
                    "error": "You do not have permission to perform this action.",
                    "missing_permissions": sorted(missing),
                }), 403

            return fn(*args, **kwargs)
        return wrapper
    return decorator
