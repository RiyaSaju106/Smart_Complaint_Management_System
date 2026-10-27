# SCMS database

The MySQL schema for SCMS, plus scripts to set it up and seed it, and the tests that check its
relationships and constraints.

| File | Purpose |
|---|---|
| [`schema.sql`](schema.sql) | All 10 tables, keys and constraints |
| `apply_schema.py` | Applies the schema; also upgrades databases created by earlier versions |
| `check_connection.py` | Checks the connection and retrieves the demo resident |
| `seed_reference_data.py` | Predefined categories and departments |
| `seed_demo_users.py` | Demo `resident`, `administrator` and `maintenance_staff` accounts |
| `passwords.py` | Password hashing helpers (use these in Auth) |
| `connection.py` | `get_connection()` for Python code |
| `tests/db/` | pytest suite, run against `scms_test_db` only |

All commands are run from the **repository root**. Module boundaries and API contracts are in
`Documentation/API/`.

## Quick start (about 5 minutes)

### 1. Prerequisites

- MySQL 8.0.16 or newer, running (default `127.0.0.1:3306`). CHECK constraints need 8.0.16+.
- Python 3.9 or newer.

### 2. Create the databases and the app user (once, as MySQL root)

```bash
mysql -u root -p
```

```sql
CREATE DATABASE IF NOT EXISTS scms_db      CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE DATABASE IF NOT EXISTS scms_test_db CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER IF NOT EXISTS 'scms_user'@'localhost' IDENTIFIED BY '<choose-a-password>';
GRANT ALL PRIVILEGES ON scms_db.*      TO 'scms_user'@'localhost';
GRANT ALL PRIVILEGES ON scms_test_db.* TO 'scms_user'@'localhost';
```

Each developer runs this on their own machine with their own password. If you connect from another
host or from Docker, create the user as `'scms_user'@'%'` instead of `'localhost'`.

### 3. Python environment

```bash
python3 -m venv .venv
.venv/bin/pip install -r db/requirements.txt
```

### 4. Configure `.env`

```bash
cp .env.example .env
```

Then edit `.env`. It is git-ignored: **never commit it**.

| Variable | Purpose |
|---|---|
| `DB_HOST`, `DB_PORT` | MySQL host and port, e.g. `127.0.0.1`, `3306` |
| `DB_NAME` | App database: `scms_db` |
| `DB_USER`, `DB_PASSWORD` | `scms_user` and the password from step 2 |
| `TEST_DB_NAME` | Test-only database: `scms_test_db` (must differ from `DB_NAME`) |
| `DEMO_RESIDENT_EMAIL`, `DEMO_RESIDENT_PASSWORD` | Demo resident login (choose any password) |
| `DEMO_ADMIN_EMAIL`, `DEMO_ADMIN_PASSWORD` | Demo administrator login |
| `DEMO_STAFF_PASSWORD` | Optional. Password for the four demo maintenance staff (`staff.electrical@example.com`, `staff.plumbing@…`, `staff.housekeeping@…`, `staff.security@…`), one per department |

### 5. Build, seed and check

```bash
.venv/bin/python -m db.apply_schema           # create or upgrade all tables
.venv/bin/python -m db.seed_reference_data    # categories and departments
.venv/bin/python -m db.seed_demo_users        # demo resident, administrator and staff
.venv/bin/python -m db.check_connection       # connect and retrieve the demo resident
.venv/bin/python -m pytest tests/db -v        # relationship and constraint tests
```

`check_connection` should end with:

```
Test user retrieved: resident@example.com -> user_id <uuid>, name 'Demo Resident', role resident
```

Every script is safe to run again: nothing is dropped, deleted or duplicated in `scms_db`.

### Command reference

| Command | What it does |
|---|---|
| `python -m db.apply_schema [--database NAME]` | Runs `schema.sql` (`CREATE TABLE IF NOT EXISTS`), then upgrades an older `users` table: legacy role values are converted to the lowercase roles (any case, `Maintenance Staff` / `maintenance-staff`, the short forms `admin` / `staff`, stored as ENUM or VARCHAR), and missing columns and the department foreign key are added. Users, password hashes and timestamps are kept. If a role value can't be mapped (e.g. `superuser`), it changes nothing and exits 1, listing the values to fix. Prints which upgrades ran. |
| `python -m db.seed_reference_data` | Creates any missing categories (Electrical, Water Supply, Cleaning, Security, Other) and departments (Electrical, Plumbing, Housekeeping, Security). "Plumbing" is not a predefined category because TC-ASG-03 creates it. |
| `python -m db.seed_demo_users` | Creates the demo resident and administrator with hashed passwords, generated UUIDs and placeholder contact details for the resident, plus one maintenance staff account per department when `DEMO_STAFF_PASSWORD` is set. Skips existing emails. Never prints passwords or hashes. |
| `python -m db.check_connection` | Prints database and server version, then retrieves `DEMO_RESIDENT_EMAIL`. Exits non-zero on failure. |
| `python -m pytest tests/db -v` | **Drops and recreates `scms_test_db`**, builds the schema from scratch, and empties all tables before each test. Refuses to run against `scms_db`. |

## Schema

### Conventions

- Lowercase plural table names. **All IDs are `CHAR(36)` UUID strings**, generated in Python (`str(uuid.uuid4())`).
- `utf8mb4`, InnoDB, strict SQL mode (MySQL 8 default).
- Enum values are lowercase and **case-sensitive** (`COLLATE utf8mb4_bin`): a wrong-case value such as `Resident` or `In Progress` is rejected, not converted.
- Foreign keys are `RESTRICT`: a row that others depend on cannot be deleted. Users and categories are deactivated with `is_active = FALSE` instead.

### Role and status values

| Roles (stored / API) | UI display | | Statuses (stored / API) | UI display |
|---|---|---|---|---|
| `resident` | Resident | | `submitted` | Submitted |
| `maintenance_staff` | Maintenance Staff | | `assigned` | Assigned |
| `administrator` | Administrator | | `in_progress` | In Progress |
| | | | `resolved` | Resolved |
| | | | `closed` | Closed |

The demo uses only `resident` and `administrator`; `maintenance_staff` is fully supported.

### Tables and relationships

```
departments 1───* users (maintenance staff)                 categories 1───* complaints
users (resident) 1───* complaints 1───* attachments
                       complaints 1───* assignments  *───1 departments
                                        assignments  *───1 users (assigned_by, staff_id)
                       complaints 1───* status_history *───1 users (changed_by)
                       complaints 1───0..1 resolutions *───1 users (resolved_by)
                       complaints 1───0..1 feedback    *───1 users (resident)
                       complaints 1───* notifications  *───1 users (recipient)
```

| Table | Key columns | Constraints worth knowing |
|---|---|---|
| `users` | `user_id`, `name`, `email`, `password_hash`, `contact_number`, `unit_address`, `role`, `department_id`, `is_active`, `created_at`, `updated_at` | Unique `email` (case-insensitive). `contact_number` and `unit_address` are NULL-able in the database, but **Auth must require them for residents** (SRS Appendix B). `department_id` is for maintenance staff. |
| `departments` | `department_id`, `name`, `description` | Unique `name` |
| `categories` | `category_id`, `name`, `description`, `is_active` | Unique `name` (case-insensitive). Cannot be deleted while complaints use it. |
| `complaints` | `complaint_id`, `resident_id`, `title`, `category_id`, `description`, `location`, `status`, `created_at`, `updated_at` | `status` defaults to `submitted`. `description` ≤ 1000 characters. Unknown `resident_id` or `category_id` is rejected. |
| `attachments` | `attachment_id`, `complaint_id`, `file_path`, `file_type`, `file_size_kb`, `uploaded_at` | |
| `assignments` | `assignment_id`, `complaint_id`, `assigned_by`, `department_id`, `staff_id`, `assigned_at`, `is_current` | **At most one current assignment per complaint.** To reassign, set the old row's `is_current = FALSE` and insert a new row; history is kept. |
| `status_history` | `history_id`, `complaint_id`, `old_status`, `new_status`, `changed_by`, `remarks`, `changed_at` | Append-only by contract: never UPDATE or DELETE. `old_status` is NULL for the first `submitted` row. A complaint with history cannot be deleted. |
| `resolutions` | `resolution_id`, `complaint_id`, `resolved_by`, `details`, `resolved_at` | One per complaint |
| `notifications` | `notification_id`, `user_id`, `complaint_id`, `event`, `message`, `is_read`, `created_at` | `event` uses the Notification contract names, e.g. `COMPLAINT_ASSIGNED` |
| `feedback` | `feedback_id`, `complaint_id`, `resident_id`, `rating`, `comments`, `submitted_at` | One per complaint; `rating` 1–5 |

Full column types are in [`schema.sql`](schema.sql).

### Differences from the SAD data dictionary

| Change | Reason |
|---|---|
| Role and status values are lowercase | Agreed API convention |
| `users.contact_number` and `unit_address` NULL-able (SAD: NOT NULL) | Staff and administrator accounts may not have them; Auth enforces them for residents |
| Added `users.is_active` | Admin/Reporting deactivates accounts instead of deleting them (PR #13) |
| Added `notifications.event` | Notification contract stores the lifecycle event (PR #13) |
| `status_history.old_status` / `new_status` are ENUMs (SAD: VARCHAR(20)) | Only valid statuses can be recorded |
| `assignments.current_complaint_id` (generated column) | Lets the database enforce one current assignment per complaint |

## Using it from the app

```python
from db.connection import get_connection            # reads .env; rows come back as dicts
from db.passwords import hash_password, verify_password

password_hash = hash_password(plain_password)          # store this in users.password_hash
verify_password(row["password_hash"], plain_password)  # at login -> True/False
```

Always use `db.passwords`. Werkzeug's default method (scrypt) fails on Pythons built without
`hashlib.scrypt`, such as the macOS system Python 3.9
(`AttributeError: module 'hashlib' has no attribute 'scrypt'`), and a scrypt hash cannot be checked
on such a machine.

Always pass values as query parameters (`cur.execute("... WHERE email = %s", (email,))`), never by
building SQL strings (SEC-003).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Access denied for user 'scms_user'@'localhost'` | `DB_PASSWORD` in `.env` doesn't match step 2, or the user wasn't created |
| `Unknown database 'scms_db'` | Run the step 2 SQL |
| `Test user ... NOT FOUND` | Run `python -m db.seed_demo_users` |
| `Data truncated for column 'role'` | Role isn't one of the lowercase values (check the case) |
| `Cannot add or update a child row: a foreign key constraint fails` | The referenced user, category, department or complaint doesn't exist |
