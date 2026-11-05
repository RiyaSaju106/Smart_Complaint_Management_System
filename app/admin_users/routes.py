"""Administrator user management (FR-023, issue #33). HTTP layer.

    GET   /api/admin/users                    list resident and staff accounts (filters, paging)
    POST  /api/admin/users                    create a resident or maintenance staff account
    GET   /api/admin/users/<id>               one account
    PATCH /api/admin/users/<id>               edit name, contact, address, staff department
    POST  /api/admin/users/<id>/deactivate    block login for the account
    POST  /api/admin/users/<id>/activate      allow login again

Rules:
  - Administrators only. The role comes from the signed session, never from the request, so
    residents and maintenance staff get 403 and anonymous callers get 401.
  - Only resident and maintenance staff accounts are managed. Administrator accounts are never
    created, edited, deactivated or shown here (a missing or administrator id both answer 404/403
    as documented below), so an administrator cannot lock out or demote another one.
  - Roles and emails are fixed once an account exists.
  - A staff member who still has assigned or in-progress complaints cannot be deactivated: the
    complaints would be stuck. Reassign them first (409 STAFF_HAS_OPEN_COMPLAINTS).
  - Passwords are stored hashed and are never returned.

    queries.py  PyMySQL SQL        schema.py  request validation
"""
import pymysql
from flask import Blueprint, current_app, jsonify, request

from app.access import ADMINISTRATOR, error, role_required
from db.connection import get_connection
from db.passwords import hash_password

from . import queries, schema

admin_users_bp = Blueprint("admin_users", __name__, url_prefix="/api/admin/users")

DUPLICATE_ENTRY = 1062


@admin_users_bp.errorhandler(pymysql.MySQLError)
def database_error(exc):
    """Database failures become JSON in the project's error format; details go to the log only."""
    current_app.logger.error("Database error in admin_users module: %s", exc, exc_info=exc)
    return error(500, "DATABASE_ERROR", "A database error occurred. Please try again.")


def _iso(value):
    return value.isoformat() if value is not None else None


def _user_json(row):
    return {
        "user_id": row["user_id"],
        "name": row["name"],
        "email": row["email"],
        "role": row["role"],
        "contact_number": row["contact_number"],
        "unit_address": row["unit_address"],
        "department_id": row["department_id"],
        "department": row["department"],
        "is_active": bool(row["is_active"]),
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
    }


def _managed_user(cur, user_id):
    """(row, None) for a resident/staff account; (None, error_response) otherwise."""
    row = queries.get_user(cur, user_id) if schema.is_uuid(user_id) else None
    if row is None:
        return None, error(404, "NOT_FOUND", "User not found.")
    if row["role"] not in schema.MANAGED_ROLES:
        return None, error(403, "FORBIDDEN", "Administrator accounts cannot be managed here.")
    return row, None


@admin_users_bp.get("")
@role_required(ADMINISTRATOR)
def list_users():
    filters, problem = schema.parse_list_filters(request.args)
    if problem:
        return error(400, "INVALID_FILTER", problem)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            rows, total = queries.list_users(cur, filters)
    finally:
        conn.close()
    return jsonify({
        "items": [_user_json(r) for r in rows],
        "page": filters["page"],
        "page_size": filters["page_size"],
        "total": total,
    })


@admin_users_bp.post("")
@role_required(ADMINISTRATOR)
def create_user():
    clean, problem = schema.parse_create(request.get_json(silent=True))
    if problem:
        return error(400, "VALIDATION_ERROR", problem)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if clean["department_id"] and not queries.department_exists(cur, clean["department_id"]):
                return error(400, "VALIDATION_ERROR", "'department_id' does not exist.")
            try:
                user_id = queries.insert_user(cur, clean, hash_password(clean["password"]))
            except pymysql.err.IntegrityError as exc:
                conn.rollback()
                if exc.args and exc.args[0] == DUPLICATE_ENTRY:
                    return error(409, "EMAIL_ALREADY_EXISTS",
                                 "An account with this email already exists.")
                raise
            row = queries.get_user(cur, user_id)
        conn.commit()
    finally:
        conn.close()
    return jsonify(_user_json(row)), 201


@admin_users_bp.get("/<user_id>")
@role_required(ADMINISTRATOR)
def get_user(user_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            row, problem = _managed_user(cur, user_id)
    finally:
        conn.close()
    return problem or jsonify(_user_json(row))


@admin_users_bp.patch("/<user_id>")
@role_required(ADMINISTRATOR)
def update_user(user_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            row, problem = _managed_user(cur, user_id)
            if problem:
                return problem
            changes, problem = schema.parse_update(request.get_json(silent=True), row["role"])
            if problem:
                return error(400, "VALIDATION_ERROR", problem)
            if "department_id" in changes and not queries.department_exists(cur, changes["department_id"]):
                return error(400, "VALIDATION_ERROR", "'department_id' does not exist.")
            queries.update_user(cur, user_id, changes)
            row = queries.get_user(cur, user_id)
        conn.commit()
    finally:
        conn.close()
    return jsonify(_user_json(row))


def _set_active(user_id, active):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            row, problem = _managed_user(cur, user_id)
            if problem:
                return problem
            if bool(row["is_active"]) != active:  # already in the requested state: nothing to do
                if not active and row["role"] == "maintenance_staff":
                    open_count = queries.open_complaint_count(cur, user_id)
                    if open_count:
                        return error(
                            409, "STAFF_HAS_OPEN_COMPLAINTS",
                            f"This staff member still has {open_count} assigned or in-progress "
                            "complaint(s). Reassign them before deactivating the account.",
                        )
                queries.set_active(cur, user_id, active)
                row = queries.get_user(cur, user_id)
        conn.commit()
    finally:
        conn.close()
    return jsonify(_user_json(row))


@admin_users_bp.post("/<user_id>/deactivate")
@role_required(ADMINISTRATOR)
def deactivate_user(user_id):
    return _set_active(user_id, False)


@admin_users_bp.post("/<user_id>/activate")
@role_required(ADMINISTRATOR)
def activate_user(user_id):
    return _set_active(user_id, True)