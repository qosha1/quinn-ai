"""
Board UI logging configuration.

Configures the board UI to use enhanced logging when connected to an org,
writing logs to the org's centralized log directory.
"""

import logging
import sys
from pathlib import Path
from typing import Optional

from cli.core.logging import configure_enhanced_logging

_configured = False
_current_org: Optional[Path] = None


def configure_board_logging(
    org_path: Optional[Path] = None,
    verbose: bool = False,
) -> None:
    """Configure board UI logging.

    When org_path is provided, configures enhanced logging to write to
    org's logs/board/ directory. Otherwise, logs only to console.

    Args:
        org_path: Path to org folder (if connected).
        verbose: If True, show DEBUG level on console.
    """
    global _configured, _current_org

    # Get root logger for board_ui
    root_logger = logging.getLogger("board_ui")
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers.clear()

    # Console handler (always present)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    console_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        "%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # If connected to org, use enhanced logging
    if org_path:
        configure_enhanced_logging(
            org_path=org_path,
            component="board",
            json_format=True,
            legacy_logging=False,  # Board logs only to board/
            verbose=verbose,
        )
        _current_org = org_path

    _configured = True


def get_board_logger(name: str) -> logging.Logger:
    """Get a logger for board UI components.

    Args:
        name: Logger name (typically __name__).

    Returns:
        Logger instance.
    """
    return logging.getLogger(f"board_ui.{name}")


def is_configured() -> bool:
    """Check if logging has been configured.

    Returns:
        True if configure_board_logging() has been called.
    """
    return _configured


def get_current_org() -> Optional[Path]:
    """Get the currently configured org path.

    Returns:
        Org path if configured, None otherwise.
    """
    return _current_org
