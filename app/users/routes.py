
from flask import Blueprint, jsonify

users_bp = Blueprint("users", __name__, url_prefix="/api/users")


@users_bp.route("/me", methods=["GET"])
def get_profile():
    return jsonify({
        "message": "Profile endpoint ready for implementation"
    }), 501


@users_bp.route("/me", methods=["PATCH"])
def update_profile():
    return jsonify({
        "message": "Profile update endpoint ready for implementation"
    }), 501
