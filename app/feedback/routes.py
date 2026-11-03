"""Feedback endpoints (FR-021, FR-022, SAD 4.3.6).

    POST /api/complaints/<complaint_id>/feedback   the resident who raised the complaint rates it
    GET  /api/complaints/<complaint_id>/feedback   read it: the owner, the assigned staff, administrators

Rules (SRS business rules, Rohan's STP 13.2):
  - Only the complaint's own resident can submit, and only once the complaint is Resolved (a
    Closed complaint has been through Resolved, so it is still eligible).
  - One feedback per complaint: a second submission is rejected and the first is left unchanged.
  - rating is a whole number from 1 to 5; comment is optional, at most 500 characters.

The user and role always come from the session set at login, never from the request.
"""
import uuid

import pymysql
from flask import Blueprint, current_app, jsonify, request, session

from app.access import RESIDENT, error
from app.tracking.scope import ROLES, visible_complaints
from db.connection import get_connection

feedback_bp = Blueprint("feedback", __name__, url_prefix="/api")

ELIGIBLE_STATUSES = ("resolved", "closed")
MAX_COMMENT = 500  # feedback.comments is VARCHAR(500)

COLUMNS = "feedback_id, complaint_id, resident_id, rating, comments, submitted_at"


@feedback_bp.errorhandler(pymysql.MySQLError)
def database_error(exc):
    current_app.logger.error("Database error in feedback module: %s", exc, exc_info=exc)
    return error(500, "DATABASE_ERROR", "A database error occurred. Please try again.")


def _serialize(row):
    submitted = row["submitted_at"]
    return {
        "feedback_id": row["feedback_id"],
        "complaint_id": row["complaint_id"],
        "resident_id": row["resident_id"],
        "rating": row["rating"],
        "comment": row["comments"],
        "created_at": submitted.isoformat() if submitted is not None else None,
    }


def parse_feedback(data):
    """Returns (rating, comment, error_message)."""
    if not isinstance(data, dict):
        return None, None, "Request body must be a JSON object."
    rating = data.get("rating")
    # bool is a subclass of int in Python, so True would otherwise pass as 1.
    if isinstance(rating, bool) or not isinstance(rating, int) or not 1 <= rating <= 5:
        return None, None, "'rating' must be a whole number from 1 to 5."
    comment = data.get("comment")
    if comment is not None:
        if not isinstance(comment, str):
            return None, None, "'comment' must be text."
        comment = comment.strip() or None
        if comment is not None and len(comment) > MAX_COMMENT:
            return None, None, f"'comment' must be at most {MAX_COMMENT} characters."
    return rating, comment, None


def _find_feedback(cur, complaint_id):
    cur.execute(f"SELECT {COLUMNS} FROM feedback WHERE complaint_id = %s", (complaint_id,))
    return cur.fetchone()


@feedback_bp.post("/complaints/<complaint_id>/feedback")
def submit_feedback(complaint_id):
    if "user_id" not in session:
        return error(401, "UNAUTHENTICATED", "Please log in.")
    if session.get("role") != RESIDENT:
        return error(403, "FORBIDDEN", "Only residents can give feedback on complaints.")
    user_id = session["user_id"]

    rating, comment, problem = parse_feedback(request.get_json(silent=True))
    if problem:
        return error(400, "VALIDATION_ERROR", problem)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Lock the complaint so two submissions for it cannot both pass the duplicate check.
            cur.execute(
                "SELECT resident_id, status FROM complaints WHERE complaint_id = %s FOR UPDATE",
                (complaint_id,),
            )
            complaint = cur.fetchone()
            if complaint is None:
                return error(404, "NOT_FOUND", "Complaint ID does not exist.")
            if complaint["resident_id"] != user_id:
                return error(403, "FORBIDDEN", "Only the resident who raised this complaint can give feedback.")
            if complaint["status"] not in ELIGIBLE_STATUSES:
                return error(409, "FEEDBACK_NOT_ALLOWED",
                             "Feedback can only be given once the complaint is resolved.")
            if _find_feedback(cur, complaint_id) is not None:
                return error(409, "DUPLICATE_FEEDBACK", "Feedback has already been submitted for this complaint.")

            cur.execute(
                "INSERT INTO feedback (feedback_id, complaint_id, resident_id, rating, comments) "
                "VALUES (%s, %s, %s, %s, %s)",
                (str(uuid.uuid4()), complaint_id, user_id, rating, comment),
            )
            row = _find_feedback(cur, complaint_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return jsonify({
        "status": "success",
        "message": "Thank you. Your feedback has been recorded.",
        "data": _serialize(row),
    }), 201


@feedback_bp.get("/complaints/<complaint_id>/feedback")
def view_feedback(complaint_id):
    if "user_id" not in session:
        return error(401, "UNAUTHENTICATED", "Please log in.")
    role = session.get("role")
    if role not in ROLES:
        return error(403, "FORBIDDEN", "You do not have access to this complaint.")

    # Same visibility rule as complaint tracking: owner, currently assigned staff, administrators.
    visible, params = visible_complaints(role, session["user_id"])
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT complaint_id FROM complaints WHERE complaint_id = %s", (complaint_id,))
            if cur.fetchone() is None:
                return error(404, "NOT_FOUND", "Complaint ID does not exist.")
            cur.execute(
                f"SELECT c.complaint_id FROM complaints c WHERE c.complaint_id = %s AND {visible}",
                [complaint_id, *params],
            )
            if cur.fetchone() is None:
                return error(403, "FORBIDDEN", "You do not have access to this complaint.")
            row = _find_feedback(cur, complaint_id)
    finally:
        conn.close()

    # data is null when the complaint has no feedback yet.
    return jsonify({"status": "success", "data": _serialize(row) if row else None}), 200
