"""Status and status-history read endpoints (Issue #26)."""

from flask import jsonify, session

from app.access import (
    RESIDENT,
    MAINTENANCE_STAFF,
    ADMINISTRATOR,
    error,
)
from db.connection import get_connection
from app.tracking import tracking_bp


def _iso(value):
    return value.isoformat() if value is not None else None


def _user_id():
    """Return the logged-in user's ID, if present."""
    return session.get("user_id")


def _can_view_complaint(cur, complaint, user_id, role):
    """Check whether the caller is allowed to view this complaint."""
    if role == ADMINISTRATOR:
        return True

    if role == RESIDENT:
        return str(complaint["resident_id"]) == str(user_id)

    if role == MAINTENANCE_STAFF:
        cur.execute(
            """
            SELECT staff_id
            FROM assignments
            WHERE complaint_id = %s
              AND is_current = TRUE
            """,
            (complaint["complaint_id"],),
        )
        assignment = cur.fetchone()

        return (
            assignment is not None
            and str(assignment["staff_id"]) == str(user_id)
        )

    return False


def _load_authorized_complaint(cur, complaint_id, user_id, role):
    """Return the complaint, or an appropriate HTTP error response."""
    cur.execute(
        """
        SELECT complaint_id, resident_id, status, updated_at
        FROM complaints
        WHERE complaint_id = %s
        """,
        (complaint_id,),
    )
    complaint = cur.fetchone()

    if complaint is None:
        return None, error(404, "NOT_FOUND", "Complaint not found.")

    if not _can_view_complaint(cur, complaint, user_id, role):
        return None, error(
            403,
            "FORBIDDEN",
            "You do not have permission to view this complaint.",
        )

    return complaint, None


def _tracking_request(complaint_id):
    """Open a connection and authorize access to a complaint."""
    user_id = _user_id()

    if not user_id:
        return None, None, None, error(
            401,
            "UNAUTHENTICATED",
            "Authentication is required.",
        )

    role = session.get("role")

    if role not in (RESIDENT, MAINTENANCE_STAFF, ADMINISTRATOR):
        return None, None, None, error(
            403,
            "FORBIDDEN",
            "You do not have permission to view this complaint.",
        )

    conn = get_connection()

    try:
        cur = conn.cursor()
        complaint, problem = _load_authorized_complaint(
            cur,
            complaint_id,
            user_id,
            role,
        )

        if problem:
            cur.close()
            conn.close()
            return None, None, None, problem

        return conn, cur, complaint, None

    except Exception:
        conn.close()
        raise
