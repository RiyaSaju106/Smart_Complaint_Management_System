"""Shared status-history writer: the one function every module uses to write status_history.

Interface agreed on #26 (contract: category-assignment-search-tracking-contract.md, section 1).
Built in #19 because complaint assignment needed it first; Processing/Status (process/) and
Complaint submission switch their own history inserts to it.
"""
import uuid


def record_status_change(cur, complaint_id, old_status, new_status, changed_by, remarks=None):
    """Append one status_history row using the caller's cursor. Never commits or rolls back.

    The row is part of the caller's transaction, so it is saved only if the caller's status change
    is. old_status is None for the initial 'submitted' row; old_status == new_status is allowed
    (a remark without a status change). Transition rules are not checked here: each module
    enforces its own. status_history is append-only: nothing may UPDATE or DELETE its rows.
    """
    cur.execute(
        "INSERT INTO status_history "
        "(history_id, complaint_id, old_status, new_status, changed_by, remarks) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (str(uuid.uuid4()), complaint_id, old_status, new_status, changed_by, remarks),
    )
