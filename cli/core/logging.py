"""
QuinnAI CLI logging infrastructure.

Provides structured logging for debugging with:
- Log levels (DEBUG, INFO, WARNING, ERROR)
- File output to org's logs directory
- Console output controlled by verbosity

Usage:
    from cli.core.logging import get_logger, configure_logging

    # At CLI entry point
    configure_logging(org_path, verbose=args.verbose)

    # In modules
    logger = get_logger(__name__)
    logger.info("Session spawned", worker_id=worker.id)
"""

import logging
import sys
from pathlib import Path
from typing import Optional

from .constants import LIVE_DIR


# ===================
# CONSTANTS
# ===================

LOGS_DIR = "logs"
"""Logs directory name within org."""

LOG_FILE_NAME = "quinn.log"
"""Main log file name."""

DEFAULT_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
"""Default log format string."""

DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
"""Default date format for log timestamps."""

MAX_LOG_SIZE_BYTES = 10 * 1024 * 1024  # 10MB
"""Maximum log file size before rotation."""

BACKUP_COUNT = 5
"""Number of backup log files to keep."""


# ===================
# LOGGER CACHE
# ===================

_loggers: dict[str, logging.Logger] = {}
_configured = False
_org_path: Optional[Path] = None


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for the given name.

    Creates a new logger if one doesn't exist, otherwise returns cached.
    If logging hasn't been configured yet, returns a basic logger that
    logs to stderr at WARNING level.

    Args:
        name: Logger name, typically __name__ of the calling module.

    Returns:
        Logger instance.
    """
    if name in _loggers:
        return _loggers[name]

    logger = logging.getLogger(f"quinn.{name}")

    # If not configured yet, set a NullHandler to avoid "No handler" warnings
    if not _configured:
        if not logger.handlers:
            logger.addHandler(logging.NullHandler())

    _loggers[name] = logger
    return logger


def configure_logging(
    org_path: Optional[Path] = None,
    verbose: bool = False,
    debug: bool = False,
    log_to_file: bool = True,
) -> None:
    """Configure logging for the CLI.

    Sets up file and console handlers based on verbosity settings.
    Call this once at CLI entry point before any logging.

    Args:
        org_path: Path to org folder. If provided, logs go to org_path/live/logs/.
                 If None, file logging is disabled.
        verbose: If True, show INFO level on console. If False, only WARNING+.
        debug: If True, show DEBUG level on console. Overrides verbose.
        log_to_file: If True, write logs to file (requires org_path).
    """
    global _configured, _org_path

    _org_path = org_path

    # Get root quinn logger
    root_logger = logging.getLogger("quinn")
    root_logger.setLevel(logging.DEBUG)  # Capture all, filter at handlers

    # Clear any existing handlers
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stderr)
    if debug:
        console_handler.setLevel(logging.DEBUG)
    elif verbose:
        console_handler.setLevel(logging.INFO)
    else:
        console_handler.setLevel(logging.WARNING)

    console_formatter = logging.Formatter(DEFAULT_LOG_FORMAT, DEFAULT_DATE_FORMAT)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # File handler (if org_path provided and log_to_file enabled)
    if org_path and log_to_file:
        try:
            log_dir = org_path / LIVE_DIR / LOGS_DIR
            log_dir.mkdir(parents=True, exist_ok=True)

            log_file = log_dir / LOG_FILE_NAME

            # Use RotatingFileHandler to prevent unbounded growth
            from logging.handlers import RotatingFileHandler

            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=MAX_LOG_SIZE_BYTES,
                backupCount=BACKUP_COUNT,
            )
            file_handler.setLevel(logging.DEBUG)  # Log everything to file

            file_formatter = logging.Formatter(DEFAULT_LOG_FORMAT, DEFAULT_DATE_FORMAT)
            file_handler.setFormatter(file_formatter)
            root_logger.addHandler(file_handler)

        except (OSError, PermissionError) as e:
            # Can't set up file logging - log a warning to console
            root_logger.warning(f"Could not set up file logging: {e}")

    _configured = True

    # Update all cached loggers to use the new configuration
    for name, logger in _loggers.items():
        # Remove NullHandler if present
        logger.handlers = [h for h in logger.handlers if not isinstance(h, logging.NullHandler)]


def get_log_file_path() -> Optional[Path]:
    """Get the current log file path.

    Returns:
        Path to log file if configured, None otherwise.
    """
    if _org_path:
        return _org_path / LIVE_DIR / LOGS_DIR / LOG_FILE_NAME
    return None


def is_configured() -> bool:
    """Check if logging has been configured.

    Returns:
        True if configure_logging() has been called.
    """
    return _configured


# ===================
# STRUCTURED LOGGING HELPERS
# ===================

def log_session_spawn(
    logger: logging.Logger,
    worker_id: str,
    worker_name: str,
    provider: str,
    session_id: Optional[str] = None,
) -> None:
    """Log a session spawn event.

    Args:
        logger: Logger to use.
        worker_id: Worker ID.
        worker_name: Worker name.
        provider: Session provider.
        session_id: Session ID if available.
    """
    logger.info(
        "Session spawned: worker=%s (%s), provider=%s, session_id=%s",
        worker_name,
        worker_id,
        provider,
        session_id or "pending",
    )


def log_session_stop(
    logger: logging.Logger,
    worker_id: str,
    worker_name: str,
    force: bool = False,
) -> None:
    """Log a session stop event.

    Args:
        logger: Logger to use.
        worker_id: Worker ID.
        worker_name: Worker name.
        force: Whether this was a forced stop.
    """
    mode = "forced" if force else "graceful"
    logger.info(
        "Session stopped (%s): worker=%s (%s)",
        mode,
        worker_name,
        worker_id,
    )


def log_budget_check(
    logger: logging.Logger,
    worker_id: str,
    required: float,
    available: float,
    allowed: bool,
) -> None:
    """Log a budget check event.

    Args:
        logger: Logger to use.
        worker_id: Worker ID.
        required: Required amount.
        available: Available amount.
        allowed: Whether the check passed.
    """
    status = "approved" if allowed else "denied"
    logger.debug(
        "Budget check %s: worker=%s, required=$%.4f, available=$%.4f",
        status,
        worker_id,
        required,
        available,
    )


def log_budget_spend(
    logger: logging.Logger,
    worker_id: str,
    amount: float,
    provider: str,
    model: str,
) -> None:
    """Log a budget spend event.

    Args:
        logger: Logger to use.
        worker_id: Worker ID.
        amount: Amount spent.
        provider: Provider name.
        model: Model name.
    """
    logger.info(
        "Budget spend: worker=%s, amount=$%.4f, provider=%s, model=%s",
        worker_id,
        amount,
        provider,
        model,
    )


def log_worker_lifecycle(
    logger: logging.Logger,
    worker_id: str,
    worker_name: str,
    old_status: str,
    new_status: str,
) -> None:
    """Log a worker lifecycle change.

    Args:
        logger: Logger to use.
        worker_id: Worker ID.
        worker_name: Worker name.
        old_status: Previous lifecycle status.
        new_status: New lifecycle status.
    """
    logger.info(
        "Worker lifecycle: %s (%s) %s -> %s",
        worker_name,
        worker_id,
        old_status,
        new_status,
    )


def log_org_state_change(
    logger: logging.Logger,
    old_status: str,
    new_status: str,
) -> None:
    """Log an organization state change.

    Args:
        logger: Logger to use.
        old_status: Previous org status.
        new_status: New org status.
    """
    logger.info(
        "Org state change: %s -> %s",
        old_status,
        new_status,
    )
