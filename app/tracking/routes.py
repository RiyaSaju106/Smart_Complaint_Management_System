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


@tracking_bp.get("/complaints/<complaint_id>/status")
def get_complaint_status(complaint_id):
    conn, cur, complaint, problem = _tracking_request(complaint_id)

    if problem:
        return problem

    try:
        return jsonify({
            "complaint_id": complaint["complaint_id"],
            "status": complaint["status"],
            "updated_at": _iso(complaint["updated_at"]),
        }), 200
    finally:
        cur.close()
        conn.close()


@tracking_bp.get("/complaints/<complaint_id>/history")
def get_complaint_history(complaint_id):
    conn, cur, complaint, problem = _tracking_request(complaint_id)

    if problem:
        return problem

    try:
        cur.execute(
            """
            SELECT
                h.old_status,
                h.new_status,
                h.changed_by,
                u.name AS changed_by_name,
                h.remarks,
                h.changed_at
            FROM status_history AS h
            JOIN users AS u ON u.user_id = h.changed_by
            WHERE h.complaint_id = %s
            ORDER BY h.changed_at ASC, h.history_id ASC
            """,
            (complaint_id,),
        )

        rows = cur.fetchall()

        items = [
            {
                "old_status": row["old_status"],
                "new_status": row["new_status"],
                "changed_by": {
                    "user_id": row["changed_by"],
                    "name": row["changed_by_name"],
                },
                "remarks": row["remarks"],
                "changed_at": _iso(row["changed_at"]),
            }
            for row in rows
        ]

        return jsonify({
            "complaint_id": complaint["complaint_id"],
            "items": items,
        }), 200
    finally:
        cur.close()
        conn.close()