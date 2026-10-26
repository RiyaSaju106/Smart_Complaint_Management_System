
"""Complaint registration API (SRS FR-005 to FR-008)."""

import uuid

import pymysql
from flask import Blueprint, current_app, jsonify, request, session

from app.access import RESIDENT, error, role_required
from db.connection import get_connection

complaints_bp = Blueprint("complaints", __name__, url_prefix="/api/complaints")


def validation_error(message, fields=None):
    response = {"error": {"code": "VALIDATION_ERROR", "message": message}}
    if fields:
        response["error"]["fields"] = fields
    return jsonify(response), 400


@complaints_bp.post("")
@role_required(RESIDENT)
def submit_complaint():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return validation_error("A JSON request body is required.")

    required_fields = ("title", "category_id", "description", "location")
    missing = [
        field for field in required_fields
        if not isinstance(data.get(field), str) or not data[field].strip()
    ]
    if missing:
        return validation_error(
            "Title, category, description, and location are required.",
            missing,
        )

    title = data["title"].strip()
    category_id = data["category_id"].strip()
    description = data["description"].strip()
    location = data["location"].strip()

    limits = {
        "title": 150,
        "category_id": 36,
        "description": 1000,
        "location": 200,
    }
    values = {
        "title": title,
        "category_id": category_id,
        "description": description,
        "location": location,
    }

    too_long = [
        field for field, limit in limits.items()
        if len(values[field]) > limit
    ]
    if too_long:
        return validation_error("One or more fields exceed the allowed length.", too_long)

    complaint_id = str(uuid.uuid4())
    resident_id = session["user_id"]
    conn = None

    try:
        conn = get_connection()
        with conn.cursor() as cur:
            # Ensure the session belongs to an active resident account.
            cur.execute(
                """
                SELECT user_id
                FROM users
                WHERE user_id = %s
                  AND role = %s
                  AND is_active = TRUE
                """,
                (resident_id, RESIDENT),
            )
            if cur.fetchone() is None:
                conn.rollback()
                session.clear()
                return error(401, "UNAUTHENTICATED", "Please log in.")

            # Only active categories may be selected for new complaints.
            cur.execute(
                """
                SELECT category_id
                FROM categories
                WHERE category_id = %s AND is_active = TRUE
                """,
                (category_id,),
            )
            if cur.fetchone() is None:
                conn.rollback()
                return validation_error("The selected category does not exist or is inactive.",
                                        ["category_id"])

            cur.execute(
                """
                INSERT INTO complaints
                    (complaint_id, resident_id, title, category_id,
                     description, location, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'submitted')
                """,
                (
                    complaint_id,
                    resident_id,
                    title,
                    category_id,
                    description,
                    location,
                ),
            )

            # Preserve the initial submitted state in the append-only history.
            cur.execute(
                """
                INSERT INTO status_history
                    (history_id, complaint_id, old_status, new_status, changed_by)
                VALUES (%s, %s, NULL, 'submitted', %s)
                """,
                (str(uuid.uuid4()), complaint_id, resident_id),
            )

        conn.commit()

    except pymysql.MySQLError:
        if conn is not None:
            conn.rollback()
        current_app.logger.exception("Complaint submission failed.")
        return error(
            500,
            "DATABASE_ERROR",
            "Unable to submit your complaint right now. Please try again.",
        )
    finally:
        if conn is not None:
            conn.close()

    return jsonify({
        "status": "success",
        "message": "Complaint submitted successfully.",
        "data": {
            "complaint_id": complaint_id,
            "status": "submitted",
        },
    }), 201
