"""Fixtures for the Category/Assignment tests. Runs against TEST_DB_NAME only, never DB_NAME.

Requests go through the real app factory, the real role_required decorator and the real PyMySQL
code; only get_connection is pointed at the test database. Login is stood in for by writing the
same session keys that /api/auth/login sets.
"""
import os
import uuid

import pytest

from app import create_app
from db.apply_schema import apply_schema
from db.connection import get_connection

# Children first, so the order is also valid when foreign keys are enforced.
TABLES = (
    "feedback", "notifications", "resolutions", "status_history", "assignments",
    "attachments", "complaints", "categories", "users", "departments",
)


@pytest.fixture(scope="session")
def test_db_name():
    name = os.environ.get("TEST_DB_NAME", "").strip()
    if not name:
        pytest.exit("TEST_DB_NAME is not set (see db/README.md, step 4).", returncode=2)
    if name in (os.environ.get("DB_NAME"), "scms_db"):
        pytest.exit("TEST_DB_NAME must differ from DB_NAME; refusing to run.", returncode=2)
    server = get_connection(use_database=False)
    try:
        with server.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
            )
    finally:
        server.close()
    conn = get_connection(database=name)
    try:
        apply_schema(conn)  # the same schema the app uses
    finally:
        conn.close()
    return name


@pytest.fixture
def conn(test_db_name):
    """Autocommit connection for seeding and assertions, with all tables emptied first."""
    c = get_connection(database=test_db_name)
    c.autocommit(True)  # see rows committed by the app's own connections
    with c.cursor() as cur:
        cur.execute("SELECT DATABASE() AS db")
        assert cur.fetchone()["db"] == test_db_name
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        for table in TABLES:
            cur.execute(f"TRUNCATE TABLE {table}")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
    yield c
    c.close()


@pytest.fixture
def app(monkeypatch, conn, test_db_name, tmp_path):
    monkeypatch.setenv("SECRET_KEY", "test-only")
    test_connection = lambda: get_connection(database=test_db_name)  # noqa: E731
    monkeypatch.setattr("app.categories.routes.get_connection", test_connection)
    monkeypatch.setattr("app.complaints.routes.get_connection", test_connection)
    monkeypatch.setattr("process.routes.get_connection", test_connection)
    monkeypatch.setattr("app.notifications.service.get_connection", test_connection)
    monkeypatch.setattr("app.notifications.routes.get_connection", test_connection)
    monkeypatch.setattr("app.tracking.routes.get_connection", test_connection)
    monkeypatch.setattr("app.tracking.search.get_connection", test_connection)
    flask_app = create_app()
    flask_app.config.update(TESTING=True, ATTACHMENT_UPLOAD_DIR=str(tmp_path))
    return flask_app


@pytest.fixture
def client_for(app):
    """client_for(user_id, role) -> test client logged in as that user; no args -> anonymous."""
    def make(user_id=None, role=None):
        client = app.test_client()
        if user_id is not None:
            with client.session_transaction() as sess:
                sess["user_id"] = user_id
                sess["role"] = role
                sess["name"] = "Test User"
        return client
    return make


class Seed:
    def __init__(self, conn):
        self.conn = conn

    def _run(self, sql, params=()):
        with self.conn.cursor() as cur:
            cur.execute(sql, params)

    def department(self, name=None):
        department_id = str(uuid.uuid4())
        self._run(
            "INSERT INTO departments (department_id, name, description) VALUES (%s, %s, %s)",
            (department_id, name or f"dept-{department_id}", "Test department"),
        )
        return department_id

    def category(self, name=None, active=True):
        category_id = str(uuid.uuid4())
        self._run(
            "INSERT INTO categories (category_id, name, description, is_active) "
            "VALUES (%s, %s, %s, %s)",
            (category_id, name or f"cat-{category_id}", "Test category", active),
        )
        return category_id

    def user(self, role, department_id=None, name=None, active=True):
        user_id = str(uuid.uuid4())
        self._run(
            "INSERT INTO users (user_id, name, email, password_hash, contact_number, unit_address, "
            "role, department_id, is_active) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                user_id, name or f"{role} {user_id[:8]}", f"{user_id}@example.com",
                "not-a-real-hash", "9876543210", "Test Block, Unit 101", role, department_id, active,
            ),
        )
        return user_id

    def complaint(self, resident_id, category_id, status="submitted"):
        complaint_id = str(uuid.uuid4())
        self._run(
            "INSERT INTO complaints (complaint_id, resident_id, title, category_id, description, "
            "location, status) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (complaint_id, resident_id, "Leaking tap", category_id, "Tap leaks.", "Block A", status),
        )
        return complaint_id

    def assignment(self, complaint_id, assigned_by, department_id, staff_id=None):
        self._run(
            "INSERT INTO assignments (assignment_id, complaint_id, assigned_by, department_id, "
            "staff_id) VALUES (%s, %s, %s, %s, %s)",
            (str(uuid.uuid4()), complaint_id, assigned_by, department_id, staff_id),
        )

    def scalar(self, sql, params=()):
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
        return next(iter(row.values())) if row else None


@pytest.fixture
def seed(conn):
    return Seed(conn)


@pytest.fixture
def admin(seed, client_for):
    return client_for(seed.user("administrator"), "administrator")


@pytest.fixture
def resident(seed, client_for):
    return client_for(seed.user("resident"), "resident")


@pytest.fixture
def staff(seed, client_for):
    return client_for(seed.user("maintenance_staff", seed.department()), "maintenance_staff")
