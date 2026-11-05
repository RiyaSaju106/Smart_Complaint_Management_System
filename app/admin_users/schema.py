"""Validation for the administrator user-management endpoints (FR-023, #33).

Pure functions with no Flask or database code. Each parser returns (value, error_message);
error_message is None when the input is valid.
"""
import re
import uuid

MANAGED_ROLES = ("resident", "maintenance_staff")  # administrators are never managed through the API
STATUSES = ("active", "inactive")
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

LIMITS = {"name": 100, "email": 100, "contact_number": 15, "unit_address": 150}
MIN_PASSWORD = 8
MAX_PASSWORD = 128
UPDATABLE = {"name", "contact_number", "unit_address", "department_id"}
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def is_uuid(value):
    try:
        return str(uuid.UUID(str(value))) == str(value).lower()
    except ValueError:
        return False


def _text(data, field, required=True):
    value = data.get(field)
    if value is None or (isinstance(value, str) and not value.strip()):
        return (None, f"'{field}' is required.") if required else (None, None)
    if not isinstance(value, str):
        return None, f"'{field}' must be text."
    value = value.strip()
    if len(value) > LIMITS[field]:
        return None, f"'{field}' must be at most {LIMITS[field]} characters."
    return value, None


def parse_list_filters(args):
    """?role=&status=&department_id=&q=&page=&page_size="""
    role = args.get("role") or None
    if role is not None and role not in MANAGED_ROLES:
        return None, "'role' must be resident or maintenance_staff."
    status = args.get("status") or None
    if status is not None and status not in STATUSES:
        return None, "'status' must be active or inactive."
    department_id = args.get("department_id") or None
    if department_id is not None and not is_uuid(department_id):
        return None, "'department_id' is not a valid id."
    q = (args.get("q") or "").strip() or None
    if q is not None and len(q) > 100:
        return None, "'q' must be at most 100 characters."
    try:
        page = int(args.get("page") or 1)
        page_size = int(args.get("page_size") or DEFAULT_PAGE_SIZE)
    except ValueError:
        return None, "'page' and 'page_size' must be whole numbers."
    if page < 1 or not 1 <= page_size <= MAX_PAGE_SIZE:
        return None, f"'page' must be at least 1 and 'page_size' between 1 and {MAX_PAGE_SIZE}."
    return {"role": role, "status": status, "department_id": department_id, "q": q,
            "page": page, "page_size": page_size}, None


def parse_create(data):
    """POST body: name, email, password, role, and per role:
    resident -> contact_number, unit_address (both required, as at self-registration);
    maintenance_staff -> department_id (required), contact_number optional."""
    if not isinstance(data, dict):
        return None, "Please provide a JSON object."
    role = data.get("role")
    if role not in MANAGED_ROLES:
        return None, "'role' must be resident or maintenance_staff."

    name, problem = _text(data, "name")
    if problem:
        return None, problem
    email, problem = _text(data, "email")
    if problem:
        return None, problem
    email = email.lower()
    if not EMAIL_RE.fullmatch(email):
        return None, "'email' is not a valid email address."

    password = data.get("password")
    if not isinstance(password, str) or not password:
        return None, "'password' is required."
    if not MIN_PASSWORD <= len(password) <= MAX_PASSWORD:
        return None, f"'password' must be {MIN_PASSWORD} to {MAX_PASSWORD} characters."

    is_resident = role == "resident"
    contact_number, problem = _text(data, "contact_number", required=is_resident)
    if problem:
        return None, problem
    unit_address, problem = _text(data, "unit_address", required=is_resident)
    if problem:
        return None, problem

    department_id = data.get("department_id")
    if is_resident:
        if department_id is not None:
            return None, "'department_id' applies to maintenance staff only."
    else:
        if not isinstance(department_id, str) or not is_uuid(department_id):
            return None, "'department_id' is required for maintenance staff."

    return {"name": name, "email": email, "password": password, "role": role,
            "contact_number": contact_number, "unit_address": unit_address,
            "department_id": department_id}, None


def parse_update(data, target_role):
    """PATCH body: any of name, contact_number, unit_address, department_id (staff only).
    Role and email are not changeable here."""
    if not isinstance(data, dict) or not data:
        return None, "Please provide at least one field to update."
    unknown = sorted(set(data) - UPDATABLE)
    if unknown:
        return None, ("Only name, contact_number, unit_address and department_id can be "
                      f"updated (not: {', '.join(unknown)}).")
    clean = {}
    for field in ("name", "contact_number", "unit_address"):
        if field in data:
            value, problem = _text(data, field)
            if problem:
                return None, problem
            clean[field] = value
    if "department_id" in data:
        if target_role != "maintenance_staff":
            return None, "'department_id' applies to maintenance staff only."
        if not isinstance(data["department_id"], str) or not is_uuid(data["department_id"]):
            return None, "'department_id' is not a valid id."
        clean["department_id"] = data["department_id"]
    return clean, None