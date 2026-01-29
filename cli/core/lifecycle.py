"""
Lifecycle state validation for beads.

Enforces valid state transitions based on bead type configuration.
Validates that beads can only be closed when in terminal states.

Lifecycle rules are loaded in this priority order:
1. Database (org-specific lifecycle_configs table) - highest priority
2. config/lifecycle.yaml (project-specific customization) - medium priority
3. Hardcoded constants (LIFECYCLE_STATES) - fallback

This allows each org to customize their lifecycle states without modifying code.
"""

import json
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from shared.enums import BeadType

from .constants import LIFECYCLE_INITIAL_STATES, LIFECYCLE_STATES

_logger = logging.getLogger(__name__)


# Cache for loaded lifecycle config
_lifecycle_config_cache: dict | None = None
_db_path: Optional[Path] = None


def _get_config_path() -> Path:
    """Get the path to lifecycle.yaml config file."""
    # Config lives in cli/config/lifecycle.yaml
    return Path(__file__).parent.parent / "config" / "lifecycle.yaml"


def _load_lifecycle_config() -> dict:
    """Load lifecycle configuration from YAML file.

    Returns:
        Dict with bead type configurations, or empty dict if file not found.
    """
    global _lifecycle_config_cache

    if _lifecycle_config_cache is not None:
        return _lifecycle_config_cache

    config_path = _get_config_path()
    if not config_path.exists():
        _lifecycle_config_cache = {}
        return _lifecycle_config_cache

    try:
        import yaml
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
            _lifecycle_config_cache = data.get("bead_types", {})
            return _lifecycle_config_cache
    except ImportError:
        # yaml not available, use hardcoded defaults
        _lifecycle_config_cache = {}
        return _lifecycle_config_cache
    except (OSError, ValueError) as e:
        # Config file malformed or not accessible, use hardcoded defaults
        _logger.debug(f"Failed to load lifecycle config from file: {e}")
        _lifecycle_config_cache = {}
        return _lifecycle_config_cache


def _load_from_database(bead_type: str) -> Optional[dict]:
    """Load lifecycle config from database table.

    Args:
        bead_type: The bead type to load config for

    Returns:
        Config dict or None if not found in database
    """
    if _db_path is None:
        return None

    try:
        from .db import open_database
        from .queries import get_lifecycle_config

        db = open_database(_db_path)
        try:
            config_json = get_lifecycle_config(db, bead_type)
            if config_json:
                return json.loads(config_json)
        finally:
            db.close()
    except (sqlite3.Error, json.JSONDecodeError, OSError) as e:
        # Database error, fall through to other sources
        _logger.debug(f"Failed to load lifecycle config from database: {e}")
        return None

    return None


def _get_lifecycle_for_type(bead_type: str) -> dict:
    """Get lifecycle configuration for a specific bead type.

    Tries in priority order:
    1. Database (org-specific)
    2. YAML file (project-specific)
    3. Hardcoded constants (fallback)

    Args:
        bead_type: The bead type (task, bug, feature, etc.)

    Returns:
        Dict with states, terminal_states, initial_state, transitions
    """
    # Try database first (highest priority - org-specific)
    db_config = _load_from_database(bead_type)
    if db_config:
        return {
            "states": db_config.get("states", []),
            "terminal": db_config.get("terminal_states", []),
            "initial": db_config.get("initial_state", db_config.get("states", ["open"])[0]),
            "transitions": db_config.get("transitions", {}),
        }

    # Try YAML config (medium priority - project-specific)
    yaml_config = _load_lifecycle_config()
    if bead_type in yaml_config:
        cfg = yaml_config[bead_type]
        return {
            "states": cfg.get("states", []),
            "terminal": cfg.get("terminal_states", []),
            "initial": cfg.get("initial_state", cfg.get("states", ["open"])[0]),
            "transitions": cfg.get("transitions", {}),
        }

    # Try default from YAML
    if "default" in yaml_config:
        cfg = yaml_config["default"]
        return {
            "states": cfg.get("states", []),
            "terminal": cfg.get("terminal_states", []),
            "initial": cfg.get("initial_state", cfg.get("states", ["open"])[0]),
            "transitions": cfg.get("transitions", {}),
        }

    # Try database default (org-specific default)
    db_default = _load_from_database("default")
    if db_default:
        return {
            "states": db_default.get("states", []),
            "terminal": db_default.get("terminal_states", []),
            "initial": db_default.get("initial_state", db_default.get("states", ["open"])[0]),
            "transitions": db_default.get("transitions", {}),
        }

    # Fall back to hardcoded constants (lowest priority - built-in defaults)
    config = LIFECYCLE_STATES.get(bead_type, LIFECYCLE_STATES["default"])
    initial = LIFECYCLE_INITIAL_STATES.get(
        bead_type, LIFECYCLE_INITIAL_STATES["default"]
    )
    return {
        "states": config["states"],
        "terminal": config["terminal"],
        "initial": initial,
        "transitions": config["transitions"],
    }


def set_database_path(db_path: Path) -> None:
    """Set the database path for loading lifecycle configs.

    Args:
        db_path: Path to quinn.db
    """
    global _db_path
    _db_path = db_path
    clear_lifecycle_cache()


def clear_lifecycle_cache() -> None:
    """Clear the cached lifecycle configuration.

    Call this if the config file or database has been modified and needs to be reloaded.
    """
    global _lifecycle_config_cache
    _lifecycle_config_cache = None


class LifecycleError(Exception):
    """Base exception for lifecycle validation errors."""

    pass


class InvalidStateTransitionError(LifecycleError):
    """Raised when attempting an invalid state transition."""

    def __init__(
        self,
        bead_id: str,
        bead_type: str,
        current_state: str,
        target_state: str,
        allowed_states: list[str],
    ):
        self.bead_id = bead_id
        self.bead_type = bead_type
        self.current_state = current_state
        self.target_state = target_state
        self.allowed_states = allowed_states

        if allowed_states:
            allowed_str = ", ".join(allowed_states)
            message = (
                f"Cannot transition bead '{bead_id}' from '{current_state}' to '{target_state}'. "
                f"Allowed transitions: {allowed_str}"
            )
        else:
            message = (
                f"Cannot transition bead '{bead_id}' from '{current_state}'. "
                f"State '{current_state}' is terminal."
            )
        super().__init__(message)


class CannotCloseBeadError(LifecycleError):
    """Raised when attempting to close a bead in a non-terminal state."""

    def __init__(
        self,
        bead_id: str,
        bead_type: str,
        current_state: str,
        terminal_states: list[str],
    ):
        self.bead_id = bead_id
        self.bead_type = bead_type
        self.current_state = current_state
        self.terminal_states = terminal_states

        terminal_str = ", ".join(terminal_states)
        # Provide actionable guidance
        if bead_type == BeadType.TASK.value:
            if current_state == "review":
                guidance = "Complete the review first."
            elif current_state == "implementation":
                guidance = "Move to review state before closing."
            elif current_state == "planning":
                guidance = "Begin implementation or reject the task."
            elif current_state == "investigation":
                guidance = "Complete investigation and move to planning."
            else:
                guidance = f"Move to a terminal state: {terminal_str}"
        elif bead_type == BeadType.BUG.value:
            if current_state == "review":
                guidance = "Complete the fix review."
            elif current_state == "fixing":
                guidance = "Submit for review or mark as wontfix."
            elif current_state == "investigation":
                guidance = "Move to fixing or mark as wontfix/duplicate."
            elif current_state == "triage":
                guidance = "Triage the bug first."
            else:
                guidance = f"Move to a terminal state: {terminal_str}"
        elif bead_type == BeadType.FEATURE.value:
            if current_state == "review":
                guidance = "Complete the feature review."
            elif current_state == "implementation":
                guidance = "Submit for review or defer the feature."
            elif current_state == "design":
                guidance = "Begin implementation or reject/defer."
            elif current_state == "discovery":
                guidance = "Complete discovery and move to design."
            else:
                guidance = f"Move to a terminal state: {terminal_str}"
        else:
            guidance = f"Move to a terminal state: {terminal_str}"

        message = (
            f"Cannot close bead '{bead_id}': in '{current_state}' state. {guidance}"
        )
        super().__init__(message)


class BeadBlockedError(LifecycleError):
    """Raised when attempting to close a bead that has unresolved dependencies."""

    def __init__(
        self,
        bead_id: str,
        blocking_beads: list[str],
    ):
        self.bead_id = bead_id
        self.blocking_beads = blocking_beads

        blockers_str = ", ".join(blocking_beads[:5])
        if len(blocking_beads) > 5:
            blockers_str += f" (and {len(blocking_beads) - 5} more)"

        message = (
            f"Cannot close bead '{bead_id}': blocked by {len(blocking_beads)} "
            f"unresolved dependencies: {blockers_str}. "
            "Resolve or close blocking beads first."
        )
        super().__init__(message)


class InvalidStateError(LifecycleError):
    """Raised when a state is not valid for a bead type."""

    def __init__(
        self,
        bead_id: str,
        bead_type: str,
        invalid_state: str,
        valid_states: list[str],
    ):
        self.bead_id = bead_id
        self.bead_type = bead_type
        self.invalid_state = invalid_state
        self.valid_states = valid_states

        valid_str = ", ".join(valid_states)
        message = (
            f"Invalid state '{invalid_state}' for {bead_type} bead '{bead_id}'. "
            f"Valid states: {valid_str}"
        )
        super().__init__(message)


@dataclass
class LifecycleConfig:
    """Configuration for a bead type's lifecycle."""

    bead_type: str
    states: list[str]
    terminal: list[str]
    transitions: dict[str, list[str]]

    @classmethod
    def for_type(cls, bead_type: str) -> "LifecycleConfig":
        """Get lifecycle configuration for a bead type.

        Loads from config/lifecycle.yaml if available, otherwise uses
        hardcoded defaults from constants.py.

        Args:
            bead_type: The bead type (task, bug, feature, etc.)

        Returns:
            LifecycleConfig for the bead type
        """
        config = _get_lifecycle_for_type(bead_type)
        return cls(
            bead_type=bead_type,
            states=config["states"],
            terminal=config["terminal"],
            transitions=config["transitions"],
        )

    def get_initial_state(self) -> str:
        """Get the initial state for this bead type.

        Returns:
            Initial state name
        """
        config = _get_lifecycle_for_type(self.bead_type)
        return config["initial"]

    def is_valid_state(self, state: str) -> bool:
        """Check if a state is valid for this bead type.

        Args:
            state: State to check

        Returns:
            True if state is valid
        """
        all_states = set(self.states) | set(self.terminal)
        return state in all_states

    def is_terminal(self, state: str) -> bool:
        """Check if a state is a terminal state.

        Args:
            state: State to check

        Returns:
            True if state is terminal
        """
        return state in self.terminal

    def get_allowed_transitions(self, current_state: str) -> list[str]:
        """Get list of states that can be transitioned to from current state.

        Args:
            current_state: Current state

        Returns:
            List of allowed target states
        """
        return self.transitions.get(current_state, [])

    def can_transition(self, current_state: str, target_state: str) -> bool:
        """Check if a transition from current to target state is allowed.

        Args:
            current_state: Current state
            target_state: Target state

        Returns:
            True if transition is allowed
        """
        allowed = self.get_allowed_transitions(current_state)
        return target_state in allowed


def validate_state_transition(
    bead_id: str,
    bead_type: str,
    current_state: str,
    target_state: str,
) -> None:
    """Validate that a state transition is allowed.

    Args:
        bead_id: Bead identifier
        bead_type: Type of bead (task, bug, feature, etc.)
        current_state: Current lifecycle state
        target_state: Target lifecycle state

    Raises:
        InvalidStateTransitionError: If transition is not allowed
        InvalidStateError: If current or target state is invalid
    """
    config = LifecycleConfig.for_type(bead_type)

    # Check if current state is valid
    if not config.is_valid_state(current_state):
        all_states = list(set(config.states) | set(config.terminal))
        raise InvalidStateError(bead_id, bead_type, current_state, all_states)

    # Check if target state is valid
    if not config.is_valid_state(target_state):
        all_states = list(set(config.states) | set(config.terminal))
        raise InvalidStateError(bead_id, bead_type, target_state, all_states)

    # Check if transition is allowed
    if not config.can_transition(current_state, target_state):
        allowed = config.get_allowed_transitions(current_state)
        raise InvalidStateTransitionError(
            bead_id, bead_type, current_state, target_state, allowed
        )


def validate_can_close(
    bead_id: str,
    bead_type: str,
    current_state: str,
) -> None:
    """Validate that a bead can be closed.

    A bead can only be closed when in a terminal state.

    Args:
        bead_id: Bead identifier
        bead_type: Type of bead
        current_state: Current lifecycle state

    Raises:
        CannotCloseBeadError: If bead is not in a terminal state
        InvalidStateError: If current state is invalid
    """
    config = LifecycleConfig.for_type(bead_type)

    # Check if current state is valid
    if not config.is_valid_state(current_state):
        all_states = list(set(config.states) | set(config.terminal))
        raise InvalidStateError(bead_id, bead_type, current_state, all_states)

    # Check if in terminal state
    if not config.is_terminal(current_state):
        raise CannotCloseBeadError(bead_id, bead_type, current_state, config.terminal)


def get_initial_state(bead_type: str) -> str:
    """Get the initial state for a bead type.

    Args:
        bead_type: Type of bead

    Returns:
        Initial state name
    """
    config = LifecycleConfig.for_type(bead_type)
    return config.get_initial_state()


def get_valid_states(bead_type: str) -> list[str]:
    """Get all valid states for a bead type.

    Args:
        bead_type: Type of bead

    Returns:
        List of valid state names
    """
    config = LifecycleConfig.for_type(bead_type)
    return list(set(config.states) | set(config.terminal))


def get_terminal_states(bead_type: str) -> list[str]:
    """Get terminal states for a bead type.

    Args:
        bead_type: Type of bead

    Returns:
        List of terminal state names
    """
    config = LifecycleConfig.for_type(bead_type)
    return config.terminal


def get_next_states(bead_type: str, current_state: str) -> list[str]:
    """Get allowed next states from current state.

    Args:
        bead_type: Type of bead
        current_state: Current state

    Returns:
        List of allowed target states
    """
    config = LifecycleConfig.for_type(bead_type)
    return config.get_allowed_transitions(current_state)


def parse_status_from_args(args: list[str]) -> Optional[str]:
    """Parse the status/state value from bd command arguments.

    Looks for --status or --state flags and extracts the value.

    Args:
        args: Command line arguments

    Returns:
        Status value or None if not found
    """
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("--status", "--state", "-s"):
            # Value is next argument
            if i + 1 < len(args):
                return args[i + 1]
        elif arg.startswith("--status="):
            return arg.split("=", 1)[1]
        elif arg.startswith("--state="):
            return arg.split("=", 1)[1]
        i += 1
    return None


def save_lifecycle_config(db_path: Path, bead_type: str, config: dict) -> None:
    """Save lifecycle configuration to database.

    Args:
        db_path: Path to quinn.db
        bead_type: Bead type to configure (task, bug, feature, etc. or "default")
        config: Configuration dict with states, terminal_states, initial_state, transitions

    Example:
        config = {
            "states": ["open", "in_progress", "review", "done"],
            "terminal_states": ["done", "rejected"],
            "initial_state": "open",
            "transitions": {
                "open": ["in_progress", "rejected"],
                "in_progress": ["review", "rejected"],
                "review": ["done", "in_progress"],
                "done": [],
                "rejected": []
            }
        }
        save_lifecycle_config(db_path, "task", config)
    """
    from .db import open_database

    config_json = json.dumps(config)
    db = open_database(db_path)
    try:
        db.execute(
            """INSERT INTO lifecycle_configs (bead_type, config, updated_at)
               VALUES (?, ?, datetime('now'))
               ON CONFLICT(bead_type) DO UPDATE SET
                   config = excluded.config,
                   updated_at = datetime('now')""",
            (bead_type, config_json),
        )
        db.connection.commit()
    finally:
        db.close()

    # Clear cache so next read gets the updated config
    clear_lifecycle_cache()


def get_lifecycle_config_from_db(db_path: Path, bead_type: str) -> Optional[dict]:
    """Get lifecycle configuration from database.

    Args:
        db_path: Path to quinn.db
        bead_type: Bead type to get config for

    Returns:
        Configuration dict or None if not found
    """
    from .db import open_database
    from .queries import get_lifecycle_config

    db = open_database(db_path)
    try:
        config_json = get_lifecycle_config(db, bead_type)
        if config_json:
            return json.loads(config_json)
        return None
    finally:
        db.close()


def list_lifecycle_configs_from_db(db_path: Path) -> dict[str, dict]:
    """List all lifecycle configurations from database.

    Args:
        db_path: Path to quinn.db

    Returns:
        Dict mapping bead_type to configuration dict
    """
    from .db import open_database
    from .queries import get_all_lifecycle_configs

    db = open_database(db_path)
    try:
        config_strings = get_all_lifecycle_configs(db)
        return {bead_type: json.loads(config_json) for bead_type, config_json in config_strings.items()}
    finally:
        db.close()
