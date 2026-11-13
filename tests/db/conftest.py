"""Fixtures for database tests.

Tests run against TEST_DB_NAME (default scms_test_db), never DB_NAME.
Each test session drops and recreates the test database and applies the schema from scratch, which
also proves the schema builds on a clean database. All tables are emptied before each test.
"""
import os

import pytest

from db.apply_schema import apply_schema
from db.connection import get_connection, get_settings
from app import create_app

TEST_DB_NAME = os.environ.get("TEST_DB_NAME", "scms_test_db")

# Child tables first, so deletes never hit a foreign key.
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
    conn = get_connection(database=test_db_name)
    with conn.cursor() as cur:
        cur.execute("SELECT DATABASE() AS db")
        assert cur.fetchone()["db"] == test_db_name
        for table in TABLES:
            cur.execute(f"DELETE FROM {table}")
    conn.commit()
    yield conn
    conn.rollback()
    conn.close()

@pytest.fixture
def app(monkeypatch, conn, test_db_name, tmp_path):
    conn.autocommit(True)  # test connection always sees what the app commits

    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-pytest")
    # New connection per request, so the 5 concurrent threads never share one,
    # and every request goes to the TEST database.
    monkeypatch.setattr(
        "app.complaints.routes.get_connection",
        lambda: get_connection(database=test_db_name),
    )
    flask_app = create_app()
    flask_app.config.update(
        TESTING=True,
        ATTACHMENT_UPLOAD_DIR=str(tmp_path / "attachments"),
    )
    return flask_app

@pytest.fixture
def client(app):
    """A test client for the Flask application."""
    return app.test_client()