"""Category and Department management (FR-009, FR-010): HTTP layer.

Any logged-in user lists active categories; administrators create, edit, deactivate and delete
them, and list departments and each department's staff.

How the module is split (same as process/):
  routes.py   this file: login and role checks, order of checks, transactions, responses
  schema.py   request validation
  queries.py  PyMySQL SQL, one small function per query; reused by other modules
"""
import uuid

import pymysql
from flask import Blueprint, current_app, jsonify, request, session

from app.access import ADMINISTRATOR, error, role_required
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
