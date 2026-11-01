"""Browser pages for SCMS: login, register and the complaint form (issue #54), category and
department management for administrators (issue #55), and complaint assignment for
administrators (issue #56), and the notification list for every role (issue #58).

These routes only render HTML. All data goes through the existing /api/...endpoints, which
keep doing the real validation and role checks. A page here redirects to /login when nobody is
signed in (the JSON 401 used by the API is not useful in a browser).
"""
from flask import Blueprint, redirect, render_template, session, url_for

from app.access import ADMINISTRATOR, MAINTENANCE_STAFF, RESIDENT

ui_bp = Blueprint("ui", __name__)

# Header colour and badge for each role, as on the role landing pages.
ROLE_HEADERS = {
    RESIDENT: ("resident", "Resident"),
    MAINTENANCE_STAFF: ("staff", "Maintenance Staff"),
    ADMINISTRATOR: ("admin", "Administrator"),
}


@ui_bp.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("roles.home"))
    return redirect(url_for("ui.login_page"))


@ui_bp.route("/login")
def login_page():
    if "user_id" in session:
        return redirect(url_for("roles.home"))
    return render_template("login.html")


@ui_bp.route("/register")
def register_page():
    if "user_id" in session:
        return redirect(url_for("roles.home"))
    return render_template("register.html")


@ui_bp.route("/complaints/new")
def new_complaint_page():
    if "user_id" not in session:
        return redirect(url_for("ui.login_page"))
    if session.get("role") != RESIDENT:
        # Staff and administrators do not submit complaints; send them to their own page.
        return redirect(url_for("roles.home"))
    return render_template("complaint_new.html", name=session.get("name"))


@ui_bp.route("/admin/categories")
def admin_categories_page():
    if "user_id" not in session:
        return redirect(url_for("ui.login_page"))
    if session.get("role") != ADMINISTRATOR:
        return redirect(url_for("roles.home"))
    return render_template("admin_categories.html", name=session.get("name"))


@ui_bp.route("/admin/assignments")
def admin_assignments_page():
    if "user_id" not in session:
        return redirect(url_for("ui.login_page"))
    if session.get("role") != ADMINISTRATOR:
        return redirect(url_for("roles.home"))
    return render_template("admin_assignments.html", name=session.get("name"))


@ui_bp.route("/notifications")
def notifications_page():
    if "user_id" not in session:
        return redirect(url_for("ui.login_page"))
    header = ROLE_HEADERS.get(session.get("role"))
    if header is None:
        return redirect(url_for("roles.home"))
    return render_template(
        "notifications.html", header_class=header[0], role_label=header[1], name=session.get("name")
    )
