# SCMS database: `users` table

This folder holds the database foundation for SCMS authentication: the `users` table schema,
a connection check, a script that applies the schema, and a script that seeds demo accounts.
Tests live in `tests/db/`.

All commands below are run from the **repository root**.

## 1. Prerequisites

- MySQL 8 server running and reachable (default `127.0.0.1:3306`).
- Python 3.9+.

## 2. Create the databases and the app user (once, as MySQL root)

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

If you connect over TCP from a host other than this machine (or from Docker), create the user for
`'scms_user'@'%'` instead of `'localhost'`.

## 3. Python environment

```bash
python3 -m venv .venv
.venv/bin/pip install -r db/requirements.txt
```

Use `.venv/bin/python` below, or run `source .venv/bin/activate` and drop the `.venv/bin/` prefix.

## 4. Configure `.env`

```bash
cp .env.example .env
```

Then edit `.env`. It is git-ignored: **never commit it**.

| Variable | Purpose |
|---|---|
| `DB_HOST` | MySQL host, e.g. `127.0.0.1` |
| `DB_PORT` | MySQL port, e.g. `3306` |
| `DB_NAME` | App database: `scms_db` |
| `DB_USER` | App MySQL user: `scms_user` |
| `DB_PASSWORD` | Password for `DB_USER` |
| `TEST_DB_NAME` | Test-only database: `scms_test_db` (must differ from `DB_NAME`) |
| `DEMO_RESIDENT_EMAIL` / `DEMO_RESIDENT_PASSWORD` | Demo Resident login |
| `DEMO_ADMIN_EMAIL` / `DEMO_ADMIN_PASSWORD` | Demo Administrator login |

## 5. Commands

| Step | Command | Notes |
|---|---|---|
| Check connection | `.venv/bin/python -m db.check_connection` | Prints database name and server version; exits non-zero on failure. |
| Apply schema | `.venv/bin/python -m db.apply_schema` | Safe to rerun: `CREATE TABLE IF NOT EXISTS` plus an idempotent `ALTER` on `role`. Never drops tables or deletes rows. `--database NAME` targets another database. |
| Seed demo users | `.venv/bin/python -m db.seed_demo_users` | Creates one Resident and one Administrator. Skips emails that already exist. Never prints passwords or hashes. |
| Run tests | `.venv/bin/python -m pytest tests/db -v` | Uses `scms_test_db` only. It creates the database if missing and empties `users` before each test. Refuses to run against `scms_db`. |

## 6. `users` table contract

Defined in [`schema.sql`](schema.sql). Charset `utf8mb4`, InnoDB.

| Column | Type | Rules |
|---|---|---|
| `user_id` | `CHAR(36)` | Primary key. UUID string generated **in application code** (`str(uuid.uuid4())`), not by MySQL. |
| `name` | `VARCHAR(100)` | NOT NULL |
| `email` | `VARCHAR(100)` | NOT NULL, **UNIQUE**. The collation is case-insensitive, so `A@x.com` and `a@x.com` collide. Store emails lower-cased and trimmed. |
| `password_hash` | `VARCHAR(255)` | NOT NULL. Never plaintext (SEC-001). |
| `role` | `ENUM('Resident','Maintenance Staff','Administrator')` | NOT NULL. Exact spelling and case are a shared contract. |
| `created_at` | `DATETIME` | NOT NULL, defaults to insert time. |
| `updated_at` | `DATETIME` | NOT NULL, updates automatically on every row change. |

### Roles

- The ENUM supports all three roles: `Resident`, `Maintenance Staff`, `Administrator`.
- **The demo uses only `Resident` and `Administrator`.** `Maintenance Staff` stays in the ENUM so the
  final design can support it without a schema change.
- Roles are **case-sensitive** (`role` uses `COLLATE utf8mb4_bin`). An unknown or wrong-case role (e.g. lowercase `resident`) is rejected with an error. It is not silently converted. This relies on strict SQL mode, the MySQL 8 default.

### Password hashing

Use the helpers in [`passwords.py`](passwords.py). They wrap Werkzeug with the method pinned to
`pbkdf2:sha256`:

```python
from db.passwords import hash_password, verify_password

password_hash = hash_password(plain_password)           # store this
verify_password(row["password_hash"], plain_password)   # at login -> True/False
```

Do not call `generate_password_hash` with Werkzeug's default method. The default is scrypt, which
fails on Pythons built without `hashlib.scrypt` (for example the macOS system Python 3.9:
`AttributeError: module 'hashlib' has no attribute 'scrypt'`). A scrypt hash created on one machine
also cannot be verified on a machine that lacks scrypt.

### Connecting from Python

```python
from db.connection import get_connection   # reads .env

conn = get_connection()   # PyMySQL connection to DB_NAME; rows come back as dicts
```

### Note for Riya: draft API contract mismatch

`Documentation/API/auth-user-contract.md` (branch `riya-day1-setup`) shows `"id": 1` and
`"role": "resident"` in its example responses. The database uses a **UUID string** in `user_id` and the
role strings **`Resident`** / **`Administrator`**. Either update the API examples, or map the values
explicitly in the service layer.
