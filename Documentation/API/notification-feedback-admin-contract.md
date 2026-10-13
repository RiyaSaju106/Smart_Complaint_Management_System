# SCMS — Notification, Feedback and Admin/Reporting API Contracts

## 1. Purpose

Define the module boundaries and initial API contracts for the Notification, Feedback and Admin/Reporting modules of the Smart Complaint Management System.

## 2. Module boundaries

| Module | Responsible for | Not responsible for | Requirements |
|---|---|---|---|
| Notification | Creating in-app notifications for complaint lifecycle events; listing a user's notifications; read/unread state | Changing complaint status; SMS/WhatsApp/e-mail delivery (out of scope) | FR-019 |
| Feedback | Accepting one rating and optional comment per resolved complaint; returning feedback for a complaint | Deciding when a complaint is Resolved (Processing/Status module) | FR-021, FR-022 |
| Admin/Reporting | Staff/resident account management; dashboard counts; basic reports | Complaint assignment (Category/Assignment module); changing complaint data | FR-023, FR-024, FR-025 |

Dependencies: all three modules rely on the Auth/User module for the authenticated user and role. Admin/Reporting reads complaint, category, department, assignment and feedback data; it never writes complaint data.

## 3. General conventions

- Base path: `/api`
- Request and response format: JSON.
- Authentication is required for every endpoint in this document.
- Admin/Reporting endpoints are restricted to the `admin` role.
- Never return passwords or password hashes in API responses.
- Errors use the common error response agreed in the Auth/User contract.

## 4. Notification events

Other modules call the internal function below after their own change has been saved:

```python
notify(event, complaint_id, recipient_ids)
```

| Event | Raised by | Recipients |
|---|---|---|
| `COMPLAINT_SUBMITTED` | Complaint module | Resident |
| `COMPLAINT_ASSIGNED` | Category/Assignment module | Resident, assigned staff |
| `STATUS_CHANGED` | Processing/Status module | Resident |
| `COMPLAINT_RESOLVED` | Processing/Status module | Resident |
| `COMPLAINT_CLOSED` | Processing/Status module | Resident |

Rule: a notification failure is logged and must never block or roll back the action that raised it.

## 5. Notification endpoints

### 5.1 List my notifications

- **Method:** GET
- **Path:** `/api/notifications`
- **Purpose:** Return the authenticated user's own notifications, newest first.
- **Query:** `unread=true` (optional)

Expected success: `200 OK`

Example response:

```json
{
  "notifications": [
    {
      "id": 12,
      "complaint_id": 4,
      "event": "COMPLAINT_ASSIGNED",
      "message": "Your complaint #4 has been assigned.",
      "is_read": false,
      "created_at": "2026-10-14T10:30:00Z"
    }
  ]
}
```

Possible error: `401 Unauthorized`.

### 5.2 Mark a notification as read

- **Method:** PATCH
- **Path:** `/api/notifications/{id}/read`
- **Purpose:** Mark one of the user's own notifications as read.

Expected success: `200 OK`

Possible errors: `401 Unauthorized`, `403 Forbidden` (belongs to another user), `404 Not Found`.

## 6. Feedback endpoints

### 6.1 Submit feedback

- **Method:** POST
- **Path:** `/api/complaints/{complaint_id}/feedback`
- **Purpose:** Record the complaint owner's rating once the complaint is Resolved.

Example request:

```json
{
  "rating": 4,
  "comment": "Fixed quickly, thank you."
}
```

Rules: `rating` is an integer from 1 to 5; `comment` is optional (maximum 500 characters); one feedback per complaint.

Expected success: `201 Created`

Example response:

```json
{
  "message": "Feedback recorded",
  "feedback": {
    "id": 3,
    "complaint_id": 4,
    "rating": 4,
    "comment": "Fixed quickly, thank you.",
    "created_at": "2026-10-14T11:00:00Z"
  }
}
```

Possible errors: `400 Bad Request` (rating missing or outside 1–5), `401 Unauthorized`, `403 Forbidden` (not the complaint owner), `404 Not Found`, `409 Conflict` (complaint not Resolved, or feedback already submitted).

### 6.2 View feedback

- **Method:** GET
- **Path:** `/api/complaints/{complaint_id}/feedback`
- **Purpose:** Return the feedback for a complaint to its owner, the assigned staff member or an administrator.

Expected success: `200 OK`

Possible errors: `401 Unauthorized`, `403 Forbidden`, `404 Not Found`.

## 7. Admin/Reporting endpoints

All endpoints in this section return `403 Forbidden` when the user is not an administrator.

### 7.1 List users

- **Method:** GET
- **Path:** `/api/admin/users`
- **Query:** `role=resident|staff|admin`, `active=true|false` (both optional)

Expected success: `200 OK`

### 7.2 Create a staff or administrator account

- **Method:** POST
- **Path:** `/api/admin/users`

Example request:

```json
{
  "name": "Test Plumber",
  "email": "plumber@example.com",
  "password": "ExamplePassword123!",
  "role": "staff",
  "department_id": 2
}
```

Expected success: `201 Created`

Possible errors: `400 Bad Request`, `409 Conflict` (email already registered).

### 7.3 Update a user

- **Method:** PATCH
- **Path:** `/api/admin/users/{id}`
- **Purpose:** Change `role`, `department_id` or `is_active`. Accounts are deactivated, never deleted, so complaint history is preserved.

Expected success: `200 OK`

Possible errors: `400 Bad Request`, `404 Not Found`, `409 Conflict` (administrator deactivating their own account).

### 7.4 Dashboard

- **Method:** GET
- **Path:** `/api/admin/dashboard`

Example response:

```json
{
  "total": 6,
  "by_status": {
    "Submitted": 2,
    "Assigned": 1,
    "In Progress": 1,
    "Resolved": 1,
    "Closed": 1
  },
  "pending": 4,
  "average_rating": 4.0
}
```

Expected success: `200 OK`

### 7.5 Reports

- **Method:** GET
- **Path:** `/api/admin/reports`
- **Query:** `type=status|category|period|pending|workload` (required), `from`, `to` (dates, optional)

Example response:

```json
{
  "type": "category",
  "rows": [
    { "label": "Plumbing", "count": 3 },
    { "label": "Electrical", "count": 2 }
  ]
}
```

Expected success: `200 OK`

Possible error: `400 Bad Request` (unknown type, or `from` later than `to`).

## 8. Data needed from other modules

| Data | Owner | Used for |
|---|---|---|
| User id, role, is_active | Auth/User (Riya) | Access checks, user management |
| Complaint id, owner, status, category, created_at | Complaint / Processing (Riya, Ritu) | Notifications, feedback eligibility, dashboard, reports |
| Category, department, current assignment | Category/Assignment (Rohit) | Assignment notifications, category and workload reports |

New tables owned by these modules: `notification` (id, user_id, complaint_id, event, message, is_read, created_at) and `feedback` (id, complaint_id unique, resident_id, rating, comment, created_at).

## 9. Admin backlog

| Sprint | Task | Requirement |
|---|---|---|
| 2 | Notification and Feedback model skeletons; test fixtures | FR-019, FR-021 |
| 2 | Admin-only route guard; authorization tests | FR-023 |
| 2 | Submission notification hook (must not block complaint creation) | FR-019 |
| 2 | Notification list and read/unread state | FR-019 |
| 3 | Assignment, status, resolution and closure notifications | FR-019 |
| 3 | Feedback submission with eligibility and duplicate checks | FR-021, FR-022 |
| 3 | Admin user management (create staff, update, deactivate) | FR-023 |
| 3 | Dashboard counts and basic reports | FR-024, FR-025 |
| 3 | Notification, feedback and admin UI | FR-019, FR-021–FR-025 |

## 10. Requirements mapping

- FR-019: Notification module.
- FR-021, FR-022: Feedback module.
- FR-023, FR-024, FR-025: Admin/Reporting module.

## 11. Team decisions pending

- Final table and field names, to align with the database conventions.
- Whether e-mail notifications are added later (in-app only for Version 1.0).
- Pagination for the notification list and reports.

**Note:** This document is an initial proposal for team review. Confirm all endpoint details and requirement mappings against the approved SCMS SRS before implementation.
