"""Apply db/schema.sql to the database. Safe to run repeatedly.

Usage: python -m db.apply_schema [--database NAME]
Defaults to DB_NAME from .env.

After creating any missing tables, it upgrades a users table created by an earlier version of the
schema: legacy role values (any case, spaces or the short forms admin/staff, stored as ENUM or
VARCHAR) become the lowercase roles, and missing columns are added. Every step checks first, keeps
all rows, and does nothing when the table is already current. If a role value cannot be mapped,
nothing is changed and the command fails with the values it could not map.
"""
import argparse
import re
import sys
from pathlib import Path

from db.connection import get_connection

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

ROLES = ("resident", "maintenance_staff", "administrator")
ROLE_COLUMN_TYPE = "enum('resident','maintenance_staff','administrator')"
ROLE_ENUM = "ENUM('resident', 'maintenance_staff', 'administrator') COLLATE utf8mb4_bin NOT NULL"

# Legacy spellings, after lower-casing and turning spaces/hyphens into underscores.
# Covers 'Resident', 'Maintenance Staff', 'Administrator' (earlier schema), any upper/lower case,
# and the short forms 'admin' and 'staff' used in early API drafts.
ROLE_ALIASES = {
    **{role: role for role in ROLES},
    "admin": "administrator",
    "staff": "maintenance_staff",
    "maintenance": "maintenance_staff",
    "maintenancestaff": "maintenance_staff",
}


class MigrationError(Exception):
    pass


def canonical_role(value):
    """Return the lowercase role for a legacy role value, or None if it is not recognised."""
    if value is None:
        return None
    return ROLE_ALIASES.get(re.sub(r"[\s\-]+", "_", value.strip().lower()))

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


def _role_column_is_current(cur):
    cur.execute(
        "SELECT COLUMN_TYPE AS t, COLLATION_NAME AS c, IS_NULLABLE AS n FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND COLUMN_NAME = 'role'"
    )
    row = cur.fetchone()
    return (row["t"], row["c"], row["n"]) == (ROLE_COLUMN_TYPE, "utf8mb4_bin", "NO")


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

    if not _role_column_is_current(cur):
        # Read every distinct stored value exactly (binary), so 'Admin' and 'admin' are both seen.
        cur.execute(
            "SELECT DISTINCT CONVERT(role USING utf8mb4) COLLATE utf8mb4_bin AS r FROM users"
        )
        mapping = {row["r"]: canonical_role(row["r"]) for row in cur.fetchall()}
        unknown = sorted(repr(old) for old, new in mapping.items() if new is None)
        if unknown:
            raise MigrationError(
                f"users.role has values that are not a known role: {', '.join(unknown)}. "
                "Nothing was changed. Fix those rows, then run this again."
            )
        # Widen to text first, so old and new values can coexist while converting.
        cur.execute(
            "ALTER TABLE users MODIFY role VARCHAR(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL"
        )
        converted = 0
        for old, new in mapping.items():
            if old != new:
                # updated_at is kept: this is a format change, not a user edit.
                cur.execute(
                    "UPDATE users SET role = %s, updated_at = updated_at WHERE role = %s", (new, old)
                )
                converted += cur.rowcount
        cur.execute(f"ALTER TABLE users MODIFY role {ROLE_ENUM}")
        applied.append(f"converted users.role to lowercase ENUM ({converted} row(s) changed)")

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
        try:
            applied = apply_schema(conn)
        except MigrationError as exc:
            print(f"Schema upgrade FAILED: {exc}", file=sys.stderr)
            return 1
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
