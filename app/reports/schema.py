"""Validation of the report query parameters (FR-024, FR-025).

Pure functions with no Flask or database code. Each parser returns (value, error_message);
error_message is None when the input is valid. Empty values count as not given.
"""
from datetime import date

STATUSES = ("submitted", "assigned", "in_progress", "resolved", "closed")
OPEN_STATUSES = ("submitted", "assigned", "in_progress")  # pending and unresolved
STATUS_LABELS = {
    "submitted": "Submitted", "assigned": "Assigned", "in_progress": "In progress",
    "resolved": "Resolved", "closed": "Closed",
}
REPORT_TYPES = ("status", "category", "department", "period", "pending", "workload")
PERIOD_GROUPS = ("day", "month")
PENDING_LIMIT = 100


def _date(args, name):
    value = args.get(name)
    if value is None or value == "":
        return None, None
    try:
        if len(value) != 10:
            raise ValueError
        return date.fromisoformat(value), None
    except ValueError:
        return None, f"'{name}' must be a date in YYYY-MM-DD format."


def parse_range(args):
    """?from=&to= on every report: optional complaint created_at range, inclusive."""
    date_from, problem = _date(args, "from")
    if problem:
        return None, problem
    date_to, problem = _date(args, "to")
    if problem:
        return None, problem
    if date_from and date_to and date_from > date_to:
        return None, "'from' must not be after 'to'."
    return {"from": date_from, "to": date_to}, None


def parse_report(args):
    """GET /api/admin/reports: type (required), from, to, group (period report only)."""
    report_type = args.get("type") or None
    if report_type not in REPORT_TYPES:
        return None, f"'type' is required and must be one of: {', '.join(REPORT_TYPES)}."
    period, problem = parse_range(args)
    if problem:
        return None, problem
    group = args.get("group") or "month"
    if report_type == "period" and group not in PERIOD_GROUPS:
        return None, f"'group' must be one of: {', '.join(PERIOD_GROUPS)}."
    return {"type": report_type, "group": group, **period}, None
