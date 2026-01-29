"""Common utility functions shared across query modules."""

import uuid
from datetime import date, datetime
from typing import Optional

from ..db import Database


def generate_id(prefix: str = "") -> str:
    """Generate a unique ID.

    Args:
        prefix: Optional prefix for the ID

    Returns:
        Unique identifier string
    """
    short_uuid = str(uuid.uuid4())[:8]
    return f"{prefix}-{short_uuid}" if prefix else short_uuid


def parse_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    """Parse datetime from ISO format string.

    Args:
        dt_str: ISO format datetime string

    Returns:
        datetime object or None if parsing fails
    """
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str) if isinstance(dt_str, str) else dt_str
    except (ValueError, AttributeError):
        return None


def parse_date(date_str: Optional[str]) -> Optional[date]:
    """Parse date from ISO format string.

    Args:
        date_str: ISO format date string

    Returns:
        date object or None if parsing fails
    """
    if not date_str:
        return None
    try:
        return date.fromisoformat(date_str) if isinstance(date_str, str) else date_str
    except (ValueError, AttributeError):
        return None


def get_row_value(row: dict, key: str, default=None):
    """Safely get value from sqlite3.Row or dict.

    Args:
        row: Database row (sqlite3.Row or dict)
        key: Column name
        default: Default value if key not found

    Returns:
        Value from row or default
    """
    try:
        return row[key]
    except (KeyError, IndexError):
        return default


def get_or_create_config(db: Database, key: str, default: str) -> str:
    """Get config value or create with default if not exists.

    Args:
        db: Database instance
        key: Config key
        default: Default value to set if key doesn't exist

    Returns:
        Config value
    """
    value = db.fetchone("SELECT value FROM config WHERE key = ?", (key,))
    if value:
        return value["value"]

    db.execute("INSERT INTO config (key, value) VALUES (?, ?)", (key, default))
    db.connection.commit()
    return default


__all__ = [
    "generate_id",
    "parse_datetime",
    "parse_date",
    "get_row_value",
    "get_or_create_config",
]
