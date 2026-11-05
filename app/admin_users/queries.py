"""PyMySQL SQL for administrator user management (FR-023, #33).

Every query takes an open cursor. No password hash is ever selected for output.
"""
import uuid

USER_COLUMNS = (
    "u.user_id, u.name, u.email, u.role, u.contact_number, u.unit_address, "
    "u.department_id, d.name AS department, u.is_active, u.created_at, u.updated_at"
)
_FROM = "FROM users u LEFT JOIN departments d ON d.department_id = u.department_id"
_MANAGED = "u.role IN ('resident', 'maintenance_staff')"


def list_users(cur, filters):
    where, params = [_MANAGED], []
    if filters["role"]:
        where.append("u.role = %s")
        params.append(filters["role"])
    if filters["status"]:
        where.append("u.is_active = %s")
        params.append(filters["status"] == "active")
    if filters["department_id"]:
        where.append("u.department_id = %s")
        params.append(filters["department_id"])
    if filters["q"]:
        where.append("(u.name LIKE %s OR u.email LIKE %s)")
        like = f"%{filters['q']}%"
        params += [like, like]
    clause = " WHERE " + " AND ".join(where)

    cur.execute(f"SELECT COUNT(*) AS n {_FROM}{clause}", params)
    total = cur.fetchone()["n"]
    offset = (filters["page"] - 1) * filters["page_size"]
    cur.execute(
        f"SELECT {USER_COLUMNS} {_FROM}{clause} ORDER BY u.created_at DESC, u.name "
        "LIMIT %s OFFSET %s",
        params + [filters["page_size"], offset],
    )
    return cur.fetchall(), total


def get_user(cur, user_id):
    """Any role, so the route can tell 'not found' from 'administrator account'."""
    cur.execute(f"SELECT {USER_COLUMNS} {_FROM} WHERE u.user_id = %s", (user_id,))
    return cur.fetchone()


def department_exists(cur, department_id):
    cur.execute("SELECT 1 AS ok FROM departments WHERE department_id = %s", (department_id,))
    return cur.fetchone() is not None


def insert_user(cur, clean, password_hash):
    user_id = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO users (user_id, name, email, password_hash, contact_number, unit_address, "
        "role, department_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (user_id, clean["name"], clean["email"], password_hash, clean["contact_number"],
         clean["unit_address"], clean["role"], clean["department_id"]),
    )
    return user_id


def update_user(cur, user_id, changes):
    assignments = ", ".join(f"{field} = %s" for field in changes)  # field names come from schema.UPDATABLE only
    cur.execute(
        f"UPDATE users SET {assignments} WHERE user_id = %s",
        list(changes.values()) + [user_id],
    )


def set_active(cur, user_id, active):
    cur.execute("UPDATE users SET is_active = %s WHERE user_id = %s", (active, user_id))


def open_complaint_count(cur, staff_id):
    """Complaints currently assigned to this staff member that are still being worked on."""
    cur.execute(
        "SELECT COUNT(*) AS n FROM assignments a "
        "JOIN complaints c ON c.complaint_id = a.complaint_id "
        "WHERE a.staff_id = %s AND a.is_current = TRUE "
        "AND c.status IN ('assigned', 'in_progress')",
        (staff_id,),
    )
    return cur.fetchone()["n"]