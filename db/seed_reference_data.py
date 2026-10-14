"""Create the predefined complaint categories and departments. Safe to run repeatedly.

Usage: python -m db.seed_reference_data
A row whose name already exists is skipped. Administrators can edit or deactivate these later
(FR-010). "Plumbing" is deliberately not a predefined category: test case TC-ASG-03 creates it.
"""
import sys
import uuid

from db.connection import get_connection

CATEGORIES = (
    ("Electrical", "Power, lighting, sockets and wiring"),
    ("Water Supply", "Leaks, low pressure and drainage"),
    ("Cleaning", "Common area cleanliness and waste"),
    ("Security", "Gates, locks and access"),
    ("Other", "Anything not covered by another category"),
)

DEPARTMENTS = (
    ("Electrical", "Electrical maintenance team"),
    ("Plumbing", "Plumbing and water supply team"),
    ("Housekeeping", "Cleaning and waste management team"),
    ("Security", "Security and access team"),
)


def seed(cur, table, id_column, rows):
    for name, description in rows:
        cur.execute(f"SELECT 1 FROM {table} WHERE name = %s", (name,))
        if cur.fetchone():
            print(f"Skipped {table} {name}: already exists")
            continue
        cur.execute(
            f"INSERT INTO {table} ({id_column}, name, description) VALUES (%s, %s, %s)",
            (str(uuid.uuid4()), name, description),
        )
        print(f"Created {table} {name}")


def main():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            seed(cur, "categories", "category_id", CATEGORIES)
            seed(cur, "departments", "department_id", DEPARTMENTS)
        conn.commit()
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
