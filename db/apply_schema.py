"""Apply db/schema.sql to the database. Safe to run repeatedly.

Usage: python -m db.apply_schema [--database NAME]
Defaults to DB_NAME from .env.
"""
import argparse
import sys
from pathlib import Path

from db.connection import get_connection

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def schema_statements():
    lines = [
        line for line in SCHEMA_PATH.read_text().splitlines()
        if not line.strip().startswith("--")
    ]
    return [stmt.strip() for stmt in "\n".join(lines).split(";") if stmt.strip()]


def apply_schema(conn):
    with conn.cursor() as cur:
        for statement in schema_statements():
            cur.execute(statement)
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", help="database to apply to (default: DB_NAME)")
    args = parser.parse_args()

    conn = get_connection(database=args.database)
    try:
        apply_schema(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT DATABASE() AS db")
            db_name = cur.fetchone()["db"]
            cur.execute("SELECT COUNT(*) AS n FROM users")
            count = cur.fetchone()["n"]
    finally:
        conn.close()
    print(f"Schema applied to {db_name}. users table present, {count} row(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
