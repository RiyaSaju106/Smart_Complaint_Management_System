# SCMS: Admin dashboard and reports API

**Issue:** #34 · **Requirements:** FR-024 (dashboard counts and statuses), FR-025 (basic reports) · SRS Appendix B "Report Requirements"
**Code:** `app/reports/` (`routes.py`, `schema.py`, `queries.py`) · **Pages:** `/admin` (figure tiles), `/admin/reports`

Based on the dashboard and report sections of the earlier draft Admin/Reporting contract (PR #13, not merged), aligned with the shared conventions in `module-boundaries.md`: lowercase status values, UUIDs, and the standard error body.

## Conventions

- **Administrators only.** Anyone else gets `403 FORBIDDEN`; not logged in gets `401 UNAUTHENTICATED`. The role comes from the server-side session, never the request.
- **Read-only.** Every figure is counted live from MySQL when requested, so it always matches the database. Nothing is cached or written.
- **Optional date range** on every endpoint: `from`, `to` as `YYYY-MM-DD`, inclusive, applied to the complaint's `created_at`. Either may be given alone. Empty values count as not given.
- **Department and staff figures use each complaint's current assignment** (`is_current = TRUE`), never earlier ones.
- **Open / pending** means `submitted`, `assigned` or `in_progress` (not yet resolved or closed).
- Errors: `{"error": {"code": "...", "message": "..."}}`. Bad parameters → `400 INVALID_FILTER`; database failure → `500 DATABASE_ERROR` (details logged, never returned).

The earlier `GET /api/admin/dashboard` (#16) is unchanged. It is the role-check endpoint used by the login and role tests.

## GET /api/admin/reports/summary (FR-024)

Dashboard figures.

```json
200
{
  "period": {"from": null, "to": null},
  "total": 7,
  "by_status": {"submitted": 2, "assigned": 2, "in_progress": 1, "resolved": 1, "closed": 1},
  "pending": 5,
  "unassigned": 2,
  "feedback": {"count": 2, "average_rating": 4.5}
}
```

- `by_status` always has all five statuses (0 when none).
- `pending` = open complaints. `unassigned` = open complaints with no current assignment.
- `average_rating` is `null` when there is no feedback in the range (two decimal places otherwise).

## GET /api/admin/reports?type=… (FR-025)

| `type` | Rows | Ordering |
|---|---|---|
| `status` | `{key, label, count, share}` for all five statuses | lifecycle order |
| `category` | `{category_id, label, is_active, count, share}` for every category, including inactive and empty ones | most complaints first, then name |
| `department` | `{department_id, label, count, open, share}` for every department, then a `"Not assigned"` row with `department_id: null` | most complaints first, then name; "Not assigned" last |
| `period` | `{period, count, share}`; extra parameter `group=month` (default, `YYYY-MM`) or `group=day` (`YYYY-MM-DD`). Only periods that have complaints. | oldest first |
| `pending` | `{complaint_id, title, status, category, department, staff, created_at, age_days}` for open complaints, at most 100 (`limit`) | oldest first |
| `workload` | `{staff: {user_id, name, is_active}, department, assigned, in_progress, open, resolved, closed}` for every maintenance staff member | most open first, then name |

`share` is the row's percentage of `total`, to one decimal place.

`total` is the number of complaints the report covers. For `pending` it is the full number of open complaints, even beyond the 100 listed. For `workload` it is the open complaints held by staff.

```json
GET /api/admin/reports?type=department&from=2026-10-01&to=2026-10-31
200
{
  "type": "department",
  "period": {"from": "2026-10-01", "to": "2026-10-31"},
  "total": 5,
  "rows": [
    {"department_id": "…", "label": "Plumbing", "count": 3, "open": 3, "share": 60.0},
    {"department_id": "…", "label": "Electrical", "count": 2, "open": 0, "share": 40.0},
    {"department_id": "…", "label": "Housekeeping", "count": 0, "open": 0, "share": 0.0},
    {"department_id": null, "label": "Not assigned", "count": 0, "open": 0, "share": 0.0}
  ]
}
```

`400 INVALID_FILTER` when: `type` is missing or unknown (values are lowercase), a date is not `YYYY-MM-DD`, `from` is after `to`, or `group` is not `day`/`month` on a period report.

## Requirement coverage

| SRS Appendix B report | Where |
|---|---|
| Total complaints | `summary.total`; every report's `total` |
| Complaints by status | `summary.by_status`; `type=status` |
| Complaints by category | `type=category` |
| Complaints by date/period | `type=period` (`group=month|day`); `from`/`to` on every endpoint |
| Pending and unresolved complaints | `summary.pending`, `summary.unassigned`; `type=pending` |
| Basic staff/department workload | `type=workload`; `type=department` (`open`) |

Tests: `tests/categories/test_reports.py` builds a fixed set of complaints and checks every figure against known values and direct SQL counts. It also checks that the reports are read-only, admin-only and validate their parameters. Page tests are in `tests/test_ui_pages.py`.
