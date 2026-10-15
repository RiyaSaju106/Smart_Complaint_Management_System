"""PyMySQL data access for the Processing & Status module.

Every function takes an open cursor (rows come back as dicts, see db.connection) and only runs
parameterised SQL (SEC-003). Nothing here commits or rolls back: the route owns the transaction, so
a resolution, its history row and the status change succeed or fail together.

Timestamps are not set here; MySQL fills them (DEFAULT / ON UPDATE CURRENT_TIMESTAMP).
"""
import uuid


def list_assigned(cur, staff_id, status=None):
    """Complaints whose *current* assignment is this staff member, newest first."""
    sql = (
        "SELECT c.complaint_id, c.title, c.category_id, cat.name AS category, c.location, "
        "c.status, c.created_at "
        "FROM complaints c "
        "JOIN assignments a ON a.complaint_id = c.complaint_id AND a.is_current = TRUE "
        "JOIN categories cat ON cat.category_id = c.category_id "
        "WHERE a.staff_id = %s"
    )
    params = [staff_id]
    if status:
        sql += " AND c.status = %s"
        params.append(status)
    sql += " ORDER BY c.created_at DESC"
    cur.execute(sql, params)
    return cur.fetchall()


def lock_complaint(cur, complaint_id):
    """Fetch {resident_id, status} and lock the row until commit, so two concurrent requests
    cannot both pass the transition check. Returns None if the complaint does not exist."""
    cur.execute(
        "SELECT resident_id, status FROM complaints WHERE complaint_id = %s FOR UPDATE",
        (complaint_id,),
    )
    return cur.fetchone()


def current_staff_id(cur, complaint_id):
    """staff_id of the current assignment, or None (no current assignment, or no staff set)."""
    cur.execute(
        "SELECT staff_id FROM assignments WHERE complaint_id = %s AND is_current = TRUE",
        (complaint_id,),
    )
    row = cur.fetchone()
    return row["staff_id"] if row else None


def has_resolution(cur, complaint_id):
    cur.execute("SELECT 1 FROM resolutions WHERE complaint_id = %s", (complaint_id,))
    return cur.fetchone() is not None


def insert_resolution(cur, complaint_id, resolved_by, details):
    cur.execute(
        "INSERT INTO resolutions (resolution_id, complaint_id, resolved_by, details) "
        "VALUES (%s, %s, %s, %s)",
        (str(uuid.uuid4()), complaint_id, resolved_by, details),
    )


def insert_history(cur, complaint_id, old_status, new_status, changed_by, remarks):
    """Append one status_history row. That table is append-only: never UPDATE or DELETE it."""
    cur.execute(
        "INSERT INTO status_history "
        "(history_id, complaint_id, old_status, new_status, changed_by, remarks) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (str(uuid.uuid4()), complaint_id, old_status, new_status, changed_by, remarks),
    )


def set_status(cur, complaint_id, new_status):
    """Update the complaint's status and return the new updated_at (set by MySQL)."""
    cur.execute(
        "UPDATE complaints SET status = %s WHERE complaint_id = %s", (new_status, complaint_id)
    )
    cur.execute("SELECT updated_at FROM complaints WHERE complaint_id = %s", (complaint_id,))
    return cur.fetchone()["updated_at"]