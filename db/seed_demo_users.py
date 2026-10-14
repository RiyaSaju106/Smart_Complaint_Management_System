"""Create the demo resident and administrator accounts. Safe to run repeatedly.

Usage: python -m db.seed_demo_users
Reads DEMO_RESIDENT_EMAIL, DEMO_RESIDENT_PASSWORD, DEMO_ADMIN_EMAIL and
DEMO_ADMIN_PASSWORD from the environment (.env). Passwords are hashed (db.passwords,
pbkdf2:sha256) before insert; a user whose email already exists is skipped.
Never prints passwords or hashes.
"""
import os
import sys
import uuid

from db.passwords import hash_password

from db.connection import get_connection

DEMO_USERS = (
    ("Demo Resident", "resident", "DEMO_RESIDENT_EMAIL", "DEMO_RESIDENT_PASSWORD"),
    ("Demo Administrator", "administrator", "DEMO_ADMIN_EMAIL", "DEMO_ADMIN_PASSWORD"),
)


def main():
    missing = [
        var for _, _, email_var, password_var in DEMO_USERS
        for var in (email_var, password_var) if not os.environ.get(var)
    ]
    if missing:
        print(f"Missing environment variables: {', '.join(missing)}", file=sys.stderr)
        return 1

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            for name, role, email_var, password_var in DEMO_USERS:
                email = os.environ[email_var].strip().lower()
                cur.execute("SELECT 1 FROM users WHERE email = %s", (email,))
                if cur.fetchone():
                    print(f"Skipped {role} {email}: already exists")
                    continue
                cur.execute(
                    "INSERT INTO users (user_id, name, email, password_hash, role) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (
                        str(uuid.uuid4()),
                        name,
                        email,
                        hash_password(os.environ[password_var]),
                        role,
                    ),
                )
                print(f"Created {role} {email}")
        conn.commit()
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
