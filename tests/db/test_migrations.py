"""Fresh setup and upgrade-from-older-schema tests for db/apply_schema.py.

Each test rebuilds the test database in a specific starting state, runs apply_schema twice and
checks that existing users are preserved and the second run changes nothing. The test database is
rebuilt fresh afterwards so other tests are unaffected.
"""
import pytest

from db.apply_schema import MigrationError, apply_schema
from db.connection import get_connection
from db.passwords import hash_password, verify_password

ALL_TABLES = sorted([
    "assignments", "attachments", "categories", "complaints", "departments", "feedback",
    "notifications", "resolutions", "status_history", "users",
])

LEGACY_USERS_TABLE = """
CREATE TABLE users (
    user_id       CHAR(36)     NOT NULL,
    name          VARCHAR(100) NOT NULL,
    email         VARCHAR(100) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role          {role_type}  NOT NULL,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id),
    UNIQUE KEY uq_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
"""

# Every users.role shape that earlier versions of this branch (or early drafts) produced,
# with the stored values to migrate and the role each should become.
LEGACY_SCHEMAS = {
    "v1_capitalized_enum_case_insensitive": (
        "ENUM('Resident', 'Maintenance Staff', 'Administrator')",
        {"Resident": "resident", "Maintenance Staff": "maintenance_staff",
         "Administrator": "administrator"},
    ),
    "v2_capitalized_enum_case_sensitive": (
        "ENUM('Resident', 'Maintenance Staff', 'Administrator') COLLATE utf8mb4_bin",
        {"Resident": "resident", "Maintenance Staff": "maintenance_staff",
         "Administrator": "administrator"},
    ),
    "v3_lowercase_enum_missing_columns": (
        "ENUM('resident', 'maintenance_staff', 'administrator') COLLATE utf8mb4_bin",
        {"resident": "resident", "maintenance_staff": "maintenance_staff",
         "administrator": "administrator"},
    ),
    "v4_varchar_mixed_spellings": (
        "VARCHAR(20)",
        {"Resident": "resident", "RESIDENT": "resident", "maintenance staff": "maintenance_staff",
         "staff": "maintenance_staff", "Administrator": "administrator", "ADMIN": "administrator",
         "admin": "administrator", "resident": "resident"},
    ),
}


def recreate_database(name):
    conn = get_connection(use_database=False)
    try:
        with conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS `{name}`")
            cur.execute(f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def empty_db(test_db_name):
    """An empty test database. Rebuilt with the current schema afterwards."""
    recreate_database(test_db_name)
    conn = get_connection(database=test_db_name)
    yield conn
    conn.close()
    recreate_database(test_db_name)
    conn = get_connection(database=test_db_name)
    try:
        apply_schema(conn)
    finally:
        conn.close()


def query(conn, sql, args=None):
    with conn.cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchall()


def tables(conn):
    return [r["t"] for r in query(
        conn,
        "SELECT TABLE_NAME AS t FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() ORDER BY TABLE_NAME",
    )]


def role_column(conn):
    return query(
        conn,
        "SELECT COLUMN_TYPE AS type, COLLATION_NAME AS collation FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND COLUMN_NAME = 'role'",
    )[0]


def create_legacy_users(conn, role_type, stored_roles):
    with conn.cursor() as cur:
        cur.execute(LEGACY_USERS_TABLE.format(role_type=role_type))
        for i, role in enumerate(stored_roles):
            cur.execute(
                "INSERT INTO users (user_id, name, email, password_hash, role, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (f"00000000-0000-0000-0000-{i:012d}", f"Legacy {i}", f"legacy{i}@example.com",
                 hash_password(f"Password{i}!"), role, "2026-01-01 08:00:00", "2026-01-02 09:00:00"),
            )
    conn.commit()


def snapshot(conn):
    return {
        r["user_id"]: r for r in query(
            conn,
            "SELECT user_id, name, email, password_hash, CAST(role AS CHAR) AS role, created_at, "
            "updated_at FROM users",
        )
    }


def test_fresh_database_setup(empty_db):
    conn = empty_db

    first = apply_schema(conn)
    second = apply_schema(conn)

    assert tables(conn) == ALL_TABLES
    assert first == [] and second == []
    assert role_column(conn) == {
        "type": "enum('resident','maintenance_staff','administrator')", "collation": "utf8mb4_bin",
    }


@pytest.mark.parametrize("version", list(LEGACY_SCHEMAS))
def test_migration_from_older_schema_preserves_users(empty_db, version):
    conn = empty_db
    role_type, expected = LEGACY_SCHEMAS[version]
    create_legacy_users(conn, role_type, list(expected))
    before = snapshot(conn)

    first = apply_schema(conn)
    after_first = snapshot(conn)
    second = apply_schema(conn)
    after_second = snapshot(conn)

    # Every user kept, with identical id, name, email, password hash and timestamps.
    assert set(after_first) == set(before)
    for user_id, old in before.items():
        new = after_first[user_id]
        assert {k: v for k, v in new.items() if k != "role"} == {
            k: v for k, v in old.items() if k != "role"
        }
        assert new["role"] == expected[old["role"]]
        i = int(user_id[-12:])
        assert verify_password(new["password_hash"], f"Password{i}!")

    # Schema is now current: all tables, lowercase role ENUM, new columns with defaults.
    assert tables(conn) == ALL_TABLES
    assert role_column(conn)["type"] == "enum('resident','maintenance_staff','administrator')"
    assert role_column(conn)["collation"] == "utf8mb4_bin"
    extra = query(conn, "SELECT DISTINCT contact_number, unit_address, department_id, is_active FROM users")
    assert extra == [{"contact_number": None, "unit_address": None, "department_id": None, "is_active": 1}]
    assert "added fk_users_department" in first

    # Rerunning is safe: no upgrades and no data changes.
    assert second == []
    assert after_second == after_first


def full_columns(conn):
    return query(
        conn,
        "SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, COLLATION_NAME, IS_NULLABLE "
        "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() "
        "ORDER BY TABLE_NAME, ORDINAL_POSITION",
    )


def test_migration_with_unknown_role_changes_nothing(empty_db):
    conn = empty_db
    create_legacy_users(conn, "VARCHAR(20)", ["Resident", "superuser", "Janitor"])
    before = snapshot(conn)
    schema_before = full_columns(conn)

    with pytest.raises(MigrationError) as excinfo:
        apply_schema(conn)

    assert "'Janitor'" in str(excinfo.value) and "'superuser'" in str(excinfo.value)
    # Nothing at all was changed: no new tables, no altered columns, no changed rows.
    assert tables(conn) == ["users"]
    assert full_columns(conn) == schema_before
    assert snapshot(conn) == before

    # Rerunning after the bad values are fixed completes the full upgrade.
    with conn.cursor() as cur:
        cur.execute("UPDATE users SET role = 'Resident' WHERE role IN ('superuser', 'Janitor')")
    conn.commit()
    assert "added fk_users_department" in apply_schema(conn)
    assert tables(conn) == ALL_TABLES
    assert apply_schema(conn) == []
