"""Browser pages for SCMS (issue #54): login, register and the complaint form.

These routes only render HTML. All data goes through the existing /api/... endpoints, which
keep doing the real validation and role checks. A page here redirects to /login when nobody is
signed in (the JSON 401 used by the API is not useful in a browser).
"""
from flask import Blueprint, redirect, render_template, session, url_for

from app.access import RESIDENT

ui_bp = Blueprint("ui", __name__)


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