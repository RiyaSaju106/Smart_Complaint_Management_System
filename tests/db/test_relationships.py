"""Relationship and constraint tests for the core SCMS schema (Issue #15)."""
import uuid

import pymysql
import pytest

from db.passwords import hash_password

ER_DUP_ENTRY = 1062
ER_ROW_IS_REFERENCED = 1451
ER_NO_REFERENCED_ROW = 1452
ER_CHECK_CONSTRAINT_VIOLATED = 3819


def new_id():
    return str(uuid.uuid4())


def insert(conn, table, **values):
    columns = ", ".join(values)
    placeholders = ", ".join(["%s"] * len(values))
    with conn.cursor() as cur:
        cur.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", tuple(values.values()))
    conn.commit()


def errno_of(excinfo):
    return excinfo.value.args[0]


def add_department(conn, name="Plumbing"):
    department_id = new_id()
    insert(conn, "departments", department_id=department_id, name=name)
    return department_id


def add_category(conn, name="Water Supply"):
    category_id = new_id()
    insert(conn, "categories", category_id=category_id, name=name)
    return category_id


def add_user(conn, role="resident", department_id=None):
    user_id = new_id()
    insert(
        conn, "users",
        user_id=user_id, name=f"Test {role}", email=f"{user_id}@example.com",
        password_hash=hash_password("Secret123!"), role=role, department_id=department_id,
    )
    return user_id


def add_complaint(conn, resident_id, category_id, **overrides):
    complaint_id = new_id()
    values = dict(
        complaint_id=complaint_id, resident_id=resident_id, title="Leaking tap",
        category_id=category_id, description="Kitchen tap leaks.", location="Block A, 101",
    )
    values.update(overrides)
    insert(conn, "complaints", **values)
    return complaint_id


@pytest.fixture
def world(conn):
    """A department, category, resident, administrator, staff member and one complaint."""
    department_id = add_department(conn)
    category_id = add_category(conn)
    resident_id = add_user(conn, "resident")
    admin_id = add_user(conn, "administrator")
    staff_id = add_user(conn, "maintenance_staff", department_id)
    complaint_id = add_complaint(conn, resident_id, category_id)
    return dict(
        department_id=department_id, category_id=category_id, resident_id=resident_id,
        admin_id=admin_id, staff_id=staff_id, complaint_id=complaint_id,
    )


def test_complaint_lifecycle_records_related_rows(conn, world):
    w = world
    insert(conn, "assignments", assignment_id=new_id(), complaint_id=w["complaint_id"],
           assigned_by=w["admin_id"], department_id=w["department_id"], staff_id=w["staff_id"])
    history = [
        (None, "submitted", w["resident_id"], "2026-10-14 09:00:00"),
        ("submitted", "assigned", w["admin_id"], "2026-10-14 10:00:00"),
        ("assigned", "in_progress", w["staff_id"], "2026-10-14 11:00:00"),
        ("in_progress", "resolved", w["staff_id"], "2026-10-14 12:00:00"),
    ]
    for old, new, actor, at in history:
        insert(conn, "status_history", history_id=new_id(), complaint_id=w["complaint_id"],
               old_status=old, new_status=new, changed_by=actor, changed_at=at)
    insert(conn, "resolutions", resolution_id=new_id(), complaint_id=w["complaint_id"],
           resolved_by=w["staff_id"], details="Replaced washer.")
    insert(conn, "feedback", feedback_id=new_id(), complaint_id=w["complaint_id"],
           resident_id=w["resident_id"], rating=5, comments="Quick fix.")
    insert(conn, "notifications", notification_id=new_id(), user_id=w["resident_id"],
           complaint_id=w["complaint_id"], event="COMPLAINT_RESOLVED", message="Resolved.")
    insert(conn, "attachments", attachment_id=new_id(), complaint_id=w["complaint_id"],
           file_path="uploads/tap.jpg", file_type="image/jpeg", file_size_kb=120)

    with conn.cursor() as cur:
        cur.execute(
            "SELECT c.status, cat.name AS category, u.role AS resident_role, "
            "a.staff_id, d.name AS department, f.rating, r.details "
            "FROM complaints c "
            "JOIN categories cat ON cat.category_id = c.category_id "
            "JOIN users u ON u.user_id = c.resident_id "
            "JOIN assignments a ON a.complaint_id = c.complaint_id AND a.is_current "
            "JOIN departments d ON d.department_id = a.department_id "
            "JOIN feedback f ON f.complaint_id = c.complaint_id "
            "JOIN resolutions r ON r.complaint_id = c.complaint_id "
            "WHERE c.complaint_id = %s",
            (w["complaint_id"],),
        )
        row = cur.fetchone()
        cur.execute(
            "SELECT old_status, new_status, changed_by FROM status_history "
            "WHERE complaint_id = %s ORDER BY changed_at",
            (w["complaint_id"],),
        )
        rows = cur.fetchall()

    assert row == {
        "status": "submitted", "category": "Water Supply", "resident_role": "resident",
        "staff_id": w["staff_id"], "department": "Plumbing", "rating": 5,
        "details": "Replaced washer.",
    }
    assert [(r["old_status"], r["new_status"], r["changed_by"]) for r in rows] == [
        (old, new, actor) for old, new, actor, _ in history
    ]


def test_new_complaint_defaults_to_submitted(conn, world):
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM complaints WHERE complaint_id = %s", (world["complaint_id"],))
        assert cur.fetchone()["status"] == "submitted"


def test_new_user_defaults_to_active(conn, world):
    with conn.cursor() as cur:
        cur.execute("SELECT is_active FROM users WHERE user_id = %s", (world["resident_id"],))
        assert cur.fetchone()["is_active"] == 1


def test_complaint_with_unknown_category_rejected(conn, world):
    with pytest.raises(pymysql.err.IntegrityError) as excinfo:
        add_complaint(conn, world["resident_id"], new_id())
    assert errno_of(excinfo) == ER_NO_REFERENCED_ROW


def test_complaint_with_unknown_resident_rejected(conn, world):
    with pytest.raises(pymysql.err.IntegrityError) as excinfo:
        add_complaint(conn, new_id(), world["category_id"])
    assert errno_of(excinfo) == ER_NO_REFERENCED_ROW


def test_user_with_unknown_department_rejected(conn):
    with pytest.raises(pymysql.err.IntegrityError) as excinfo:
        add_user(conn, "maintenance_staff", department_id=new_id())
    assert errno_of(excinfo) == ER_NO_REFERENCED_ROW


def test_assignment_with_unknown_department_rejected(conn, world):
    with pytest.raises(pymysql.err.IntegrityError) as excinfo:
        insert(conn, "assignments", assignment_id=new_id(), complaint_id=world["complaint_id"],
               assigned_by=world["admin_id"], department_id=new_id())
    assert errno_of(excinfo) == ER_NO_REFERENCED_ROW


@pytest.mark.parametrize("duplicate", ["Water Supply", "water supply"])
def test_duplicate_category_name_rejected(conn, world, duplicate):
    with pytest.raises(pymysql.err.IntegrityError) as excinfo:
        add_category(conn, duplicate)
    assert errno_of(excinfo) == ER_DUP_ENTRY


def test_duplicate_department_name_rejected(conn, world):
    with pytest.raises(pymysql.err.IntegrityError) as excinfo:
        add_department(conn, "Plumbing")
    assert errno_of(excinfo) == ER_DUP_ENTRY


@pytest.mark.parametrize("status", ["Submitted", "In Progress", "open", ""])
def test_invalid_complaint_status_rejected(conn, world, status):
    with pytest.raises(pymysql.err.DataError):
        add_complaint(conn, world["resident_id"], world["category_id"], status=status)


def test_description_over_1000_characters_rejected(conn, world):
    with pytest.raises(pymysql.err.OperationalError) as excinfo:
        add_complaint(conn, world["resident_id"], world["category_id"], description="x" * 1001)
    assert errno_of(excinfo) == ER_CHECK_CONSTRAINT_VIOLATED


def test_only_one_current_assignment_per_complaint(conn, world):
    w = world
    first = new_id()
    insert(conn, "assignments", assignment_id=first, complaint_id=w["complaint_id"],
           assigned_by=w["admin_id"], department_id=w["department_id"])

    with pytest.raises(pymysql.err.IntegrityError) as excinfo:
        insert(conn, "assignments", assignment_id=new_id(), complaint_id=w["complaint_id"],
               assigned_by=w["admin_id"], department_id=w["department_id"])
    assert errno_of(excinfo) == ER_DUP_ENTRY

    # Reassignment: retire the current row, then add the new one. History is kept.
    with conn.cursor() as cur:
        cur.execute("UPDATE assignments SET is_current = FALSE WHERE assignment_id = %s", (first,))
    conn.commit()
    insert(conn, "assignments", assignment_id=new_id(), complaint_id=w["complaint_id"],
           assigned_by=w["admin_id"], department_id=w["department_id"], staff_id=w["staff_id"])
    with conn.cursor() as cur:
        cur.execute(
            "SELECT SUM(is_current) AS current_rows, COUNT(*) AS all_rows FROM assignments "
            "WHERE complaint_id = %s",
            (w["complaint_id"],),
        )
        counts = cur.fetchone()
    assert (counts["current_rows"], counts["all_rows"]) == (1, 2)


@pytest.mark.parametrize("rating", [0, 6])
def test_feedback_rating_outside_1_to_5_rejected(conn, world, rating):
    with pytest.raises(pymysql.err.OperationalError) as excinfo:
        insert(conn, "feedback", feedback_id=new_id(), complaint_id=world["complaint_id"],
               resident_id=world["resident_id"], rating=rating)
    assert errno_of(excinfo) == ER_CHECK_CONSTRAINT_VIOLATED


def test_only_one_feedback_per_complaint(conn, world):
    values = dict(complaint_id=world["complaint_id"], resident_id=world["resident_id"], rating=4)
    insert(conn, "feedback", feedback_id=new_id(), **values)
    with pytest.raises(pymysql.err.IntegrityError) as excinfo:
        insert(conn, "feedback", feedback_id=new_id(), **values)
    assert errno_of(excinfo) == ER_DUP_ENTRY


def test_only_one_resolution_per_complaint(conn, world):
    values = dict(complaint_id=world["complaint_id"], resolved_by=world["staff_id"], details="Fixed.")
    insert(conn, "resolutions", resolution_id=new_id(), **values)
    with pytest.raises(pymysql.err.IntegrityError) as excinfo:
        insert(conn, "resolutions", resolution_id=new_id(), **values)
    assert errno_of(excinfo) == ER_DUP_ENTRY


def test_category_in_use_cannot_be_deleted(conn, world):
    with pytest.raises(pymysql.err.IntegrityError) as excinfo:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM categories WHERE category_id = %s", (world["category_id"],))
    assert errno_of(excinfo) == ER_ROW_IS_REFERENCED


def test_complaint_with_history_cannot_be_deleted(conn, world):
    insert(conn, "status_history", history_id=new_id(), complaint_id=world["complaint_id"],
           new_status="submitted", changed_by=world["resident_id"])
    with pytest.raises(pymysql.err.IntegrityError) as excinfo:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM complaints WHERE complaint_id = %s", (world["complaint_id"],))
    assert errno_of(excinfo) == ER_ROW_IS_REFERENCED
