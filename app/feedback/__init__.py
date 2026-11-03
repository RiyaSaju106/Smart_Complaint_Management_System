"""Feedback module (FR-021, FR-022): one rating and optional comment per resolved complaint.

The app factory registers routes.feedback_bp.
"""
from .routes import feedback_bp  # noqa: F401
