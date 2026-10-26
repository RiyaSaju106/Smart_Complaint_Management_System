
import uuid

MAX_TITLE = 150
MAX_DESCRIPTION = 1000
MAX_LOCATION = 200
MAX_IDEMPOTENCY_KEY = 128


def _required_text(data, name, max_length):
    value = data.get(name)

    if not isinstance(value, str) or not value.strip():
        return None, f"'{name}' is required and must be a non-empty string."

    value = value.strip()

    if len(value) > max_length:
        return None, f"'{name}' must be at most {max_length} characters."

    return value, None


def parse_complaint(data):
    if not isinstance(data, dict):
        return None, "Please provide a JSON object."

    title, problem = _required_text(data, "title", MAX_TITLE)
    if problem:
        return None, problem

    category_id = data.get("category_id")

    if not isinstance(category_id, str) or not category_id.strip():
        return None, "'category_id' is required."

    category_id = category_id.strip()

    try:
        uuid.UUID(category_id)
    except (ValueError, AttributeError):
        return None, "'category_id' must be a valid UUID."

    description, problem = _required_text(
        data, "description", MAX_DESCRIPTION
    )
    if problem:
        return None, problem

    location, problem = _required_text(
        data, "location", MAX_LOCATION
    )
    if problem:
        return None, problem

    return {
        "title": title,
        "category_id": category_id,
        "description": description,
        "location": location,
    }, None


def parse_idempotency_key(value):
    if value is None:
        return None, None

    if not isinstance(value, str):
        return None, "Idempotency-Key must be a string."

    value = value.strip()

    if not value:
        return None, "Idempotency-Key cannot be blank."

    if len(value) > MAX_IDEMPOTENCY_KEY:
        return None, (
            f"Idempotency-Key must be at most "
            f"{MAX_IDEMPOTENCY_KEY} characters."
        )

    return value, None
