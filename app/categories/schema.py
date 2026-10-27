"""Request validation for the Category/Department module.

Pure functions with no Flask or database code. Each parser returns (value, error_message);
error_message is None when the input is valid.

Limits match db/schema.sql: categories.name VARCHAR(100), categories.description VARCHAR(255).
"""

MAX_NAME = 100
MAX_DESCRIPTION = 255


def _name(data):
    value = data.get("name")
    if not isinstance(value, str) or not value.strip():
        return None, "'name' is required and must be a non-empty string."
    value = value.strip()
    if len(value) > MAX_NAME:
        return None, f"'name' must be at most {MAX_NAME} characters."
    return value, None


def _description(data):
    """Optional text: missing, null or blank all mean no description."""
    value = data.get("description")
    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, "'description' must be a string or null."
    value = value.strip()
    if len(value) > MAX_DESCRIPTION:
        return None, f"'description' must be at most {MAX_DESCRIPTION} characters."
    return (value or None), None


def parse_new_category(data):
    """POST /api/categories body: {name, description?}."""
    if not isinstance(data, dict):
        return None, "Please provide a JSON object."
    name, problem = _name(data)
    if problem:
        return None, problem
    description, problem = _description(data)
    if problem:
        return None, problem
    return {"name": name, "description": description}, None


def parse_category_update(data):
    """PUT /api/categories/<id> body: {name, description, is_active}, all keys required.

    description may be null. is_active must be a JSON boolean ("false" and 0 are rejected).
    """
    if not isinstance(data, dict):
        return None, "Please provide a JSON object."
    missing = [key for key in ("name", "description", "is_active") if key not in data]
    if missing:
        return None, f"Missing required field(s): {', '.join(missing)}."
    name, problem = _name(data)
    if problem:
        return None, problem
    description, problem = _description(data)
    if problem:
        return None, problem
    if not isinstance(data["is_active"], bool):
        return None, "'is_active' must be true or false."
    return {"name": name, "description": description, "is_active": data["is_active"]}, None


def parse_include_inactive(value):
    """?include_inactive= on GET /api/categories: absent, 'true' or 'false'."""
    if value is None or value == "false":
        return False, None
    if value == "true":
        return True, None
    return None, "'include_inactive' must be 'true' or 'false'."
