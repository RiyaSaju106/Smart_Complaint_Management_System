from functools import wraps

from flask import jsonify, session

RESIDENT = "Resident"
ADMINISTRATOR = "Administrator"


def error(status, code, message):
    return jsonify({"error": {"code": code, "message": message}}), status


def role_required(role):
    """Allow the request only if the logged-in user's session role matches.

    The role is read from the server-side session set at login, never from
    the request, so the interface cannot grant itself extra privileges.
    """
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                return error(401, "UNAUTHENTICATED", "Please log in.")
            if session.get("role") != role:
                return error(403, "FORBIDDEN", "You do not have access to this page.")
            return view(*args, **kwargs)
        return wrapped
    return decorator
