
import pymysql
from flask import Blueprint, jsonify, request, session

from db.connection import get_connection

users_bp = Blueprint("users", __name__, url_prefix="/api/users")

EDITABLE_FIELDS = {"name", "contact_number", "unit_address"}


def error_response(status, code, message, fields=None):
    error = {"code": code, "message": message}
    if fields is not None:
        error["fields"] = fields
    return jsonify({"error": error}), status


def require_login():
    if not session.get("user_id"):
        return error_response(401, "UNAUTHENTICATED", "Please log in.")
    return None


@users_bp.route("/me", methods=["GET"])
def get_profile():
    auth_error = require_login()
    if auth_error:
        return auth_error

    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id, name, email, contact_number, unit_address,
                       role, created_at, updated_at
                FROM users
                WHERE user_id = %s AND is_active = TRUE
                """,
                (session["user_id"],),
            )
            user = cur.fetchone()
    except pymysql.MySQLError:
        return error_response(
            500, "DATABASE_ERROR", "Unable to retrieve your profile right now."
        )
    finally:
        if conn is not None:
            conn.close()

    if not user:
        session.clear()
        return error_response(401, "UNAUTHENTICATED", "Please log in.")

    return jsonify({"user": user}), 200


@users_bp.route("/me", methods=["PATCH"])
def update_profile():
    auth_error = require_login()
    if auth_error:
        return auth_error

    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not data:
        return error_response(
            400, "VALIDATION_ERROR", "Please provide profile fields to update."
        )

    unknown_fields = sorted(set(data) - EDITABLE_FIELDS)
    if unknown_fields:
        return error_response(
            400,
            "VALIDATION_ERROR",
            "Only name, contact_number, and unit_address can be updated.",
            unknown_fields,
        )

    limits = {
        "name": 100,
        "contact_number": 15,
        "unit_address": 150,
    }

    for field, value in data.items():
        if not isinstance(value, str) or not value.strip():
            return error_response(
                400,
                "VALIDATION_ERROR",
                f"{field} must be a non-empty string.",
                [field],
            )
        if len(value.strip()) > limits[field]:
            return error_response(
                400,
                "VALIDATION_ERROR",
                f"{field} exceeds the maximum length.",
                [field],
            )

    updates = {field: value.strip() for field, value in data.items()}
    assignments = ", ".join(f"{field} = %s" for field in updates)
    values = list(updates.values()) + [session["user_id"]]

    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE users
                SET {assignments}
                WHERE user_id = %s AND is_active = TRUE
                """,
                values,
            )
            if cur.rowcount == 0:
                cur.execute(
                    "SELECT user_id FROM users WHERE user_id = %s AND is_active = TRUE",
                    (session["user_id"],),
                )
                if cur.fetchone() is None:
                    conn.rollback()
                    session.clear()
                    return error_response(
                        401, "UNAUTHENTICATED", "Please log in."
                    )
        conn.commit()
    except pymysql.MySQLError:
        if conn is not None:
            conn.rollback()
        return error_response(
            500, "DATABASE_ERROR", "Unable to update your profile right now."
        )
    finally:
        if conn is not None:
            conn.close()

    return jsonify({"message": "Profile updated successfully."}), 200
