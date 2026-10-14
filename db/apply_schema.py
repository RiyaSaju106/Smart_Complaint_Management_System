"""Apply db/schema.sql to the database. Safe to run repeatedly.

Usage: python -m db.apply_schema [--database NAME]
Defaults to DB_NAME from .env.

After creating any missing tables, it upgrades a users table created by an earlier version of the
schema (capitalized roles, missing columns). Every upgrade step checks first, keeps all rows, and
does nothing when the table is already current.
"""
import argparse
import sys
from pathlib import Path

from db.connection import get_connection

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

ROLE_ENUM = "ENUM('resident', 'maintenance_staff', 'administrator') COLLATE utf8mb4_bin NOT NULL"
OLD_ROLES = {
    "Resident": "resident",
    "Maintenance Staff": "maintenance_staff",
    "Administrator": "administrator",
}

# Columns added to users after the first version, in table order.
USERS_NEW_COLUMNS = (
    ("contact_number", "VARCHAR(15) NULL AFTER password_hash"),
    ("unit_address", "VARCHAR(150) NULL AFTER contact_number"),
    ("department_id", "CHAR(36) NULL AFTER role"),
    ("is_active", "BOOLEAN NOT NULL DEFAULT TRUE AFTER department_id"),
)


def schema_statements():
    lines = [
        line for line in SCHEMA_PATH.read_text().splitlines()
        if not line.strip().startswith("--")
    ]
    return [stmt.strip() for stmt in "\n".join(lines).split(";") if stmt.strip()]


def _column_type(cur, table, column):
    cur.execute(
        "SELECT COLUMN_TYPE AS t FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s",
        (table, column),
    )
    row = cur.fetchone()
    return row["t"] if row else None


def _constraint_exists(cur, table, name):
    cur.execute(
        "SELECT 1 FROM information_schema.TABLE_CONSTRAINTS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND CONSTRAINT_NAME = %s",
        (table, name),
    )
    return cur.fetchone() is not None


def upgrade_users(cur):
    """Bring an older users table up to the current schema. Returns the steps applied."""
    applied = []

    if "'Resident'" in (_column_type(cur, "users", "role") or ""):
        old_and_new = ", ".join(f"'{v}'" for v in [*OLD_ROLES.values(), *OLD_ROLES])
        cur.execute(f"ALTER TABLE users MODIFY role ENUM({old_and_new}) COLLATE utf8mb4_bin NOT NULL")
        for old, new in OLD_ROLES.items():
            # updated_at is kept: this is a format change, not a user edit.
            cur.execute(
                "UPDATE users SET role = %s, updated_at = updated_at WHERE role = %s", (new, old)
            )
        cur.execute(f"ALTER TABLE users MODIFY role {ROLE_ENUM}")
        applied.append("converted roles to lowercase")

    for column, definition in USERS_NEW_COLUMNS:
        if _column_type(cur, "users", column) is None:
            cur.execute(f"ALTER TABLE users ADD COLUMN {column} {definition}")
            applied.append(f"added users.{column}")

    if not _constraint_exists(cur, "users", "fk_users_department"):
        cur.execute(
            "ALTER TABLE users ADD CONSTRAINT fk_users_department "
            "FOREIGN KEY (department_id) REFERENCES departments (department_id)"
        )
        applied.append("added fk_users_department")

    return applied


def apply_schema(conn):
    with conn.cursor() as cur:
        for statement in schema_statements():
            cur.execute(statement)
        applied = upgrade_users(cur)
    conn.commit()
    return applied


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", help="database to apply to (default: DB_NAME)")
    args = parser.parse_args()

    conn = get_connection(database=args.database)
    try:
        applied = apply_schema(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT DATABASE() AS db")
            db_name = cur.fetchone()["db"]
            cur.execute(
                "SELECT TABLE_NAME AS t FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = DATABASE() ORDER BY TABLE_NAME"
            )
            tables = [row["t"] for row in cur.fetchall()]
            cur.execute("SELECT COUNT(*) AS n FROM users")
            user_count = cur.fetchone()["n"]
    finally:
        conn.close()
    print(f"Schema applied to {db_name}. {len(tables)} tables: {', '.join(tables)}.")
    print(f"Upgrades: {'; '.join(applied) if applied else 'none needed'}. users: {user_count} row(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
