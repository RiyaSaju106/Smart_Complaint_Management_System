"""PyMySQL data access for complaint search (FR-017, FR-018).

Every user-supplied value is passed as a bound parameter (SEC-003); only fixed SQL fragments are
joined together. Functions take an open cursor and never commit.
"""
from datetime import timedelta

from app.tracking.scope import visible_complaints
from app.tracking.search_schema import PAGE_SIZE

_FROM = (
    "FROM complaints c "
    "JOIN categories cat ON cat.category_id = c.category_id "
    "LEFT JOIN assignments a ON a.complaint_id = c.complaint_id AND a.is_current = TRUE "
    "LEFT JOIN departments d ON d.department_id = a.department_id "
    "LEFT JOIN users s ON s.user_id = a.staff_id "
)


def _like(text):
    """A LIKE pattern matching `text` anywhere, with LIKE wildcards in the text escaped."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _where(filters, role, user_id):
    scope_sql, params = visible_complaints(role, user_id)
    conditions = [scope_sql]

    if filters["q"]:
        # Exact Complaint ID, or a keyword in the title or description. The columns use a
        # case-insensitive collation, so LIKE ignores case.
        conditions.append("(c.complaint_id = %s OR c.title LIKE %s OR c.description LIKE %s)")
        params += [filters["q"], _like(filters["q"]), _like(filters["q"])]
    if filters["category_id"]:
        conditions.append("c.category_id = %s")
        params.append(filters["category_id"])
    if filters["status"]:
        conditions.append("c.status = %s")
        params.append(filters["status"])
    if filters["department_id"]:
        conditions.append("a.department_id = %s")  # current assignment only (joined above)
        params.append(filters["department_id"])
    if filters["from"]:
        conditions.append("c.created_at >= %s")
        params.append(filters["from"])
    if filters["to"]:
        conditions.append("c.created_at < %s")  # inclusive: before the start of the next day
        params.append(filters["to"] + timedelta(days=1))

    return " WHERE " + " AND ".join(conditions), params


def search(cur, filters, role, user_id):
    """(rows for the requested page, total number of matches), newest first."""
    where, params = _where(filters, role, user_id)

    cur.execute("SELECT COUNT(*) AS total " + _FROM + where, params)
    total = cur.fetchone()["total"]

    cur.execute(
        "SELECT c.complaint_id, c.title, c.status, c.location, c.created_at, "
        "cat.category_id, cat.name AS category_name, "
        "a.department_id, d.name AS department_name, a.staff_id, s.name AS staff_name "
        + _FROM + where
        + " ORDER BY c.created_at DESC, c.complaint_id DESC LIMIT %s OFFSET %s",
        params + [PAGE_SIZE, (filters["page"] - 1) * PAGE_SIZE],
    )
    return cur.fetchall(), total
