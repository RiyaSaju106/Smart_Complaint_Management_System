"""PyMySQL data access for the Category/Department module.

Every function takes an open cursor (rows come back as dicts, see db.connection) and only runs
parameterised SQL (SEC-003). Nothing here commits or rolls back: the caller owns the transaction.

Other modules reuse these instead of querying the tables themselves:
  get_active_category          Complaint submission (#17): is this category usable?
  get_department_staff_member  Complaint assignment (#19): may this user take work for this department?
  get_current_assignment       Processing/Status, Notification: who is the complaint assigned to now?
"""

CATEGORY_COLUMNS = "category_id, name, description, is_active"

# Staff of a department: active maintenance_staff users linked to it (users.department_id).
_DEPARTMENT_STAFF = (
    "SELECT user_id, name FROM users "
    "WHERE department_id = %s AND role = 'maintenance_staff' AND is_active = TRUE"
)


def list_categories(cur, include_inactive=False):
    sql = f"SELECT {CATEGORY_COLUMNS} FROM categories"
    if not include_inactive:
        sql += " WHERE is_active = TRUE"
    cur.execute(sql + " ORDER BY name")
    return cur.fetchall()


def get_category(cur, category_id, lock=False):
    sql = f"SELECT {CATEGORY_COLUMNS} FROM categories WHERE category_id = %s"
    if lock:
        sql += " FOR UPDATE"
    cur.execute(sql, (category_id,))
    return cur.fetchone()


def get_active_category(cur, category_id):
    """The category if it exists and is active, otherwise None."""
    cur.execute(
        f"SELECT {CATEGORY_COLUMNS} FROM categories WHERE category_id = %s AND is_active = TRUE",
        (category_id,),
    )
    return cur.fetchone()


def name_taken(cur, name, exclude_id=None):
    """True if another category already has this name.

    The comparison uses the column's collation, the same rule as the uq_categories_name key
    (case- and accent-insensitive), so this check and the database agree.
    """
    sql = "SELECT 1 FROM categories WHERE name = %s"
    params = [name]
    if exclude_id is not None:
        sql += " AND category_id <> %s"
        params.append(exclude_id)
    cur.execute(sql, params)
    return cur.fetchone() is not None


def insert_category(cur, category_id, name, description):
    cur.execute(
        "INSERT INTO categories (category_id, name, description) VALUES (%s, %s, %s)",
        (category_id, name, description),
    )


def update_category(cur, category_id, name, description, is_active):
    cur.execute(
        "UPDATE categories SET name = %s, description = %s, is_active = %s WHERE category_id = %s",
        (name, description, is_active, category_id),
    )


def category_in_use(cur, category_id):
    cur.execute("SELECT 1 FROM complaints WHERE category_id = %s LIMIT 1", (category_id,))
    return cur.fetchone() is not None


def delete_category(cur, category_id):
    cur.execute("DELETE FROM categories WHERE category_id = %s", (category_id,))


def list_departments(cur):
    cur.execute("SELECT department_id, name, description FROM departments ORDER BY name")
    return cur.fetchall()


def department_exists(cur, department_id):
    cur.execute("SELECT 1 FROM departments WHERE department_id = %s", (department_id,))
    return cur.fetchone() is not None


def list_department_staff(cur, department_id):
    cur.execute(_DEPARTMENT_STAFF + " ORDER BY name", (department_id,))
    return cur.fetchall()


def get_department_staff_member(cur, department_id, user_id):
    """{user_id, name} if the user is active maintenance staff in this department, else None."""
    cur.execute(_DEPARTMENT_STAFF + " AND user_id = %s", (department_id, user_id))
    return cur.fetchone()


def lock_complaint(cur, complaint_id):
    """{resident_id, status} of the complaint, locked until commit so two concurrent assignments
    cannot both pass the status check. None if the complaint does not exist."""
    cur.execute(
        "SELECT resident_id, status FROM complaints WHERE complaint_id = %s FOR UPDATE",
        (complaint_id,),
    )
    return cur.fetchone()


def get_current_assignment(cur, complaint_id):
    """{department_id, staff_id, assigned_at} of the current assignment, or None."""
    cur.execute(
        "SELECT department_id, staff_id, assigned_at FROM assignments "
        "WHERE complaint_id = %s AND is_current = TRUE",
        (complaint_id,),
    )
    return cur.fetchone()


def end_current_assignment(cur, complaint_id):
    """Mark the current assignment (if any) as no longer current. The row itself is kept."""
    cur.execute(
        "UPDATE assignments SET is_current = FALSE WHERE complaint_id = %s AND is_current = TRUE",
        (complaint_id,),
    )


def insert_assignment(cur, assignment_id, complaint_id, assigned_by, department_id, staff_id):
    cur.execute(
        "INSERT INTO assignments "
        "(assignment_id, complaint_id, assigned_by, department_id, staff_id, is_current) "
        "VALUES (%s, %s, %s, %s, %s, TRUE)",
        (assignment_id, complaint_id, assigned_by, department_id, staff_id),
    )


def get_assigned_at(cur, assignment_id):
    cur.execute("SELECT assigned_at FROM assignments WHERE assignment_id = %s", (assignment_id,))
    return cur.fetchone()["assigned_at"]


def set_complaint_status(cur, complaint_id, new_status):
    cur.execute(
        "UPDATE complaints SET status = %s WHERE complaint_id = %s", (new_status, complaint_id)
    )
