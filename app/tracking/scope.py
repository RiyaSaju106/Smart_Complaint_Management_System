"""Which complaints each role may see (SEC-002). One rule for the whole Search/Tracking module.

  resident           complaints they raised
  maintenance_staff  complaints whose *current* assignment names them
  administrator      every complaint

This is the same rule as _can_view_complaint in routes.py (#26), written as a SQL condition so a
search can apply it to many rows at once instead of checking complaints one by one.
"""
from app.access import ADMINISTRATOR, MAINTENANCE_STAFF, RESIDENT

ROLES = (RESIDENT, MAINTENANCE_STAFF, ADMINISTRATOR)


def visible_complaints(role, user_id, alias="c"):
    """(sql, params): a WHERE condition limiting `alias` (the complaints table) to this caller.

    Raises ValueError for an unknown role, so a caller can never fall through to "see everything".
    """
    if role == ADMINISTRATOR:
        return "TRUE", []
    if role == RESIDENT:
        return f"{alias}.resident_id = %s", [user_id]
    if role == MAINTENANCE_STAFF:
        return (
            f"EXISTS (SELECT 1 FROM assignments scope_a WHERE scope_a.complaint_id = {alias}.complaint_id "
            "AND scope_a.is_current = TRUE AND scope_a.staff_id = %s)",
            [user_id],
        )
    raise ValueError(f"Unknown role: {role!r}")
