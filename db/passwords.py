"""Password hashing for SCMS (SEC-001). Use these instead of calling werkzeug directly.

The method is pinned to pbkdf2:sha256 because Werkzeug's default (scrypt) needs
hashlib.scrypt, which some Python builds lack (e.g. macOS system Python 3.9).
"""
from werkzeug.security import check_password_hash, generate_password_hash

PASSWORD_HASH_METHOD = "pbkdf2:sha256"


def hash_password(password):
    return generate_password_hash(password, method=PASSWORD_HASH_METHOD)


def verify_password(password_hash, password):
    return check_password_hash(password_hash, password)
