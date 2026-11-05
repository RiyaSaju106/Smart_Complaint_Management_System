"""Browser pages for the Processing & Status module: the staff dashboard and complaint detail.

These routes only render HTML shells. All data is read and written through the existing /api/staff/...
endpoints in routes.py, which keep doing the real role check, the "currently assigned to you" check
and the transition rules. A page here never decides who may change a complaint; the API does.

Pages (no /api prefix, so this is a second blueprint; it is registered by process/__init__.py when
processing_bp is registered):
  GET /staff/complaints         dashboard: complaints currently assigned to the logged-in staff member
  GET /staff/complaints/<id>    one complaint: details, history, status and remark controls

Like the other browser pages, a visitor who is not signed in is redirected to /login, and a signed-in
user who is not maintenance staff is sent to their own home page.
"""
import json

from flask import Blueprint, redirect, render_template, session

from . import schema

MAINTENANCE_STAFF = "maintenance_staff"

# Templates and static files live inside this folder so the module stays self-contained.
pages_bp = Blueprint(
    "processing_pages",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/process-static",
)


def _staff_or_redirect():
    """None when the caller is signed-in maintenance staff, else the redirect to send."""
    if "user_id" not in session:
        return redirect("/login")
    if session.get("role") != MAINTENANCE_STAFF:
        return redirect("/home")
    return None


@pages_bp.get("/staff/complaints")
def staff_dashboard_page():
    denied = _staff_or_redirect()
    if denied:
        return denied
    return render_template(
        "staff_dashboard.html", name=session.get("name"), statuses=schema.STATUSES
    )


@pages_bp.get("/staff/complaints/<complaint_id>")
def staff_complaint_page(complaint_id):
    denied = _staff_or_redirect()
    if denied:
        return denied
    return render_template(
        "staff_complaint.html",
        name=session.get("name"),
        complaint_id=complaint_id,
        # One source of truth for which status buttons exist: the backend's own rules.
        transitions=json.dumps(schema.ALLOWED_TRANSITIONS),
        remarkable=json.dumps(schema.REMARKABLE_STATUSES),
        max_remarks=schema.MAX_REMARKS,
        max_details=schema.MAX_RESOLUTION_DETAILS,
    )
