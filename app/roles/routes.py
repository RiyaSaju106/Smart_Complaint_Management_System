from flask import Blueprint, jsonify, redirect, render_template, session, url_for

from app.access import ADMINISTRATOR, RESIDENT, error, role_required

roles_bp = Blueprint("roles", __name__)


@roles_bp.route("/home")
def home():
    """Send a logged-in user to the landing page for their role."""
    role = session.get("role")
    if "user_id" not in session:
        return error(401, "UNAUTHENTICATED", "Please log in.")
    if role == ADMINISTRATOR:
        return redirect(url_for("roles.admin_home"))
    if role == RESIDENT:
        return redirect(url_for("roles.resident_home"))
    return error(403, "FORBIDDEN", "Unknown role.")


@roles_bp.route("/resident")
@role_required(RESIDENT)
def resident_home():
    return render_template("resident_home.html", name=session.get("name"))


@roles_bp.route("/admin")
@role_required(ADMINISTRATOR)
def admin_home():
    return render_template("admin_home.html", name=session.get("name"))


@roles_bp.route("/api/admin/dashboard")
@role_required(ADMINISTRATOR)
def admin_dashboard():
    return jsonify({
        "user": {"id": session["user_id"], "name": session.get("name"), "role": ADMINISTRATOR},
        "message": "Administrator access granted",
    })
