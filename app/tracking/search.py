"""Complaint search and filters (FR-017, FR-018, #27): GET /api/complaints.

Any logged-in role may search, but only within the complaints that role may see (scope.py).
POST /api/complaints (submit) is the Complaint module's; the two share the path with different
methods.
"""
import pymysql
from flask import current_app, jsonify, request, session

from app.access import error
from app.tracking import search_queries, search_schema, tracking_bp
from app.tracking.scope import ROLES
from db.connection import get_connection


def _iso(value):
    return value.isoformat() if value is not None else None


def _item(row):
    assignment = None
    if row["department_id"] is not None:
        assignment = {
            "department": {"department_id": row["department_id"], "name": row["department_name"]},
            "staff": (
                {"user_id": row["staff_id"], "name": row["staff_name"]}
                if row["staff_id"] is not None else None
            ),
        }
    return {
        "complaint_id": row["complaint_id"],
        "title": row["title"],
        "category": {"category_id": row["category_id"], "name": row["category_name"]},
        "status": row["status"],
        "location": row["location"],
        "created_at": _iso(row["created_at"]),
        "current_assignment": assignment,
    }


@tracking_bp.get("/complaints")
def search_complaints():
    if not session.get("user_id"):
        return error(401, "UNAUTHENTICATED", "Please log in.")
    role = session.get("role")
    if role not in ROLES:
        return error(403, "FORBIDDEN", "You do not have access to complaints.")

    filters, problem = search_schema.parse_search(request.args)
    if problem:
        return error(400, "INVALID_FILTER", problem)

    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                rows, total = search_queries.search(cur, filters, role, session["user_id"])
        finally:
            conn.close()
    except pymysql.MySQLError as exc:
        current_app.logger.error("Database error searching complaints: %s", exc, exc_info=exc)
        return error(500, "DATABASE_ERROR", "A database error occurred. Please try again.")

    return jsonify({
        "items": [_item(r) for r in rows],
        "page": filters["page"],
        "page_size": search_schema.PAGE_SIZE,
        "total": total,
    }), 200
