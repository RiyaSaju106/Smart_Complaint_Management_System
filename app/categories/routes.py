"""Category/Assignment module (FR-009, FR-010, FR-011): HTTP layer.

Any logged-in user lists active categories; administrators create, edit, deactivate and delete
them, list departments and each department's staff, and assign or reassign complaints.

How the module is split (same as process/):
  routes.py   this file: login and role checks, order of checks, transactions, responses
  schema.py   request validation
  queries.py  PyMySQL SQL, one small function per query; reused by other modules
"""
import uuid

import pymysql
from flask import Blueprint, current_app, jsonify, request, session

from app.access import ADMINISTRATOR, error, role_required
from app.tracking.service import record_status_change
from db.connection import get_connection

from . import queries, schema

categories_bp = Blueprint("categories", __name__, url_prefix="/api")

# MySQL error numbers
DUPLICATE_ENTRY = 1062
ROW_IS_REFERENCED = 1451


@categories_bp.errorhandler(pymysql.MySQLError)
def database_error(exc):
    """Any database failure becomes JSON in the project's error format, never an HTML 500 page.
    The details go to the log only; the client gets a generic message."""
    current_app.logger.error("Database error in categories module: %s", exc, exc_info=exc)
    return error(500, "DATABASE_ERROR", "A database error occurred. Please try again.")


def _validation_error(message):
    return error(400, "VALIDATION_ERROR", message)


def _duplicate_name():
    return error(409, "DUPLICATE_CATEGORY", "A category with this name already exists.")


def _category_not_found():
    return error(404, "NOT_FOUND", "Category does not exist.")


def _iso(value):
    return value.isoformat() if value is not None else None


def _category_json(row):
    return {
        "category_id": row["category_id"],
        "name": row["name"],
        "description": row["description"],
        "is_active": bool(row["is_active"]),
    }


@categories_bp.get("/categories")
def list_categories():
    # Open to every role, so role_required (one role) does not fit; the login check is inline.
    if "user_id" not in session:
        return error(401, "UNAUTHENTICATED", "Please log in.")

    include_inactive, problem = schema.parse_include_inactive(request.args.get("include_inactive"))
    if problem:
        return _validation_error(problem)
    # Only administrators see inactive categories; for anyone else the flag is ignored.
    include_inactive = include_inactive and session.get("role") == ADMINISTRATOR

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            rows = queries.list_categories(cur, include_inactive)
    finally:
        conn.close()

    return jsonify({"items": [_category_json(r) for r in rows]}), 200


@categories_bp.post("/categories")
@role_required(ADMINISTRATOR)
def create_category():
    parsed, problem = schema.parse_new_category(request.get_json(silent=True))
    if problem:
        return _validation_error(problem)

    category_id = str(uuid.uuid4())
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if queries.name_taken(cur, parsed["name"]):
                return _duplicate_name()
            queries.insert_category(cur, category_id, parsed["name"], parsed["description"])
            row = queries.get_category(cur, category_id)
        conn.commit()
    except pymysql.err.IntegrityError as exc:
        conn.rollback()
        if exc.args[0] == DUPLICATE_ENTRY:  # another request created the same name meanwhile
            return _duplicate_name()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return jsonify(_category_json(row)), 201


@categories_bp.put("/categories/<category_id>")
@role_required(ADMINISTRATOR)
def update_category(category_id):
    parsed, problem = schema.parse_category_update(request.get_json(silent=True))
    if problem:
        return _validation_error(problem)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if queries.get_category(cur, category_id, lock=True) is None:
                return _category_not_found()
            if queries.name_taken(cur, parsed["name"], exclude_id=category_id):
                return _duplicate_name()
            queries.update_category(
                cur, category_id, parsed["name"], parsed["description"], parsed["is_active"]
            )
            row = queries.get_category(cur, category_id)
        conn.commit()
    except pymysql.err.IntegrityError as exc:
        conn.rollback()
        if exc.args[0] == DUPLICATE_ENTRY:
            return _duplicate_name()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return jsonify(_category_json(row)), 200


@categories_bp.delete("/categories/<category_id>")
@role_required(ADMINISTRATOR)
def delete_category(category_id):
    in_use = error(
        409,
        "CATEGORY_IN_USE",
        "Complaints use this category, so it cannot be deleted. Deactivate it instead.",
    )
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if queries.get_category(cur, category_id, lock=True) is None:
                return _category_not_found()
            if queries.category_in_use(cur, category_id):
                return in_use
            queries.delete_category(cur, category_id)
        conn.commit()
    except pymysql.err.IntegrityError as exc:
        conn.rollback()
        if exc.args[0] == ROW_IS_REFERENCED:  # a complaint was filed with it meanwhile
            return in_use
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return "", 204


@categories_bp.get("/departments")
@role_required(ADMINISTRATOR)
def list_departments():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            rows = queries.list_departments(cur)
    finally:
        conn.close()

    return jsonify({"items": rows}), 200


@categories_bp.get("/departments/<department_id>/staff")
@role_required(ADMINISTRATOR)
def list_department_staff(department_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if not queries.department_exists(cur, department_id):
                return error(404, "NOT_FOUND", "Department does not exist.")
            rows = queries.list_department_staff(cur, department_id)
    finally:
        conn.close()

    return jsonify({"items": rows}), 200


# A complaint in one of these states can no longer be assigned (SRS business rules).
UNASSIGNABLE_STATUSES = ("resolved", "closed")


@categories_bp.post("/complaints/<complaint_id>/assignment")
@role_required(ADMINISTRATOR)
def assign_complaint(complaint_id):
    """Assign or reassign a complaint (FR-011).

    Order of checks: login and role (401, 403) -> body (400) -> complaint exists (404) ->
    complaint still open (409) -> department and staff valid (400). Everything is written in one
    transaction: end the current assignment, insert the new one, and on the first assignment move
    the complaint submitted -> assigned with a status_history row. Reassignment keeps the status.
    """
    parsed, problem = schema.parse_assignment(request.get_json(silent=True))
    if problem:
        return _validation_error(problem)
    department_id, staff_id = parsed["department_id"], parsed["staff_id"]
    admin_id = session["user_id"]

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            complaint = queries.lock_complaint(cur, complaint_id)
            if complaint is None:
                return error(404, "NOT_FOUND", "Complaint ID does not exist.")
            status = complaint["status"]
            if status in UNASSIGNABLE_STATUSES:
                return error(
                    409, "INVALID_STATE", f"A {status} complaint cannot be assigned."
                )
            if not queries.department_exists(cur, department_id):
                return _validation_error("Department does not exist.")
            if staff_id is not None and (
                queries.get_department_staff_member(cur, department_id, staff_id) is None
            ):
                return _validation_error(
                    "The staff member must be active maintenance staff in that department."
                )

            queries.end_current_assignment(cur, complaint_id)
            assignment_id = str(uuid.uuid4())
            queries.insert_assignment(
                cur, assignment_id, complaint_id, admin_id, department_id, staff_id
            )
            if status == "submitted":
                queries.set_complaint_status(cur, complaint_id, "assigned")
                record_status_change(cur, complaint_id, "submitted", "assigned", admin_id)
                status = "assigned"
            assigned_at = queries.get_assigned_at(cur, assignment_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    # TODO(#28): once #42 is merged, notify after commit (notify() never raises):
    #   notify(COMPLAINT_ASSIGNED, complaint_id, [complaint["resident_id"], staff_id])

    return jsonify({
        "complaint_id": complaint_id,
        "status": status,
        "department_id": department_id,
        "staff_id": staff_id,
        "assigned_at": _iso(assigned_at),
    }), 200
