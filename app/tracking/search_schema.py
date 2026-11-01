"""Validation of the GET /api/complaints search and filter parameters (FR-017, FR-018).

Pure functions with no Flask or database code. parse_search returns (filters, error_message);
error_message is None when every parameter is valid. Unknown parameters are ignored.

Values are case-sensitive where the database is: status=Assigned is rejected, not converted.
"""
import uuid
from datetime import date

STATUSES = ("submitted", "assigned", "in_progress", "resolved", "closed")
MAX_Q = 100
PAGE_SIZE = 20


def _uuid(args, name):
    value = args.get(name)
    if value is None or value == "":
        return None, None
    try:
        uuid.UUID(value)
    except ValueError:
        return None, f"'{name}' must be a valid UUID."
    return value, None


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


def parse_search(args):
    """args: a mapping of query-string values (request.args).

    Returns ({"q", "category_id", "status", "department_id", "from", "to", "page"}, None)
    or (None, error message). Empty values count as not given.
    """
    q = (args.get("q") or "").strip()
    if len(q) > MAX_Q:
        return None, f"'q' must be at most {MAX_Q} characters."

    category_id, problem = _uuid(args, "category_id")
    if problem:
        return None, problem

    status = args.get("status") or None
    if status is not None and status not in STATUSES:
        return None, f"'status' must be one of: {', '.join(STATUSES)}."

    department_id, problem = _uuid(args, "department_id")
    if problem:
        return None, problem

    date_from, problem = _date(args, "from")
    if problem:
        return None, problem
    date_to, problem = _date(args, "to")
    if problem:
        return None, problem
    if date_from and date_to and date_from > date_to:
        return None, "'from' must not be after 'to'."

    raw_page = args.get("page")
    if raw_page is None or raw_page == "":
        page = 1
    elif raw_page.isdigit() and int(raw_page) >= 1:
        page = int(raw_page)
    else:
        return None, "'page' must be a whole number of 1 or more."

    return {
        "q": q or None,
        "category_id": category_id,
        "status": status,
        "department_id": department_id,
        "from": date_from,
        "to": date_to,
        "page": page,
    }, None
