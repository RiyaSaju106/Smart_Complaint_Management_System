
import re
import uuid

import pymysql
from flask import Blueprint, jsonify, request

from db.connection import get_connection
from db.passwords import hash_password, verify_password

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def error_response(status, code, message, fields=None):
    error = {"code": code, "message": message}
    if fields is not None:
        error["fields"] = fields
    return jsonify({"error": error}), status


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return error_response(
            400, "VALIDATION_ERROR", "Please provide a JSON object."
        )

    required_fields = ["name", "email", "password"]
    missing_fields = [
        field for field in required_fields
        if not isinstance(data.get(field), str) or not data[field].strip()
    ]

    email = data.get("email", "")
    email = email.strip().lower() if isinstance(email, str) else ""

    name = data.get("name", "")
    name = name.strip() if isinstance(name, str) else ""

    password = data.get("password", "")

    if data.get("email") and not isinstance(data["email"], str):
        missing_fields.append("email")

    if data.get("password") and not isinstance(password, str):
        missing_fields.append("password")

    contact_number = data.get("contact_number")
    unit_address = data.get("unit_address")

    if not isinstance(contact_number, str) or not contact_number.strip():
        missing_fields.append("contact_number")

    if not isinstance(unit_address, str) or not unit_address.strip():
        missing_fields.append("unit_address")

    if missing_fields:
        return error_response(
            400,
            "VALIDATION_ERROR",
            "Please check the submitted fields.",
            list(dict.fromkeys(missing_fields)),
        )

    if len(name) > 100:
        return error_response(
            400, "VALIDATION_ERROR", "Name must be at most 100 characters.",
            ["name"],
        )

    if len(email) > 100 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return error_response(
            400, "VALIDATION_ERROR", "Please provide a valid email address.",
            ["email"],
        )

    if len(password) < 8:
        return error_response(
            400, "VALIDATION_ERROR", "Password must be at least 8 characters.",
            ["password"],
        )

    if len(contact_number.strip()) > 15:
        return error_response(
            400, "VALIDATION_ERROR", "Contact number must be at most 15 characters.",
            ["contact_number"],
        )

    if len(unit_address.strip()) > 150:
        return error_response(
            400, "VALIDATION_ERROR", "Unit address must be at most 150 characters.",
            ["unit_address"],
        )

    user_id = str(uuid.uuid4())

    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users
                    (user_id, name, email, password_hash,
                     contact_number, unit_address, role)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    name,
                    email,
                    hash_password(password),
                    contact_number.strip(),
                    unit_address.strip(),
                    "resident",
                ),
            )
        conn.commit()

    except pymysql.err.IntegrityError:
        if conn is not None:
            conn.rollback()
        return error_response(
            409, "EMAIL_ALREADY_EXISTS", "An account with this email already exists."
        )
    except pymysql.MySQLError:
        if conn is not None:
            conn.rollback()
        return error_response(
            500, "DATABASE_ERROR", "Unable to complete registration right now."
        )
    finally:
        if conn is not None:
            conn.close()

    return jsonify({
        "message": "Registration successful.",
        "user": {
            "user_id": user_id,
            "name": name,
            "email": email,
            "role": "resident",
        },
    }), 201



@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return error_response(
            400, "VALIDATION_ERROR", "Please provide a JSON object."
        )

    email = data.get("email")
    password = data.get("password")

    missing_fields = []
    if not isinstance(email, str) or not email.strip():
        missing_fields.append("email")
    if not isinstance(password, str) or not password:
        missing_fields.append("password")

    if missing_fields:
        return error_response(
            400,
            "VALIDATION_ERROR",
            "Please check the submitted fields.",
            missing_fields,
        )

    email = email.strip().lower()

    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id, name, email, password_hash, role, is_active
                FROM users
                WHERE email = %s
                """,
                (email,),
            )
            user = cur.fetchone()
    except pymysql.MySQLError:
        return error_response(
            500, "DATABASE_ERROR", "Unable to complete login right now."
        )
    finally:
        if conn is not None:
            conn.close()

    # Use the same response for unknown email and incorrect password.
    if (
        not user
        or not user["is_active"]
        or not verify_password(user["password_hash"], password)
    ):
        return error_response(
            401, "INVALID_CREDENTIALS", "Invalid email or password."
        )

    # Prevent a previous session from carrying over into this login.
    from flask import session
    session.clear()
    session["user_id"] = user["user_id"]
    session["name"] = user["name"]
    session["role"] = user["role"]

    return jsonify({
        "message": "Login successful.",
        "user": {
            "user_id": user["user_id"],
            "name": user["name"],
            "email": user["email"],
            "role": user["role"],
        },
    }), 200


@auth_bp.route("/logout", methods=["POST"])
def logout():
    from flask import session
    session.clear()

    return jsonify({"message": "Logout successful."}), 200
