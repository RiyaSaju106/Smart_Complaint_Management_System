"""Request validation and lifecycle rules for the Processing & Status module.

Pure functions with no Flask or database code, so they are easy to read and to test on their own.
Each parser returns (value, error_message); error_message is None when the input is valid.

Values are lowercase and case-sensitive, matching db/schema.sql: 'In_Progress' is rejected, not
converted.
"""

STATUSES = ("submitted", "assigned", "in_progress", "resolved", "closed")

# Staff-driven lifecycle (SAD 3.4). Closing is a separate endpoint (resident or administrator).
ALLOWED_TRANSITIONS = {
    "assigned": ("in_progress",),
    "in_progress": ("resolved",),
}

# Staff may add remarks only while they are working on the complaint.
REMARKABLE_STATUSES = ("assigned", "in_progress")

MAX_REMARKS = 500  # status_history.remarks is VARCHAR(500)
# resolutions.details is TEXT (65,535 bytes, i.e. at least 16,383 utf8mb4 characters); this keeps
# well inside that and stops oversized request bodies being stored.
MAX_RESOLUTION_DETAILS = 5000


def can_transition(old_status, new_status):
    return new_status in ALLOWED_TRANSITIONS.get(old_status, ())


def _optional_text(data, name, max_length=None):
    """Return (stripped text or None, error message or None). Blank text counts as missing."""
    value = data.get(name)
    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, f"'{name}' must be a string."
    value = value.strip()
    if max_length is not None and len(value) > max_length:
        return None, f"'{name}' must be at most {max_length} characters."
    return (value or None), None


def parse_status_filter(value):
    """Validate the ?status= filter on the assigned-complaints list. Returns an error or None."""
    if value is not None and value not in STATUSES:
        return f"Invalid status filter: {value}"
    return None


def parse_status_update(data):
    """Validate a PATCH .../status body: {status, remarks, resolution_details}.

    Returns ({"status", "remarks", "resolution_details"}, None) or (None, error message).
    Whether resolution_details is *required* depends on the target status, which is checked in the
    route once the transition is known to be allowed.
    """
    status = data.get("status")
    if not isinstance(status, str) or status not in STATUSES:
        return None, f"Invalid target status: {status}"
    remarks, problem = _optional_text(data, "remarks", MAX_REMARKS)
    if problem:
        return None, problem
    details, problem = _optional_text(data, "resolution_details", MAX_RESOLUTION_DETAILS)
    if problem:
        return None, problem
    return {"status": status, "remarks": remarks, "resolution_details": details}, None


def parse_close(data):
    """Validate the optional closure_notes of a PATCH .../close body. Returns (notes, error)."""
    return _optional_text(data, "closure_notes", MAX_REMARKS)


def is_confirmed(data):
    """Closing needs an explicit JSON true; 'true', 1 and a missing value do not count."""
    return data.get("confirmation") is True


def parse_remark(data):
    """Validate a POST .../remarks body: {remarks}. A remark is required and may not be blank."""
    remarks, problem = _optional_text(data, "remarks", MAX_REMARKS)
    if problem:
        return None, problem
    if remarks is None:
        return None, "'remarks' is required."
    return remarks, None
