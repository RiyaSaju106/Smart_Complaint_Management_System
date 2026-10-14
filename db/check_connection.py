"""Check that the database in .env is reachable.

Usage: python -m db.check_connection
Prints the database name and server version; exits non-zero on failure.
"""
import sys

from db.connection import get_connection


def main():
    try:
        conn = get_connection()
    except Exception as exc:
        print(f"Connection FAILED: {exc}", file=sys.stderr)
        return 1
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DATABASE() AS db, VERSION() AS version")
            row = cur.fetchone()
    finally:
        conn.close()
    print(f"Connected OK. Database: {row['db']}, MySQL server version: {row['version']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
