from flask import Blueprint

complaints_bp = Blueprint(
    "complaints",
    __name__,
    url_prefix="/api",
)