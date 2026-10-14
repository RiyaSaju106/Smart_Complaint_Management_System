"""Check that the database in .env is reachable and the demo resident can be retrieved.

Usage: python -m db.check_connection
Prints the database name and server version, then looks up DEMO_RESIDENT_EMAIL (if set) and prints
its user_id, name and role. Never prints password hashes. Exits non-zero if the connection fails or
the demo user is missing.
"""
import os
import sys

from db.connection import get_connection


def main():
    try:
        conn = get_connection()
    except Exception as exc:
        print(f"Connection FAILED: {exc}", file=sys.stderr)
        return 1
    email = os.environ.get("DEMO_RESIDENT_EMAIL", "").strip().lower()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DATABASE() AS db, VERSION() AS version")
            row = cur.fetchone()
            print(f"Connected OK. Database: {row['db']}, MySQL server version: {row['version']}")
            if not email:
                return 0
            cur.execute("SELECT user_id, name, role FROM users WHERE email = %s", (email,))
            user = cur.fetchone()
    finally:
        conn.close()
    if user is None:
        print(f"Test user {email} NOT FOUND. Run: python -m db.seed_demo_users", file=sys.stderr)
        return 1
    print(f"Test user retrieved: {email} -> user_id {user['user_id']}, name {user['name']!r}, role {user['role']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
