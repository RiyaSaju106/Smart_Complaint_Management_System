"""Fixtures for the Processing & Status tests. Runs against TEST_DB_NAME only, never DB_NAME.

The real blueprint is mounted on a minimal Flask app (the project's app factory is not needed to
exercise these routes). Requests go through the real role_required decorator and the real
PyMySQL code path; only get_connection is pointed at the test database.
"""
import os
import uuid

import pytest
from flask import Flask, jsonify, request, session

import processing.routes as routes
from db.apply_schema import apply_schema
from db.connection import get_connection as _real_get_connection

# Children first, so the order is also valid when foreign keys are enforced.
TABLES = (
    "feedback", "notifications", "resolutions", "status_history", "assignments",
    "attachments", "complaints", "categories", "users", "departments",
)


def _test_db_name():
    name = os.environ.get("TEST_DB_NAME", "").strip()
    if not name:
        pytest.exit("TEST_DB_NAME is not set (see db/README.md, step 4).", returncode=2)
    if name == os.environ.get("DB_NAME"):
        pytest.exit("TEST_DB_NAME must differ from DB_NAME; refusing to run.", returncode=2)
    return name


@pytest.fixture(scope="session")
def test_db_name():
    name = _test_db_name()
    conn = _real_get_connection(database=name)
    try:
        apply_schema(conn)  # CREATE TABLE IF NOT EXISTS; same schema the app uses, no second one
    finally:
        conn.close()
    return name


@pytest.fixture
def conn(test_db_name):
    """Autocommit connection for seeding and assertions, with all tables emptied first."""
    c = _real_get_connection(database=test_db_name)
    c.autocommit(True)  # see rows committed by the app's own connections
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
        uid = str(uuid.uuid4())
        department = self.department() if role == "maintenance_staff" else None
        self._run(
            "INSERT INTO users (user_id, name, email, password_hash, role, department_id) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (uid, f"{role} {uid[:8]}", f"{role}-{uid}@example.com", "not-a-real-hash", role, department),
        )
        return uid

    @property
    def admin(self):
        if self._admin is None:
            self._admin = self.user("administrator")
        return self._admin

    def complaint(self, resident_id, status="submitted"):
        cid = str(uuid.uuid4())
        self._run(
            "INSERT INTO complaints (complaint_id, resident_id, title, category_id, description, "
            "location, status) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (cid, resident_id, "Leaking tap", self.category(), "Tap leaks.", "Block A, Unit 101", status),
        )
        return cid

    def assign(self, complaint_id, staff_id):
        self._run(
            "INSERT INTO assignments (assignment_id, complaint_id, assigned_by, department_id, staff_id) "
            "VALUES (%s, %s, %s, %s, %s)",
            (str(uuid.uuid4()), complaint_id, self.admin, self.department(), staff_id),
        )

    def resolution(self, complaint_id, resolved_by, details="Replaced the washer."):
        self._run(
            "INSERT INTO resolutions (resolution_id, complaint_id, resolved_by, details) "
            "VALUES (%s, %s, %s, %s)",
            (str(uuid.uuid4()), complaint_id, resolved_by, details),
        )


@pytest.fixture
def seed(conn):
    return Seed(conn)


@pytest.fixture
def app(monkeypatch, test_db_name):
    monkeypatch.setattr(routes, "get_connection", lambda: _real_get_connection(database=test_db_name))
    flask_app = Flask(__name__)
    flask_app.config.update(SECRET_KEY="test-only", TESTING=True)
    flask_app.register_blueprint(routes.processing_bp)

    @flask_app.post("/__test_login")  # stands in for auth login: sets the same session keys
    def _test_login():
        body = request.get_json()
        session["user_id"] = body["user_id"]
        session["role"] = body["role"]
        return jsonify({}), 200

    return flask_app


@pytest.fixture
def client_for(app):
    """client_for(user_id, role) -> test client logged in as that user; no args -> anonymous."""
    def make(user_id=None, role=None):
        client = app.test_client()
        if user_id is not None:
            assert client.post("/__test_login", json={"user_id": user_id, "role": role}).status_code == 200
        return client
    return make