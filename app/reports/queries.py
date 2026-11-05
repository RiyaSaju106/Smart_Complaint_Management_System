"""PyMySQL data access for the dashboard and reports. Read-only: nothing here writes.

Every user value is a bound parameter (SEC-003). The optional date range always applies to the
complaint's created_at, inclusive of both days. Department and staff figures use the complaint's
*current* assignment only, never earlier ones.
"""
from datetime import timedelta

from app.reports.schema import OPEN_STATUSES, PENDING_LIMIT

_OPEN = "('submitted', 'assigned', 'in_progress')"
assert OPEN_STATUSES == ("submitted", "assigned", "in_progress")  # keep _OPEN in step


def _range(period, alias="c"):
    """(sql, params): AND-conditions limiting `alias`.created_at to the requested range."""
    sql, params = "", []
    if period.get("from"):
        sql += f" AND {alias}.created_at >= %s"
        params.append(period["from"])
    if period.get("to"):
        sql += f" AND {alias}.created_at < %s"  # before the start of the next day
        params.append(period["to"] + timedelta(days=1))
    return sql, params


def count_by_status(cur, period):
    """{status: count} for the statuses that occur."""
    where, params = _range(period)
    cur.execute(f"SELECT c.status, COUNT(*) AS n FROM complaints c WHERE TRUE{where} GROUP BY c.status",
                params)
    return {row["status"]: row["n"] for row in cur.fetchall()}


def count_unassigned_open(cur, period):
    """Open complaints with no current assignment."""
    where, params = _range(period)
    cur.execute(
        f"SELECT COUNT(*) AS n FROM complaints c WHERE c.status IN {_OPEN}{where} AND NOT EXISTS "
        "(SELECT 1 FROM assignments a WHERE a.complaint_id = c.complaint_id AND a.is_current = TRUE)",
        params,
    )
    return cur.fetchone()["n"]


def feedback_summary(cur, period):
    """{count, average} of feedback on complaints in the range; average is None with no feedback."""
    where, params = _range(period)
    cur.execute(
        "SELECT COUNT(*) AS n, AVG(f.rating) AS average FROM feedback f "
        f"JOIN complaints c ON c.complaint_id = f.complaint_id WHERE TRUE{where}",
        params,
    )
    row = cur.fetchone()
    return {"count": row["n"], "average": float(row["average"]) if row["average"] is not None else None}


def by_category(cur, period):
    """Every category (including inactive ones), with its complaint count; busiest first."""
    where, params = _range(period)
    cur.execute(
        "SELECT cat.category_id, cat.name, cat.is_active, COUNT(c.complaint_id) AS n "
        f"FROM categories cat LEFT JOIN complaints c ON c.category_id = cat.category_id{where} "
        "GROUP BY cat.category_id, cat.name, cat.is_active ORDER BY n DESC, cat.name",
        params,
    )
    return cur.fetchall()


def by_department(cur, period):
    """Every department with its complaints (current assignment), plus a row for unassigned ones."""
    where, params = _range(period)
    cur.execute(
        "SELECT d.department_id, d.name, COUNT(c.complaint_id) AS n, "
        f"COALESCE(SUM(c.status IN {_OPEN}), 0) AS open_n "
        "FROM departments d "
        "LEFT JOIN assignments a ON a.department_id = d.department_id AND a.is_current = TRUE "
        f"LEFT JOIN complaints c ON c.complaint_id = a.complaint_id{where} "
        "GROUP BY d.department_id, d.name ORDER BY n DESC, d.name",
        params,
    )
    rows = cur.fetchall()
    cur.execute(
        f"SELECT COUNT(*) AS n, COALESCE(SUM(c.status IN {_OPEN}), 0) AS open_n FROM complaints c "
        "WHERE NOT EXISTS (SELECT 1 FROM assignments a WHERE a.complaint_id = c.complaint_id "
        f"AND a.is_current = TRUE){where}",
        params,
    )
    unassigned = cur.fetchone()
    return rows, unassigned


def by_period(cur, period, group):
    """[{period, n}] for each day or month that has complaints, oldest first."""
    # %% because PyMySQL treats % as a placeholder marker when parameters are passed.
    fmt = "%%Y-%%m-%%d" if group == "day" else "%%Y-%%m"
    where, params = _range(period)
    cur.execute(
        f"SELECT DATE_FORMAT(c.created_at, '{fmt}') AS period, COUNT(*) AS n FROM complaints c "
        f"WHERE TRUE{where} GROUP BY period ORDER BY period",
        params,
    )
    return cur.fetchall()


def pending(cur, period):
    """(oldest open complaints, up to PENDING_LIMIT; total number of open complaints)."""
    where, params = _range(period)
    cur.execute(f"SELECT COUNT(*) AS n FROM complaints c WHERE c.status IN {_OPEN}{where}", params)
    total = cur.fetchone()["n"]
    cur.execute(
        "SELECT c.complaint_id, c.title, c.status, c.created_at, cat.name AS category, "
        "d.name AS department, s.name AS staff, DATEDIFF(NOW(), c.created_at) AS age_days "
        "FROM complaints c JOIN categories cat ON cat.category_id = c.category_id "
        "LEFT JOIN assignments a ON a.complaint_id = c.complaint_id AND a.is_current = TRUE "
        "LEFT JOIN departments d ON d.department_id = a.department_id "
        "LEFT JOIN users s ON s.user_id = a.staff_id "
        f"WHERE c.status IN {_OPEN}{where} ORDER BY c.created_at, c.complaint_id LIMIT %s",
        params + [PENDING_LIMIT],
    )
    return cur.fetchall(), total


def workload(cur, period):
    """Every maintenance staff member with their current complaints by status, busiest first."""
    where, params = _range(period)
    cur.execute(
        "SELECT s.user_id, s.name, s.is_active, d.department_id, d.name AS department, "
        "COALESCE(SUM(c.status = 'assigned'), 0) AS assigned_n, "
        "COALESCE(SUM(c.status = 'in_progress'), 0) AS in_progress_n, "
        "COALESCE(SUM(c.status = 'resolved'), 0) AS resolved_n, "
        "COALESCE(SUM(c.status = 'closed'), 0) AS closed_n "
        "FROM users s LEFT JOIN departments d ON d.department_id = s.department_id "
        "LEFT JOIN assignments a ON a.staff_id = s.user_id AND a.is_current = TRUE "
        f"LEFT JOIN complaints c ON c.complaint_id = a.complaint_id{where} "
        "WHERE s.role = 'maintenance_staff' "
        "GROUP BY s.user_id, s.name, s.is_active, d.department_id, d.name "
        "ORDER BY (assigned_n + in_progress_n) DESC, s.name",
        params,
    )
    return cur.fetchall()
