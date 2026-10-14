"""Fixtures for database tests.

Tests run against TEST_DB_NAME (default scms_test_db), never DB_NAME.
Each test session drops and recreates the test database and applies the schema from scratch, which
also proves the schema builds on a clean database. All tables are emptied before each test.
"""
import os

import pytest

from db.apply_schema import apply_schema
from db.connection import get_connection, get_settings

TEST_DB_NAME = os.environ.get("TEST_DB_NAME", "scms_test_db")

# Child tables first, so deletes never hit a foreign key.
TABLES = (
    "feedback", "notifications", "resolutions", "status_history", "assignments",
    "attachments", "complaints", "categories", "users", "departments",
)


@pytest.fixture(scope="session")
def test_db_name():
    if TEST_DB_NAME == get_settings()["database"] or TEST_DB_NAME == "scms_db":
        pytest.exit(f"Refusing to run tests against {TEST_DB_NAME!r}: it is not a test database.")
    conn = get_connection(use_database=False)
    try:
        with conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS `{TEST_DB_NAME}`")
            cur.execute(
                f"CREATE DATABASE `{TEST_DB_NAME}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
            )
        conn.commit()
    finally:
        conn.close()
    conn = get_connection(database=TEST_DB_NAME)
    try:
        apply_schema(conn)
    finally:
        conn.close()
    return TEST_DB_NAME


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
