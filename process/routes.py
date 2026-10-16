"""Processing & Status module (SAD 3.4, 4.3): HTTP layer.

Staff view assigned complaints and move them assigned -> in_progress -> resolved; the resident who
raised the complaint, or an administrator, closes it.

How the module is split:
  routes.py   this file: authentication/role checks, the order of checks, transactions, responses
  schema.py   request validation and the allowed status transitions
  queries.py  PyMySQL SQL, one small function per query

Shared project pieces used here: db.connection.get_connection(), and app.access.role_required /
error (server-side session role, errors shaped {"error": {"code", "message"}}).

Run everything from the repository root (the folder that contains app/, db/ and this folder), e.g.
`python -m pytest tests/...`. Do not run this file directly: `app` would not be importable.
"""
import pymysql
from flask import Blueprint, current_app, jsonify, request, session

from app.access import ADMINISTRATOR, RESIDENT, error, role_required
from db.connection import get_connection

from . import queries, schema  # relative: works whatever this folder is named

# /api like the other modules (auth uses /api/auth). SAD 4.3 and the STP still say /api/v1.
processing_bp = Blueprint("processing", __name__, url_prefix="/api")

MAINTENANCE_STAFF = "maintenance_staff"


@processing_bp.errorhandler(pymysql.MySQLError)
def database_error(exc):
    """Any database failure becomes JSON in the project's error format, never an HTML 500 page.
    The details go to the log only; the client gets a generic message."""
    current_app.logger.error("Database error in processing module: %s", exc, exc_info=exc)
    return error(500, "DATABASE_ERROR", "A database error occurred. Please try again.")


def _body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _validation_error(message):
    return error(400, "VALIDATION_ERROR", message)


def _invalid_transition(old_status, new_status):
    return error(
        400,
        "INVALID_STATE_TRANSITION",
        f"Cannot transition complaint state from '{old_status}' to '{new_status}'.",
    )


def _iso(value):
    return value.isoformat() if value is not None else None


@processing_bp.get("/staff/complaints/assigned")
@role_required(MAINTENANCE_STAFF)
def assigned_complaints():
    status_filter = request.args.get("status")
    problem = schema.parse_status_filter(status_filter)
    if problem:
        return _validation_error(problem)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            rows = queries.list_assigned(cur, session["user_id"], status_filter)
    finally:
        conn.close()

    data = [
        {
            "complaint_id": r["complaint_id"],
            "title": r["title"],
            "category": r["category"],
            "category_id": r["category_id"],
            "location": r["location"],
            "status": r["status"],
            "created_at": _iso(r["created_at"]),
        }
        for r in rows
    ]
    return jsonify({"status": "success", "data": data}), 200


@processing_bp.patch("/staff/complaints/<complaint_id>/status")
@role_required(MAINTENANCE_STAFF)
def update_status(complaint_id):
    parsed, problem = schema.parse_status_update(_body())
    if problem:
        return _validation_error(problem)
    new_status = parsed["status"]
    user_id = session["user_id"]

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            complaint = queries.lock_complaint(cur, complaint_id)
            if complaint is None:
                return error(404, "NOT_FOUND", "Complaint ID does not exist.")

            if queries.current_staff_id(cur, complaint_id) != user_id:
                return error(403, "FORBIDDEN", "You are not assigned to this complaint.")

            old_status = complaint["status"]
            if not schema.can_transition(old_status, new_status):
                return _invalid_transition(old_status, new_status)

            if new_status == "resolved":
                if not parsed["resolution_details"]:
                    return _validation_error(
                        "Resolution details are required to resolve a complaint."
                    )
                queries.insert_resolution(cur, complaint_id, user_id, parsed["resolution_details"])

            queries.insert_history(
                cur, complaint_id, old_status, new_status, user_id, parsed["remarks"]
            )
            updated_at = queries.set_status(cur, complaint_id, new_status)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return jsonify({
        "status": "success",
        "message": f"Complaint status updated from {old_status} to {new_status}.",
        "data": {
            "complaint_id": complaint_id,
            "status": new_status,
            "updated_at": _iso(updated_at),
        },
    }), 200


@processing_bp.patch("/complaints/<complaint_id>/close")
def close_complaint(complaint_id):
    # role_required allows one role; closing is open to two, so the check is inline.
    if "user_id" not in session:
        return error(401, "UNAUTHENTICATED", "Please log in.")
    role = session.get("role")
    if role not in (RESIDENT, ADMINISTRATOR):
        return error(403, "FORBIDDEN", "You do not have access to this action.")
    user_id = session["user_id"]

    data = _body()
    notes, problem = schema.parse_close(data)
    if problem:
        return _validation_error(problem)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            complaint = queries.lock_complaint(cur, complaint_id)
            if complaint is None:
                return error(404, "NOT_FOUND", "Complaint ID does not exist.")

            # Only the resident who raised the complaint, or an administrator, may close it.
            if role == RESIDENT and complaint["resident_id"] != user_id:
                return error(403, "FORBIDDEN", "Only the resident who raised this complaint can close it.")

            if not schema.is_confirmed(data):
                return _validation_error("Confirmation is required to close the complaint.")

            old_status = complaint["status"]
            if old_status != "resolved":
                return _invalid_transition(old_status, "closed")

            if not queries.has_resolution(cur, complaint_id):
                return _validation_error(
                    "A complaint cannot be closed without documented resolution details."
                )

            queries.insert_history(cur, complaint_id, old_status, "closed", user_id, notes)
            closed_at = queries.set_status(cur, complaint_id, "closed")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return jsonify({
        "status": "success",
        "message": "Complaint has been closed.",
        "data": {"complaint_id": complaint_id, "status": "closed", "closed_at": _iso(closed_at)},
    }), 200