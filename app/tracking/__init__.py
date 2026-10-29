"""Search/Tracking module (FR-015 to FR-018, #26)."""

from flask import Blueprint

tracking_bp = Blueprint(
    "tracking",
    __name__,
    url_prefix="/api",
)