"""Admin/Reporting (FR-024, FR-025, #34): dashboard counts and basic reports. HTTP layer.

Administrators only. Read-only: every figure is counted live from MySQL, so it always matches the
database. Report contents follow SRS Appendix B (total, by status, by category, by period, pending
and unresolved, staff/department workload).

  routes.py   this file: role check, validation, response shape
  schema.py   query-parameter validation
  queries.py  PyMySQL SQL
"""
import pymysql
from flask import Blueprint, current_app, jsonify, request

from app.access import ADMINISTRATOR, error, role_required
from db.connection import get_connection

from . import queries, schema

reports_bp = Blueprint("reports", __name__, url_prefix="/api/admin/reports")


@reports_bp.errorhandler(pymysql.MySQLError)
def database_error(exc):
    """Database failures become JSON in the project's error format; details go to the log only."""
    current_app.logger.error("Database error in reports module: %s", exc, exc_info=exc)
    return error(500, "DATABASE_ERROR", "A database error occurred. Please try again.")


def _iso(value):
    return value.isoformat() if value is not None else None


def _period_json(period):
    return {"from": _iso(period["from"]), "to": _iso(period["to"])}


def _share(count, total):
    """Percentage of total, one decimal place; 0 when there is nothing to share."""
    return round(100.0 * count / total, 1) if total else 0.0


def _with_shares(rows, total):
    for row in rows:
        row["share"] = _share(row["count"], total)
    return rows


@reports_bp.get("/summary")
@role_required(ADMINISTRATOR)
def summary():
    """Dashboard figures (FR-024)."""
    period, problem = schema.parse_range(request.args)
    if problem:
        return error(400, "INVALID_FILTER", problem)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            counts = queries.count_by_status(cur, period)
            unassigned = queries.count_unassigned_open(cur, period)
            feedback = queries.feedback_summary(cur, period)
    finally:
        conn.close()

    by_status = {status: int(counts.get(status, 0)) for status in schema.STATUSES}
    return jsonify({
        "period": _period_json(period),
        "total": sum(by_status.values()),
        "by_status": by_status,
        "pending": sum(by_status[s] for s in schema.OPEN_STATUSES),
        "unassigned": int(unassigned),
        "feedback": {
            "count": int(feedback["count"]),
            "average_rating": round(feedback["average"], 2) if feedback["average"] is not None else None,
        },
    }), 200


def _status_report(cur, period):
    counts = queries.count_by_status(cur, period)
    rows = [{"key": s, "label": schema.STATUS_LABELS[s], "count": int(counts.get(s, 0))}
            for s in schema.STATUSES]
    total = sum(r["count"] for r in rows)
    return _with_shares(rows, total), total


def _category_report(cur, period):
    rows = [{"category_id": r["category_id"], "label": r["name"], "is_active": bool(r["is_active"]),
             "count": int(r["n"])} for r in queries.by_category(cur, period)]
    total = sum(r["count"] for r in rows)
    return _with_shares(rows, total), total


def _department_report(cur, period):
    departments, unassigned = queries.by_department(cur, period)
    rows = [{"department_id": r["department_id"], "label": r["name"], "count": int(r["n"]),
             "open": int(r["open_n"])} for r in departments]
    rows.append({"department_id": None, "label": "Not assigned", "count": int(unassigned["n"]),
                 "open": int(unassigned["open_n"])})
    total = sum(r["count"] for r in rows)
    return _with_shares(rows, total), total


def _period_report(cur, period, group):
    rows = [{"period": r["period"], "count": int(r["n"])} for r in queries.by_period(cur, period, group)]
    total = sum(r["count"] for r in rows)
    return _with_shares(rows, total), total


def _pending_report(cur, period):
    found, total = queries.pending(cur, period)
    rows = [{
        "complaint_id": r["complaint_id"], "title": r["title"], "status": r["status"],
        "category": r["category"], "department": r["department"], "staff": r["staff"],
        "created_at": _iso(r["created_at"]), "age_days": int(r["age_days"]),
    } for r in found]
    return rows, int(total)


def _workload_report(cur, period):
    rows = []
    for r in queries.workload(cur, period):
        assigned, in_progress = int(r["assigned_n"]), int(r["in_progress_n"])
        rows.append({
            "staff": {"user_id": r["user_id"], "name": r["name"], "is_active": bool(r["is_active"])},
            "department": ({"department_id": r["department_id"], "name": r["department"]}
                           if r["department_id"] else None),
            "assigned": assigned, "in_progress": in_progress, "open": assigned + in_progress,
            "resolved": int(r["resolved_n"]), "closed": int(r["closed_n"]),
        })
    return rows, sum(r["open"] for r in rows)


@reports_bp.get("")
@role_required(ADMINISTRATOR)
def report():
    """Basic reports (FR-025): ?type=status|category|department|period|pending|workload."""
    params, problem = schema.parse_report(request.args)
    if problem:
        return error(400, "INVALID_FILTER", problem)
    kind = params["type"]

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if kind == "status":
                rows, total = _status_report(cur, params)
            elif kind == "category":
                rows, total = _category_report(cur, params)
            elif kind == "department":
                rows, total = _department_report(cur, params)
            elif kind == "period":
                rows, total = _period_report(cur, params, params["group"])
            elif kind == "pending":
                rows, total = _pending_report(cur, params)
            else:
                rows, total = _workload_report(cur, params)
    finally:
        conn.close()

    body = {"type": kind, "period": _period_json(params), "total": total, "rows": rows}
    if kind == "period":
        body["group"] = params["group"]
    if kind == "pending":
        body["limit"] = schema.PENDING_LIMIT
    return jsonify(body), 200
