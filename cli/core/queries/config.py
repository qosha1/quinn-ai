"""Configuration key-value store queries."""

from typing import Optional

from ..db import Database


def get_config(db: Database, key: str) -> Optional[str]:
    """Get a config value.

    Args:
        db: Database instance
        key: Config key

    Returns:
        Config value or None
    """
    row = db.fetchone("SELECT value FROM config WHERE key = ?", (key,))
    return row["value"] if row else None


def set_config(db: Database, key: str, value: str) -> None:
    """Set a config value.

    Args:
        db: Database instance
        key: Config key
        value: Config value
    """
    db.execute(
        "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
        (key, value)
    )
    db.connection.commit()


__all__ = [
    "get_config",
    "set_config",
]
