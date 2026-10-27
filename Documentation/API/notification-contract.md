# SCMS — Notification module contract (FR-019)

**Owner:** Rohan · **Issues:** #28, #35 · **Tests:** `tests/notifications/` (TC-NTF-01, TC-NTF-02)

In-app notifications for complaint lifecycle events. No e-mail, SMS or push delivery (out of scope).
Follows the shared conventions in `module-boundaries.md`: `/api` base path, UUID ids, lowercase
roles and statuses, `{"error": {"code", "message"}}` error bodies.

## 1. Raising a notification (for other modules)

```python
from app.notifications.service import notify, COMPLAINT_ASSIGNED

# after your own change has been committed:
notify(COMPLAINT_ASSIGNED, complaint_id, [resident_id, staff_id])
```

- Call it **after** `conn.commit()`. It uses its own connection and transaction.
- It **never raises**. Any failure (database down, unknown complaint, bad recipient) is logged
  through `logging` (logger `app.notifications.service`) and `notify()` returns `0`; otherwise it
  returns the number of notifications created. A notification failure therefore never blocks or
  rolls back the action that raised it.
- Empty and duplicate recipient ids are ignored.
- `new_status=` is optional and only used in the `STATUS_CHANGED` message.

| Event | Raised by | Recipients | Status |
|---|---|---|---|
| `COMPLAINT_SUBMITTED` | Complaint module (Riya) | Resident | Ready to call once submission is merged (#17) |
| `COMPLAINT_ASSIGNED` | Category/Assignment module (Rohit) | Resident, assigned staff | Ready to call once assignment is merged (#19) |
| `STATUS_CHANGED` | Processing/Status (Ritu) | Resident | **Wired** in `PATCH /api/staff/complaints/{id}/status` (e.g. → `in_progress`) |
| `COMPLAINT_RESOLVED` | Processing/Status (Ritu) | Resident | **Wired** in the same endpoint when the status becomes `resolved` |
| `COMPLAINT_CLOSED` | Processing/Status (Ritu) | Resident | **Wired** in `PATCH /api/complaints/{id}/close` |

Messages include the complaint title, e.g. `Complaint "No water" is now In Progress.`
They are cut to 255 characters (`notifications.message` is `VARCHAR(255)`).

## 2. Endpoints

All require a logged-in user (any role). Every query uses the session's `user_id`, so a user can
only ever see or change their own notifications.

### 2.1 List my notifications

`GET /api/notifications` · optional `?unread=true|false`, `?limit=1..100` (default 50)

`200 OK`, newest first:

```json
{
  "notifications": [
    {
      "notification_id": "6f1c…",
      "complaint_id": "3f2b…",
      "event": "COMPLAINT_RESOLVED",
      "message": "Complaint \"No water\" has been resolved. You can now close it and give feedback.",
      "is_read": false,
      "created_at": "2026-10-17T10:30:00"
    }
  ],
  "unread_count": 1
}
```

Errors: `400 VALIDATION_ERROR` (bad `unread` or `limit`), `401 UNAUTHENTICATED`.

### 2.2 Mark one notification as read

`PATCH /api/notifications/{notification_id}/read` · no body

`200 OK` with `{"message": "...", "notification": {…}}`. Marking an already-read notification is harmless.

Errors: `401 UNAUTHENTICATED`, `403 FORBIDDEN` (belongs to another user), `404 NOT_FOUND`.

### 2.3 Mark all my notifications as read

`PATCH /api/notifications/read-all` · no body

`200 OK` with `{"message": "...", "updated": <number changed>}`. Error: `401 UNAUTHENTICATED`.

## 3. Traceability

| Requirement | Design element | Verification |
|---|---|---|
| FR-019 events generated | `notify()` + hooks in Processing/Status | TC-NTF-01: `test_full_lifecycle_through_the_api_notifies_the_resident`, `test_submission_…`, `test_assignment_…`, `test_administrator_closing_…` |
| FR-019 own notifications only | Session-scoped queries | TC-NTF-02: `test_user_cannot_see_or_mark_another_users_notification`, `test_request_cannot_choose_whose_notifications_to_list` |
| Failures don't block actions | `notify()` logs and swallows | `test_notification_failure_does_not_block_status_update`, `test_failed_insert_is_logged_and_leaves_nothing_behind` |
