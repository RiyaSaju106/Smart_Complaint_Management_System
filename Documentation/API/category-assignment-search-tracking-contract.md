# SCMS: Category/Assignment and Search/Tracking API contracts

**Owner:** Rohit · **Requirements:** FR-009, FR-010, FR-011, FR-015, FR-016, FR-017, FR-018 · **Issue:** #11
**Sources:** Rohit's SAD (3.4, 4.3) and STP (13.1–13.3), SRS business rules, `db/schema.sql`.

## 1. Module boundaries

| Module | Owns | Does not own | Requirements |
|---|---|---|---|
| Category/Assignment | Predefined categories; admin create, edit, deactivate and delete of categories; departments and their staff lists; assigning and reassigning a complaint to a department or staff member; the `submitted` → `assigned` transition on first assignment | Creating complaints (Complaint module); staff status updates, resolution and closure (Processing/Status module); sending notifications (Notification module) | FR-009, FR-010, FR-011 |
| Search/Tracking | Current status of a complaint; reading the status/action history; search by Complaint ID, title or keyword; filtering by category, status, department and date; the shared `record_status_change` helper that every module uses to write history | Changing complaint data; deciding which status transitions are allowed (Processing/Status module) | FR-015, FR-016, FR-017, FR-018 |

### Tables

| Table | Written by | Read by |
|---|---|---|
| `categories` | Category/Assignment | Complaint, Search/Tracking, Admin/Reporting |
| `departments` | Category/Assignment (seeded; admin-managed) | Admin/Reporting, Processing/Status |
| `assignments` | Category/Assignment | Processing/Status (staff visibility), Search/Tracking (department filter), Notification, Admin/Reporting |
| `status_history` | Every module that changes status, **only** through `record_status_change` (append-only) | Search/Tracking, Admin/Reporting |
| `complaints.status` | Category/Assignment (`submitted` → `assigned` only), Processing/Status (the rest) | Everyone |

### Interfaces offered to other modules (service layer, Python)

| Function | Used by | Behaviour |
|---|---|---|
| `get_active_category(category_id)` | Complaint (Riya) on `POST /api/complaints` | Returns the category, or `None` if it does not exist or is inactive. The caller returns **400** (see 4.1). |
| `get_current_assignment(complaint_id)` | Processing/Status (Ritu), Notification (Rohan) | Returns `department_id`, `staff_id`, `assigned_at`, or `None`. |
| `record_status_change(complaint_id, old_status, new_status, changed_by, remarks=None)` | Complaint (initial `submitted` row), Category/Assignment, Processing/Status | Inserts one `status_history` row in the caller's transaction. Never updates or deletes rows. |

### Interfaces used from other modules

| Function | From | Used for |
|---|---|---|
| Current user and role (`user_id`, `role`) | Auth/User (Riya) | Every request; 401 when missing |
| `notify(event, complaint_id, recipient_ids)` | Notification (Rohan) | Raising `COMPLAINT_ASSIGNED` after an assignment |

## 2. Conventions

These match `db/schema.sql` and the team conventions in `module-boundaries.md`.

- Base path `/api`. JSON in and out. All endpoints require an authenticated session and return **401** without one.
- **IDs are UUID strings** (`"5f0c…-…"`), never integers.
- **Roles:** `resident`, `maintenance_staff`, `administrator`. **Statuses:** `submitted`, `assigned`, `in_progress`, `resolved`, `closed`. Lowercase in the database and the API; the UI shows display names.
- Timestamps: ISO 8601 strings, e.g. `"2026-10-14T10:00:00"`.
- Errors: `{"error": {"code": "SOME_CODE", "message": "Human-readable text"}}`, the same format as the Auth contract.

## 3. Category/Assignment endpoints

### 3.1 List categories (FR-009)

`GET /api/categories`: any authenticated role.

Returns active categories, sorted by name. Administrators may pass `?include_inactive=true`.

```json
200
{
  "items": [
    {"category_id": "0b6e…", "name": "Electrical", "description": "Power, lighting, sockets and wiring", "is_active": true}
  ]
}
```

Errors: 401.

### 3.2 Create a category (FR-010)

`POST /api/categories`: `administrator` only.

```json
{"name": "Plumbing", "description": "Pipes and fittings"}
```

`201` → `{"category_id": "…", "name": "Plumbing", "description": "Pipes and fittings", "is_active": true}`

Errors:
- `400 VALIDATION_ERROR`: name missing, blank, or more than 100 characters
- `403 FORBIDDEN`: caller is not an administrator
- `409 DUPLICATE_CATEGORY`: the name already exists (case-insensitive)

### 3.3 Update or deactivate a category (FR-010)

`PUT /api/categories/{category_id}`: `administrator` only.

Body: `name`, `description`, `is_active` (all required). `is_active: false` hides the category from new complaints but keeps it on existing ones.

`200` → the updated category.

Errors: 400, 403, `404 NOT_FOUND`, `409 DUPLICATE_CATEGORY`.

### 3.4 Delete a category (FR-010)

`DELETE /api/categories/{category_id}`: `administrator` only.

`204` if no complaint uses the category.

Errors: 403, 404, `409 CATEGORY_IN_USE` when complaints reference it (the database foreign key blocks the delete; deactivate it instead).

### 3.5 List departments

`GET /api/departments`: `administrator` only.

`200` → `{"items": [{"department_id": "…", "name": "Plumbing", "description": "…"}]}`

Errors: 401, 403.

### 3.6 List a department's staff

`GET /api/departments/{department_id}/staff`: `administrator` only.

Returns active `maintenance_staff` users whose `department_id` matches.

`200` → `{"items": [{"user_id": "…", "name": "Asha K"}]}`

Errors: 401, 403, 404.

### 3.7 Assign or reassign a complaint (FR-011)

`POST /api/complaints/{complaint_id}/assignment`: `administrator` only.

```json
{"department_id": "…", "staff_id": "…"}
```

`staff_id` is optional. If given, it must be an active `maintenance_staff` user in that department.

In one transaction:
1. Mark the current assignment row (if any) `is_current = false`; insert the new row with `is_current = true`. Earlier rows are kept.
2. If the status is `submitted`, change it to `assigned` and call `record_status_change(…, "submitted", "assigned", admin_id)`. Reassigning an `assigned` or `in_progress` complaint does not change its status.
3. After commit, call `notify("COMPLAINT_ASSIGNED", complaint_id, [resident_id, staff_id])`.

```json
200
{
  "complaint_id": "…",
  "status": "assigned",
  "department_id": "…",
  "staff_id": "…",
  "assigned_at": "2026-10-14T10:00:00"
}
```

Errors:
- `400 VALIDATION_ERROR`: `department_id` missing or unknown; `staff_id` unknown, inactive, not `maintenance_staff`, or not in the department
- `403 FORBIDDEN`: caller is not an administrator; status unchanged
- `404 NOT_FOUND`: complaint does not exist
- `409 INVALID_STATE`: complaint is `resolved` or `closed`; no assignment created

## 4. Search/Tracking endpoints

**Role scoping applies to every endpoint below.**

| Role | Can see |
|---|---|
| `resident` | Only complaints where `resident_id` = the caller |
| `maintenance_staff` | Only complaints whose **current** assignment has `staff_id` = the caller |
| `administrator` | All complaints |

### 4.1 Current status (FR-015)

`GET /api/complaints/{complaint_id}/status`

`200` → `{"complaint_id": "…", "status": "in_progress", "updated_at": "2026-10-14T11:00:00"}`

Errors:
- `403 FORBIDDEN`: the complaint exists but is outside the caller's scope; no complaint data in the body
- `404 NOT_FOUND`: the complaint does not exist

### 4.2 Status/action history (FR-016)

`GET /api/complaints/{complaint_id}/history`

Returns the rows in time order (oldest first).

```json
200
{
  "complaint_id": "…",
  "items": [
    {"old_status": null, "new_status": "submitted", "changed_by": {"user_id": "…", "name": "Demo Resident"}, "remarks": null, "changed_at": "2026-10-14T09:00:00"},
    {"old_status": "submitted", "new_status": "assigned", "changed_by": {"user_id": "…", "name": "Demo Administrator"}, "remarks": null, "changed_at": "2026-10-14T10:00:00"}
  ]
}
```

Errors: 403 and 404, as in 4.1.

History is read-only. No `PUT`, `PATCH` or `DELETE` route exists, so Flask returns **405** (see 5).

### 4.3 Search and filter (FR-017, FR-018)

`GET /api/complaints`

| Query parameter | Meaning | Validation (400 `INVALID_FILTER` if broken) |
|---|---|---|
| `q` | Exact Complaint ID, or a keyword matched against title and description (case-insensitive) | Max 100 characters |
| `category_id` | Category UUID | Must be a UUID |
| `status` | One status value | Must be one of the five lowercase statuses |
| `department_id` | Department of the current assignment | Must be a UUID |
| `from`, `to` | `created_at` date range, inclusive (`YYYY-MM-DD`) | Valid dates; `from` ≤ `to` |
| `page` | Page number, 20 items per page | Integer ≥ 1 (default 1) |

All values are bound as SQL parameters, never concatenated into SQL (SEC-003, TC-TRK-06).

```json
200
{
  "items": [
    {"complaint_id": "…", "title": "Leaking tap", "category": {"category_id": "…", "name": "Water Supply"}, "status": "assigned", "created_at": "2026-10-14T09:00:00"}
  ],
  "page": 1,
  "total": 1
}
```

Results are newest first and always role-scoped (4, TC-TRK-09).

`POST /api/complaints` (submit) belongs to the Complaint module (Riya). Both routes share the path with different methods, which Flask supports across blueprints.

## 5. Final decisions on the STP alternatives

The STP listed some expected results as alternatives. These are now fixed:

| Test case | STP said | Final | Reason |
|---|---|---|---|
| **TC-ASG-02** Submit complaint with unknown `category_id` | 400/404 | **400 `VALIDATION_ERROR`** | `category_id` is a field in the request body of `POST /api/complaints`, not a resource in the URL. Riya's Complaint contract already returns 400 for invalid complaint information. An inactive category is treated the same way. The database foreign key also rejects it (tested). |
| **TC-TRK-02** Resident views another resident's complaint | 403/404 | **403 `FORBIDDEN`**, empty of complaint data | Matches Riya's `GET /api/complaints/{complaint_id}`, which uses 403 for "not permitted" and 404 for "not found". |
| **TC-TRK-04** Modify or delete history | 405/403 | **405 Method Not Allowed** | History has no `PUT`, `PATCH` or `DELETE` route, so Flask returns 405 for any role. |

### Updated STP steps (lowercase status values)

- TC-TRK-07: `GET /api/complaints?status=assigned&category_id=X` (was `status=Assigned`).
- TC-TRK-08: `GET /api/complaints?status=Foo` → 400 `INVALID_FILTER`. `status=Assigned` (wrong case) also returns 400.

## 6. Requirement coverage

| Requirement | Endpoint(s) | Test cases | Database support (`tests/db`) |
|---|---|---|---|
| FR-009 Predefined categories | `GET /api/categories` | TC-ASG-01, TC-ASG-02 | `db/seed_reference_data.py`; unknown category rejected by FK |
| FR-010 Manage categories | `POST`, `PUT`, `DELETE /api/categories…` | TC-ASG-03, TC-ASG-04, TC-ASG-05 | Duplicate names rejected (case-insensitive); category in use cannot be deleted |
| FR-011 Assign complaint | `POST /api/complaints/{id}/assignment` | TC-ASG-06, TC-ASG-07, TC-ASG-08 | One current assignment per complaint; reassignment keeps history; unknown department rejected |
| FR-015 View own status | `GET /api/complaints/{id}/status` | TC-TRK-01, TC-TRK-02 | Status enum; resident FK |
| FR-016 Status/action history | `GET /api/complaints/{id}/history` | TC-TRK-03, TC-TRK-04 | History rows in order; complaint with history cannot be deleted |
| FR-017 Search | `GET /api/complaints?q=` | TC-TRK-05, TC-TRK-06, TC-TRK-09 | Parameterized queries (application) |
| FR-018 Filter | `GET /api/complaints?status=&category_id=&department_id=&from=&to=` | TC-TRK-07, TC-TRK-08 | Indexes on status and created_at; status enum rejects invalid values |

The endpoint tests themselves (TC-ASG-*, TC-TRK-*) are written when the routes are implemented. The database-level checks in the last column already pass (`python -m pytest tests/db -v`).
