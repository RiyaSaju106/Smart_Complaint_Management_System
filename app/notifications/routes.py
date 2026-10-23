"""Notification endpoints (FR-019): a logged-in user reads and acknowledges their OWN notifications.

    GET   /api/notifications                       list mine, newest first (?unread=true, ?limit=N)
    PATCH /api/notifications/<notification_id>/read  mark one of mine as read
    PATCH /api/notifications/read-all              mark all of mine as read

Every query is scoped to the session's user_id, which is set at login and never taken from the
request, so a user cannot read or change another user's notifications (TC-NTF-02).
"""
import pymysql
from flask import Blueprint, current_app, jsonify, request, session

from app.access import error
from db.connection import get_connection

notifications_bp = Blueprint("notifications", __name__, url_prefix="/api/notifications")

DEFAULT_LIMIT = 50
MAX_LIMIT = 100

COLUMNS = "notification_id, complaint_id, event, message, is_read, created_at"


@notifications_bp.errorhandler(pymysql.MySQLError)
def database_error(exc):
    current_app.logger.error("Database error in notification module: %s", exc, exc_info=exc)
    return error(500, "DATABASE_ERROR", "A database error occurred. Please try again.")


@notifications_bp.before_request
def require_login():
    if not session.get("user_id"):
        return error(401, "UNAUTHENTICATED", "Please log in.")
    return None


def _serialize(row):
    created = row["created_at"]
    return {
        "notification_id": row["notification_id"],
        "complaint_id": row["complaint_id"],
        "event": row["event"],
        "message": row["message"],
        "is_read": bool(row["is_read"]),
        "created_at": created.isoformat() if created is not None else None,
    }


def _parse_list_args(args):
    """Returns (unread_only, limit, error_message)."""
    unread = args.get("unread")
    if unread is None:
        unread_only = False
    elif unread in ("true", "false"):
        unread_only = unread == "true"
    else:
        return None, None, "'unread' must be 'true' or 'false'."

    raw_limit = args.get("limit")
    if raw_limit is None:
        return unread_only, DEFAULT_LIMIT, None
    try:
        limit = int(raw_limit)
    except ValueError:
        return None, None, f"'limit' must be a whole number from 1 to {MAX_LIMIT}."
    if not 1 <= limit <= MAX_LIMIT:
        return None, None, f"'limit' must be a whole number from 1 to {MAX_LIMIT}."
    return unread_only, limit, None


@notifications_bp.get("")
def list_notifications():
    unread_only, limit, problem = _parse_list_args(request.args)
    if problem:
        return error(400, "VALIDATION_ERROR", problem)

    user_id = session["user_id"]
    sql = f"SELECT {COLUMNS} FROM notifications WHERE user_id = %s"
    if unread_only:
        sql += " AND is_read = FALSE"
    sql += " ORDER BY created_at DESC, notification_id LIMIT %s"

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (user_id, limit))
            rows = cur.fetchall()
            cur.execute(
                "SELECT COUNT(*) AS n FROM notifications WHERE user_id = %s AND is_read = FALSE",
                (user_id,),
            )
            unread_count = cur.fetchone()["n"]
    finally:
        conn.close()

    return jsonify({
        "notifications": [_serialize(r) for r in rows],
        "unread_count": unread_count,
    }), 200


@notifications_bp.patch("/<notification_id>/read")
def mark_read(notification_id):
    user_id = session["user_id"]
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT user_id, {COLUMNS} FROM notifications WHERE notification_id = %s",
                (notification_id,),
            )
            row = cur.fetchone()
            if row is None:
                return error(404, "NOT_FOUND", "Notification does not exist.")
            if row["user_id"] != user_id:
                return error(403, "FORBIDDEN", "You can only access your own notifications.")
            if not row["is_read"]:
                cur.execute(
                    "UPDATE notifications SET is_read = TRUE "
                    "WHERE notification_id = %s AND user_id = %s",
                    (notification_id, user_id),
                )
                row["is_read"] = True
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return jsonify({"message": "Notification marked as read.", "notification": _serialize(row)}), 200


@notifications_bp.patch("/read-all")
def mark_all_read():
    user_id = session["user_id"]
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE notifications SET is_read = TRUE WHERE user_id = %s AND is_read = FALSE",
                (user_id,),
            )
            updated = cur.rowcount
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return jsonify({"message": "All notifications marked as read.", "updated": updated}), 200
