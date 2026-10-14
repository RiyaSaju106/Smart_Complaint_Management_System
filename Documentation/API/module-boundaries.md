# SCMS: Module boundaries and shared API conventions

**Issue:** #4 · **Status:** proposed, for team review
**Sources:** SRS (FR/NFR/SEC lists, business rules, Appendix B and C), each member's SAD and STP, and the API contract documents listed below.

## 1. Architecture in one line

Layered modular monolith: browser → Flask routes → service layer (business rules, role checks) → data access layer → MySQL (`db/schema.sql`). Modules call each other only through service functions, never through another module's tables directly, except where section 4 says a module may read a table.

## 2. Modules, owners and contracts

| Module | Owner | Requirements | Contract document |
|---|---|---|---|
| Auth/User | Riya | FR-001–FR-004, SEC-001–SEC-005 | `auth-user-contract.md` (PR #12) |
| Complaint | Riya | FR-005–FR-008 | Riya's SAD 4.3 (not yet in the repo) |
| Category/Assignment | Rohit | FR-009–FR-011 | `category-assignment-search-tracking-contract.md` (PR #21) |
| Processing/Status | Ritu | FR-012–FR-014, FR-020 | Ritu's SAD 4.3 (not yet in the repo) |
| Search/Tracking | Rohit | FR-015–FR-018 | `category-assignment-search-tracking-contract.md` (PR #21) |
| Notification | Rohan | FR-019 | `notification-feedback-admin-contract.md` (PR #13) |
| Feedback | Rohan | FR-021, FR-022 | `notification-feedback-admin-contract.md` (PR #13) |
| Admin/Reporting | Rohan | FR-023–FR-025 | `notification-feedback-admin-contract.md` (PR #13) |
| Database (MySQL) | Rohit | Supports all; NFR-005/006 | `db/schema.sql`, `db/README.md` (PR #21) |

## 3. Shared conventions (proposed)

Every contract should follow these. Section 6 lists where the current documents differ.

| Topic | Convention |
|---|---|
| Base path | `/api/...` with no version segment |
| IDs | UUID strings (`CHAR(36)`), generated in Python with `uuid.uuid4()`. Never integers. |
| Role values | `resident`, `maintenance_staff`, `administrator` (lowercase; stored and sent as-is). UI display: Resident, Maintenance Staff, Administrator. |
| Complaint status values | `submitted`, `assigned`, `in_progress`, `resolved`, `closed` (lowercase). UI display: Submitted, Assigned, In Progress, Resolved, Closed. |
| Status workflow | `submitted` → `assigned` → `in_progress` → `resolved` → `closed` (SRS business rules). Closing requires a resolution; feedback only after `resolved`. |
| Error body | `{"error": {"code": "UPPER_SNAKE_CODE", "message": "Readable text"}}` |
| Common status codes | 400 invalid input or filter · 401 not logged in · 403 logged in but not allowed · 404 resource in the URL not found · 405 method not supported · 409 conflicts with current state or a unique value |
| Timestamps | ISO 8601 strings, server time |
| Passwords | Hashed with `db.passwords.hash_password` (Werkzeug `pbkdf2:sha256`); never returned by any API |
| Deletion | Users and categories are deactivated (`is_active = false`), not deleted, so complaint history stays intact |

## 4. Data ownership

| Table | Written by | Notes |
|---|---|---|
| `users` | Auth/User (registration, profile), Admin/Reporting (staff accounts, role, department, `is_active`) | |
| `departments`, `categories` | Category/Assignment | Seeded by `db/seed_reference_data.py` |
| `complaints` | Complaint (create); Category/Assignment (`submitted` → `assigned`); Processing/Status (later transitions) | |
| `attachments` | Complaint | |
| `assignments` | Category/Assignment | One current row per complaint (enforced by the database) |
| `status_history` | Any module that changes status, **only** via Search/Tracking's `record_status_change()` | Append-only; no update or delete |
| `resolutions` | Processing/Status | One per complaint |
| `notifications` | Notification | |
| `feedback` | Feedback | One per complaint; rating 1–5 (enforced by the database) |

Admin/Reporting reads all tables but writes only `users`.

## 5. Cross-module interfaces

| Provider → consumer | Interface |
|---|---|
| Auth/User → all | Current `user_id` and `role` on each request |
| Category/Assignment → Complaint | `get_active_category(category_id)` |
| Category/Assignment → Processing/Status, Notification | `get_current_assignment(complaint_id)` |
| Search/Tracking → Complaint, Category/Assignment, Processing/Status | `record_status_change(complaint_id, old, new, changed_by, remarks)` |
| Notification → Complaint, Category/Assignment, Processing/Status | `notify(event, complaint_id, recipient_ids)` with events `COMPLAINT_SUBMITTED`, `COMPLAINT_ASSIGNED`, `STATUS_CHANGED`, `COMPLAINT_RESOLVED`, `COMPLAINT_CLOSED` |

## 6. Inconsistencies to resolve before Issue #4 is Done

| # | Where | Current text | Proposed fix | Owner |
|---|---|---|---|---|
| 1 | `notification-feedback-admin-contract.md` (PR #13) | Roles `resident`, `staff`, `admin` (e.g. `role=resident\|staff\|admin`, `"role": "staff"`) | Use `maintenance_staff` and `administrator` | Rohan |
| 2 | PR #13 | Integer IDs (`"id": 12`, `"complaint_id": 4`) | UUID strings | Rohan |
| 3 | PR #13, section 8 | Feedback columns `comment`, `created_at`; notification table names singular | Database uses `comments`, `submitted_at` (SAD data dictionary) and plural table names. The API may keep `comment` if the service maps it, but say so. | Rohan |
| 4 | `auth-user-contract.md` (PR #12) | `"id": 1` | `"user_id": "<uuid>"` | Riya |
| 5 | Riya's SAD 4.3 Complaint module | `status=Submitted`; both 400 and 422 for invalid input | `status: "submitted"`; use 400 only (unknown category → 400, see TC-ASG-02) | Riya |
| 6 | Ritu's SAD 4.3 | Base path `/api/v1/...` | `/api/...` like every other module | Ritu |
| 7 | Ritu's SAD 4.3 | Endpoint titles swapped: "Close Complaint Workflow" is on `/status`, "Update Complaint Status" is on `/close` | Swap the titles | Ritu |
| 8 | Ritu's SAD 4.4 | Error body `error_code`, `message`, `timestamp`; mentions SLF4J/Logback | Use the shared error body; Python `logging` (the stack is Flask) | Ritu |
| 9 | All | Status values written capitalized | Lowercase values from section 3 | All |

Category/Assignment and Search/Tracking already follow section 3.

## 7. Review checklist for Issue #4

- [ ] Each owner confirms their row in section 2 and their tables in section 4.
- [ ] Team agrees on the conventions in section 3, especially lowercase status values.
- [ ] Items 1–9 in section 6 are fixed in the owners' contract documents.
- [ ] PRs #12, #13 and #21 are reviewed and merged.
