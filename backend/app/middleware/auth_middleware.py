from functools import wraps

from flask import jsonify, request
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity

from app.models import user as user_model
from app.models import role as role_model
from app.models import server as server_model


def auth_required(fn):
    """Decorator that verifies the JWT and injects `current_user` dict."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        user_id = get_jwt_identity()
        user = user_model.find_by_id(user_id)
        if user is None:
            return jsonify({"error": "User not found."}), 401
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

            # Server owners bypass permission checks
            server = server_model.find_by_id(server_id)
            if server and str(server.get("owner_id")) == user_id:
                return fn(*args, **kwargs)

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
