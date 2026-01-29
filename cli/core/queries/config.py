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


def get_lifecycle_config(db: Database, bead_type: str) -> Optional[str]:
    """Get lifecycle configuration for a bead type.

    Args:
        db: Database instance
        bead_type: Bead type to get config for

    Returns:
        JSON config string or None if not found
    """
    row = db.fetchone(
        "SELECT config FROM lifecycle_configs WHERE bead_type = ?",
        (bead_type,)
    )
    return row["config"] if row else None


def get_all_lifecycle_configs(db: Database) -> dict[str, str]:
    """Get all lifecycle configurations.

    Args:
        db: Database instance

    Returns:
        Dict mapping bead_type to JSON config string
    """
    rows = db.fetchall("SELECT bead_type, config FROM lifecycle_configs")
    return {row["bead_type"]: row["config"] for row in rows}


__all__ = [
    "get_config",
    "set_config",
    "get_lifecycle_config",
    "get_all_lifecycle_configs",
]
