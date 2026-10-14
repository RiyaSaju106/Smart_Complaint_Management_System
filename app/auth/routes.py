
from flask import Blueprint, jsonify, request

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}

    required_fields = ["name", "email", "password"]

    missing_fields = [
        field for field in required_fields
        if not data.get(field)
    ]

    if missing_fields:
        return jsonify({
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Please check the submitted fields.",
                "fields": missing_fields
            }
        }), 400

    return jsonify({
        "message": "Registration endpoint is ready for implementation"
    }), 501


@auth_bp.route("/login", methods=["POST"])
def login():
    return jsonify({
        "message": "Login endpoint is ready for implementation"
    }), 501


@auth_bp.route("/logout", methods=["POST"])
def logout():
    return jsonify({
        "message": "Logout endpoint is ready for implementation"
    }), 501
