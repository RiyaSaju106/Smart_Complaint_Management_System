"""Fixtures for database tests.

Tests run against TEST_DB_NAME (default scms_test_db), never DB_NAME.
The test database is created if missing, the schema is applied once per
session, and the users table is emptied before each test.
"""
import os

import pytest

from db.apply_schema import apply_schema
from db.connection import get_connection, get_settings

TEST_DB_NAME = os.environ.get("TEST_DB_NAME", "scms_test_db")


@pytest.fixture(scope="session")
def test_db_name():
    if TEST_DB_NAME == get_settings()["database"] or TEST_DB_NAME == "scms_db":
        pytest.exit(f"Refusing to run tests against {TEST_DB_NAME!r}: it is not a test database.")
    conn = get_connection(use_database=False)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{TEST_DB_NAME}` "
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
        cur.execute("DELETE FROM users")
    conn.commit()
    yield conn
    conn.rollback()
    conn.close()
