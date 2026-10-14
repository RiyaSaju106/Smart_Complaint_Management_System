"""Shared MySQL connection helper for the db/ scripts and tests/db.

Connection settings come from environment variables, loaded from the
repository's .env file if present.
"""
import os
from pathlib import Path

import pymysql
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

REQUIRED_VARS = ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD")


def get_settings():
    missing = [name for name in REQUIRED_VARS if not os.environ.get(name)]
    if missing:
        raise RuntimeError(f"Missing environment variables: {', '.join(missing)}")
    return {
        "host": os.environ["DB_HOST"],
        "port": int(os.environ["DB_PORT"]),
        "database": os.environ["DB_NAME"],
        "user": os.environ["DB_USER"],
        "password": os.environ["DB_PASSWORD"],
    }


def get_connection(database=None, use_database=True):
    """Open a connection to DB_NAME (or `database`).

    Pass use_database=False to connect to the server without selecting a database.
    """
    settings = get_settings()
    if database is not None:
        settings["database"] = database
    if not use_database:
        settings.pop("database")
    return pymysql.connect(
        **settings,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
