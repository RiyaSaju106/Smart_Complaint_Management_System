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
| `pages.py` | Browser pages for staff (HTML shells only; data and writes go through the API) |
| `templates/`, `static/` | Page templates, JS and CSS, served by the `processing_pages` blueprint |
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

## Staff pages (browser)

Registered automatically by `process/routes.py` when `processing_bp` is registered; no change to `create_app()` is needed.

| Page | Who | What it does |
|---|---|---|
| `GET /staff/complaints` | `maintenance_staff` | Dashboard of complaints currently assigned to you, with a status filter |
| `GET /staff/complaints/<id>` | `maintenance_staff` | Details, resolution, history, status button (shown only for transitions in `schema.ALLOWED_TRANSITIONS`), resolution details (required to resolve), optional remarks, and a stand-alone "Add remark" form |

Signed-out visitors are redirected to `/login`; other roles to `/home`. The pages never decide
access: every read and write goes through the `/api/staff/...` endpoints below, so another staff
member's complaint returns 403 (shown as a message, with no data or controls) and a change is only
shown as done after the server has saved it and the page has re-read the complaint.

There is no link to the dashboard on `/staff` yet (that template is outside this module); until one
is added, staff open `/staff/complaints` directly.

## Endpoints

Prefix `/api`. Authentication is the server-side session (`session["user_id"]`,
`session["role"]`) set at login; the role is never read from the request.

| Method and path | Who | Body / query | Success |
|---|---|---|---|
| `GET /api/staff/complaints/assigned` | `maintenance_staff` | optional `?status=` | `200 {status, data: [{complaint_id, title, category, category_id, location, status, created_at}]}` |
| `PATCH /api/staff/complaints/<id>/status` | `maintenance_staff` currently assigned to the complaint | `{status, remarks?, resolution_details?}` | `200 {status, message, data: {complaint_id, status, updated_at}}` |
| `GET /api/staff/complaints/<id>` | `maintenance_staff` currently assigned to the complaint | – | `200 {status, data: {…complaint, resolution, history[]}}` (403 if not assigned, 404 if unknown) |
| `POST /api/staff/complaints/<id>/remarks` | assigned `maintenance_staff`, complaint `assigned` or `in_progress` | `{remarks}` (required, ≤500) | `201 {status, message, data: {complaint_id, status}}`; writes a `status_history` row with old = new status |
| `GET /api/complaints/<id>/status` | resident (owner), `maintenance_staff` (current assignee), `administrator` (all) | – | `200 {status, data: {complaint_id, status, updated_at}}` |
| `GET /api/complaints/<id>/history` | same scoping | – | `200 {status, data: {complaint_id, history: [{old_status, new_status, changed_by, remarks, changed_at}]}}`, oldest first |
| `PATCH /api/complaints/<id>/close` | `resident` who raised it, or `administrator` | `{confirmation: true, closure_notes?}` | `200 {status, message, data: {complaint_id, status, closed_at}}` |

The list shows only complaints whose **current** assignment (`is_current = TRUE`) is the logged-in
staff member, newest first.

### Tracking (FR-015, FR-016, SEC-002)

Order of checks: login (401) -> role is resident, staff or administrator (403) -> complaint exists
(404) -> complaint is in the caller's scope (403). The 403 message is fixed and contains nothing
about the complaint. There is no route to add, change or delete history; the history path is GET
only.

History order: `changed_at` has one-second resolution, so rows from the same second are ordered by
lifecycle position (the transition into a status before remarks recorded while in it).

### Rules

- Staff can only make `assigned -> in_progress` and `in_progress -> resolved`. Anything else is
  `INVALID_STATE_TRANSITION`.
- Resolving needs non-blank `resolution_details`; a `resolutions` row is saved with it.
- Closing needs the complaint to be `resolved`, to have a `resolutions` row, and
  `confirmation` to be exactly JSON `true` (`"true"` and `1` are rejected).
- Every status change, remark and closure is written with the shared
  `app.tracking.service.record_status_change(cur, ...)` inside the request's transaction. This
  module has no history writer of its own and only reads `status_history`.
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
| FR-015, FR-016 | TC-TRK-01..04 (`test_tracking.py`): status and history per role, 403/404/401, history order (including same-second rows), read-only path, one shared transaction for all callers |
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