"""Notification service (FR-019): the one function other modules call.

    from app.notifications.service import notify, COMPLAINT_ASSIGNED
    notify(COMPLAINT_ASSIGNED, complaint_id, [resident_id, staff_id])

Call notify() AFTER your own change has been committed. It opens its own connection and commits on
its own, so a notification problem can never undo or block the action that raised it: every
failure is logged and swallowed, and notify() never raises.
"""
import logging
import uuid

from db.connection import get_connection

logger = logging.getLogger(__name__)

COMPLAINT_SUBMITTED = "COMPLAINT_SUBMITTED"
COMPLAINT_ASSIGNED = "COMPLAINT_ASSIGNED"
STATUS_CHANGED = "STATUS_CHANGED"
COMPLAINT_RESOLVED = "COMPLAINT_RESOLVED"
COMPLAINT_CLOSED = "COMPLAINT_CLOSED"

EVENTS = (
    COMPLAINT_SUBMITTED,
    COMPLAINT_ASSIGNED,
    STATUS_CHANGED,
    COMPLAINT_RESOLVED,
    COMPLAINT_CLOSED,
)

STATUS_LABELS = {
    "submitted": "Submitted",
    "assigned": "Assigned",
    "in_progress": "In Progress",
    "resolved": "Resolved",
    "closed": "Closed",
}

MAX_MESSAGE = 255  # notifications.message is VARCHAR(255)


def build_message(event, title, new_status=None):
    """Readable text shown to the user. `title` is the complaint title."""
    subject = f'"{title}"'
    if event == COMPLAINT_SUBMITTED:
        text = f"Your complaint {subject} has been submitted."
    elif event == COMPLAINT_ASSIGNED:
        text = f"Complaint {subject} has been assigned."
    elif event == STATUS_CHANGED:
        label = STATUS_LABELS.get(new_status, new_status or "updated")
        text = f"Complaint {subject} is now {label}."
    elif event == COMPLAINT_RESOLVED:
        text = f"Complaint {subject} has been resolved. You can now close it and give feedback."
    elif event == COMPLAINT_CLOSED:
        text = f"Complaint {subject} has been closed."
    else:
        text = f"Complaint {subject} was updated."
    if len(text) > MAX_MESSAGE:
        text = text[: MAX_MESSAGE - 3] + "..."
    return text


def _unique_recipients(recipient_ids):
    """Drop empty values and duplicates, keeping the order given."""
    seen = []
    for rid in recipient_ids or ():
        if rid and rid not in seen:
            seen.append(rid)
    return seen


def notify(event, complaint_id, recipient_ids, new_status=None):
    """Create one unread notification per recipient for `event` on `complaint_id`.

    `new_status` is only used in the STATUS_CHANGED message. Returns the number of notifications
    created (0 on any failure). Never raises.
    """
    try:
        if event not in EVENTS:
            logger.error("notify() called with unknown event %r for complaint %s", event, complaint_id)
            return 0
        recipients = _unique_recipients(recipient_ids)
        if not recipients:
            return 0
    except Exception:  # bad recipient_ids type, etc.
        logger.exception("notify() received invalid arguments for complaint %s", complaint_id)
        return 0

    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT title FROM complaints WHERE complaint_id = %s", (complaint_id,))
            row = cur.fetchone()
            if row is None:
                logger.error("notify(%s): complaint %s does not exist", event, complaint_id)
                return 0
            message = build_message(event, row["title"], new_status)
            cur.executemany(
                "INSERT INTO notifications (notification_id, user_id, complaint_id, event, message) "
                "VALUES (%s, %s, %s, %s, %s)",
                [(str(uuid.uuid4()), rid, complaint_id, event, message) for rid in recipients],
            )
        conn.commit()
        return len(recipients)
    except Exception:
        logger.exception(
            "Failed to create %s notification(s) for complaint %s", event, complaint_id
        )
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        return 0
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
