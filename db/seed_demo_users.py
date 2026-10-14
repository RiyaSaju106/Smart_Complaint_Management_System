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

# Residents must have contact details (SRS Appendix B). Placeholder values, not real data.
DEMO_RESIDENT_CONTACT = ("0000000000", "Demo Block A, Unit 101")


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
                contact_number, unit_address = (
                    DEMO_RESIDENT_CONTACT if role == "resident" else (None, None)
                )
                cur.execute("SELECT 1 FROM users WHERE email = %s", (email,))
                if cur.fetchone():
                    if role == "resident":
                        # Fill contact details only where an older run left them empty.
                        cur.execute(
                            "UPDATE users SET contact_number = %s, unit_address = %s "
                            "WHERE email = %s AND contact_number IS NULL AND unit_address IS NULL",
                            (contact_number, unit_address, email),
                        )
                        if cur.rowcount:
                            print(f"Updated {role} {email}: added demo contact details")
                    print(f"Skipped {role} {email}: already exists")
                    continue
                cur.execute(
                    "INSERT INTO users (user_id, name, email, password_hash, contact_number, "
                    "unit_address, role) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (
                        str(uuid.uuid4()),
                        name,
                        email,
                        hash_password(os.environ[password_var]),
                        contact_number,
                        unit_address,
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
