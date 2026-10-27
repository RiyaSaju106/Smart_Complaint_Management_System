"""Fixtures for the Notification tests. Runs against TEST_DB_NAME only, never DB_NAME.

Uses the real app factory and the real /api/auth/login endpoint, so these tests also prove the
notification module works with the session that Auth/User creates. Every module's get_connection
is pointed at the test database.
"""
import os
import uuid

import pytest

import app.auth.routes as auth_routes
import app.notifications.routes as notification_routes
import app.notifications.service as notification_service
import process.routes as processing_routes
from app import create_app
from db.apply_schema import apply_schema
from db.connection import get_connection as _real_get_connection
from db.passwords import hash_password

PASSWORD = "Secret123!"
PASSWORD_HASH = hash_password(PASSWORD)  # hashed once; hashing is deliberately slow

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
    if name == os.environ.get("DB_NAME"):
        pytest.exit("TEST_DB_NAME must differ from DB_NAME; refusing to run.", returncode=2)
    conn = _real_get_connection(database=name)
    try:
        apply_schema(conn)
    finally:
        conn.close()
    return name


@pytest.fixture
def conn(test_db_name):
    """Autocommit connection for seeding and assertions, with all tables emptied first."""
    c = _real_get_connection(database=test_db_name)
    c.autocommit(True)
    with c.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        for table in TABLES:
            cur.execute(f"TRUNCATE TABLE {table}")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
    yield c
    c.close()


class Seed:
    def __init__(self, conn):
        self.conn = conn
        self._department = None
        self._category = None
        self._admin = None

    def _run(self, sql, params=()):
        with self.conn.cursor() as cur:
            cur.execute(sql, params)

    def department(self):
        if self._department is None:
            self._department = str(uuid.uuid4())
            self._run("INSERT INTO departments (department_id, name) VALUES (%s, %s)",
                      (self._department, f"dept-{self._department}"))
        return self._department

    def category(self):
        if self._category is None:
            self._category = str(uuid.uuid4())
            self._run("INSERT INTO categories (category_id, name) VALUES (%s, %s)",
                      (self._category, f"cat-{self._category}"))
        return self._category

    def user(self, role):
        """Create a user who can log in with PASSWORD. Returns (user_id, email)."""
        uid = str(uuid.uuid4())
        email = f"{role}-{uid[:8]}@example.com"
        department = self.department() if role == "maintenance_staff" else None
        self._run(
            "INSERT INTO users (user_id, name, email, password_hash, role, department_id) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (uid, f"{role} {uid[:8]}", email, PASSWORD_HASH, role, department),
        )
        return uid, email

    @property
    def admin(self):
        if self._admin is None:
            self._admin = self.user("administrator")
        return self._admin

    def complaint(self, resident_id, status="submitted", title="Leaking tap"):
        cid = str(uuid.uuid4())
        self._run(
            "INSERT INTO complaints (complaint_id, resident_id, title, category_id, description, "
            "location, status) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (cid, resident_id, title, self.category(), "Tap leaks.", "Block A, Unit 101", status),
        )
        return cid

    def assign(self, complaint_id, staff_id):
        self._run(
            "INSERT INTO assignments (assignment_id, complaint_id, assigned_by, department_id, staff_id) "
            "VALUES (%s, %s, %s, %s, %s)",
            (str(uuid.uuid4()), complaint_id, self.admin[0], self.department(), staff_id),
        )


@pytest.fixture
def seed(conn):
    return Seed(conn)


@pytest.fixture(autouse=True)
def use_test_database(monkeypatch, test_db_name):
    """Every module's database calls, including direct notify() calls, go to the test database."""
    connect = lambda: _real_get_connection(database=test_db_name)  # noqa: E731
    for module in (auth_routes, processing_routes, notification_routes, notification_service):
        monkeypatch.setattr(module, "get_connection", connect)


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-pytest")
    flask_app = create_app()
    flask_app.config.update(TESTING=True)
    return flask_app


@pytest.fixture
def login(app):
    """login(email) -> a test client logged in through the real /api/auth/login endpoint."""
    def make(email):
        client = app.test_client()
        response = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
        assert response.status_code == 200, response.get_json()
        return client
    return make
