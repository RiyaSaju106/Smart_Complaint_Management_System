# Processing & Status module

Manages a complaint after it has been assigned (SAD 3.4): maintenance staff see their assigned
complaints and move them `assigned -> in_progress -> resolved`; the resident who raised the
complaint, or an administrator, then closes it (`resolved -> closed`). Requirements: FR-012,
FR-013, FR-014, FR-020.

Flask blueprint on PyMySQL. It uses the existing `db/schema.sql` tables (`complaints`,
`assignments`, `resolutions`, `status_history`, `categories`) and adds no tables of its own.

## Files

| File | Purpose |
|---|---|
| `routes.py` | HTTP layer: login and role checks, order of checks, one transaction per request, responses, JSON error handler for database failures |
| `schema.py` | Request validation and lifecycle rules (`STATUSES`, `ALLOWED_TRANSITIONS`, size limits). No Flask or database code |
| `queries.py` | PyMySQL SQL, one small function per query. Takes a cursor, never commits |
| `__init__.py` | Exports `processing_bp` |

Tests are in `tests/processing/` (`conftest.py` fixtures, `test_processing.py`).

## Register it

In `create_app()`:

```python
from process import processing_bp

app.register_blueprint(processing_bp)
```

The module imports `app.access` (`ADMINISTRATOR`, `RESIDENT`, `error`, `role_required`) and
`db.connection.get_connection`. **Run everything from the repository root**, the folder that holds
`app/`, `db/` and `process/`. Do not run `routes.py` directly: `app` is then not importable.

## Endpoints

Prefix `/api`. Authentication is the server-side session (`session["user_id"]`,
`session["role"]`) set at login; the role is never read from the request.

| Method and path | Who | Body / query | Success |
|---|---|---|---|
| `GET /api/staff/complaints/assigned` | `maintenance_staff` | optional `?status=` | `200 {status, data: [{complaint_id, title, category, category_id, location, status, created_at}]}` |
| `PATCH /api/staff/complaints/<id>/status` | `maintenance_staff` currently assigned to the complaint | `{status, remarks?, resolution_details?}` | `200 {status, message, data: {complaint_id, status, updated_at}}` |
| `GET /api/staff/complaints/<id>` | `maintenance_staff` currently assigned to the complaint | – | `200 {status, data: {…complaint, resolution, history[]}}` (403 if not assigned, 404 if unknown) |
| `POST /api/staff/complaints/<id>/remarks` | assigned `maintenance_staff`, complaint `assigned` or `in_progress` | `{remarks}` (required, ≤500) | `201 {status, message, data: {complaint_id, status}}`; writes a `status_history` row with old = new status |
| `PATCH /api/complaints/<id>/close` | `resident` who raised it, or `administrator` | `{confirmation: true, closure_notes?}` | `200 {status, message, data: {complaint_id, status, closed_at}}` |

The list shows only complaints whose **current** assignment (`is_current = TRUE`) is the logged-in
staff member, newest first.

### Rules

- Staff can only make `assigned -> in_progress` and `in_progress -> resolved`. Anything else is
  `INVALID_STATE_TRANSITION`.
- Resolving needs non-blank `resolution_details`; a `resolutions` row is saved with it.
- Closing needs the complaint to be `resolved`, to have a `resolutions` row, and
  `confirmation` to be exactly JSON `true` (`"true"` and `1` are rejected).
- Every status change appends a `status_history` row (old status, new status, who, remarks).
  That table is append-only: the module never updates or deletes it.
- Status values are lowercase and case-sensitive: `In_Progress` is rejected, not converted.
- Limits: `remarks` and `closure_notes` 500 characters; `resolution_details` 5,000 characters.
  Blank text counts as missing.

### Order of checks (status update)

login and role (401, 403) -> body validation (400) -> complaint exists (404) -> staff is the
current assignee (403) -> transition allowed (400) -> resolution details present when resolving
(400). Authorization runs before the transition check, so staff who are not assigned always get
403.

### Errors

All errors use the project format `{"error": {"code": "...", "message": "..."}}`.

| HTTP | Code | When |
|---|---|---|
| 400 | `VALIDATION_ERROR` | bad or missing field, bad filter, missing confirmation or resolution details |
| 400 | `INVALID_STATE_TRANSITION` | transition not allowed, or closing a complaint that is not resolved |
| 401 | `UNAUTHENTICATED` | not logged in |
| 403 | `FORBIDDEN` | wrong role, not the assigned staff member, or not the owning resident |
| 404 | `NOT_FOUND` | unknown complaint id |
| 500 | `DATABASE_ERROR` | any database failure. The client gets a generic message; details go to the log |

## Design notes

- **One transaction per request.** The complaint row is locked (`SELECT ... FOR UPDATE`), then
  the resolution, history row and status change are written together and committed once. Any
  exception rolls everything back, so a half-finished resolve cannot be saved. The lock also
  stops two concurrent requests both passing the transition check.
- **Timestamps** come from MySQL (`DEFAULT` / `ON UPDATE CURRENT_TIMESTAMP`), like the rest of
  the schema. The module never writes `created_at` or `updated_at`.
- **Parameterised SQL only** (SEC-003). IDs are generated with `uuid.uuid4()` as elsewhere.

## Tests

Prerequisites are the same as `db/README.md`: MySQL running, `.env` filled in, and
`TEST_DB_NAME` set to a database that is not `DB_NAME`.

```bash
.venv/bin/python -m pytest tests/processing -v
```

The tests run against `TEST_DB_NAME` only (they refuse to run if it equals `DB_NAME`), build the
tables with the project's own `db.apply_schema`, and empty all tables before each test. They mount
the real blueprint on a minimal Flask app and go through the real `role_required` and PyMySQL
code. Only login is stood in for: a test-only route sets `session["user_id"]` and
`session["role"]`, because `/api/auth/login` is not implemented yet.

| Area | Covers |
|---|---|
| FR-012 | TC-PRC-01, 02: list, own and current assignments only, status filter, 401/403 |
| FR-013 | TC-PRC-03, 04: allowed and illegal transitions, case-sensitive statuses, 404, unassigned and reassigned staff |
| FR-014 | TC-PRC-05, 06: resolve saves the resolution; missing or blank details writes nothing; length limits |
| FR-020 | TC-PRC-07, 08: close, unresolved, missing resolution, missing confirmation |
| Closure authorization | owner resident and administrator allowed; other resident, staff and anonymous refused |
| `status_history` | full lifecycle recorded with old and new status, user and remarks; rejected requests write nothing |
| Failures | database errors return JSON without leaking details; a failure mid-request rolls back everything |

## Known gaps

- **Notifications** are raised by `app.notifications.service.notify()` after each committed status change (see `Documentation/API/notification-contract.md`). The processing module only calls it; it holds no notification logic.
- **Account status:** the module trusts the session role and does not re-check `users.is_active`.
- **Prefix:** SAD 4.3 and the STP test cases say `/api/v1/...`; the code uses `/api` to match the
  other modules. Update the documents or change `url_prefix` in `routes.py`.
- **Login:** `/api/auth/login` is a stub, so there is no end-to-end test through the real login
  yet.
- Performance and non-functional cases (TC-PERF, TC-NFR) are not covered by these tests.
