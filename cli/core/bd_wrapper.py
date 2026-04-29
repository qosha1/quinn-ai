"""
Beads (bd) wrapper for QuinnAI workers.

Provides org-aware beads integration by:
1. Setting BEADS_DIR to the org's .beads directory
2. Adding worker context to beads operations
3. Checking worker permissions before executing commands
4. Validating lifecycle state transitions before update/close
5. Executing the bundled bd binary with proper environment

Workers use this via `qn-bd` or programmatically via run_bd().
"""

import json
import logging
import os
import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

_logger = logging.getLogger(__name__)

from .constants import (
    BD_COMMAND_PERMISSIONS,
    PERM_LEVEL_NAMES,
    PERM_LEVEL_READ,
    PERM_LEVEL_WRITE,
    BEAD_TYPE_TASK,
    BEAD_TYPE_EPIC,
    BEAD_TYPE_GATE,
    BEAD_TYPE_AGENT,
    BEAD_TYPE_ROLE,
    BEAD_TYPE_RIG,
    BEAD_TYPE_CONVOY,
    BEAD_TYPE_EVENT,
    BEADS_DIR,
    BD_COMMAND_TIMEOUT_SECONDS,
)
from .lifecycle import (
    BeadBlockedError,
    CannotCloseBeadError,
    InvalidStateTransitionError,
    LifecycleError,
    parse_status_from_args,
    validate_can_close,
    validate_state_transition,
)


# Safe pattern for worker IDs - alphanumeric, underscores, hyphens only
SAFE_WORKER_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')


def validate_worker_id(worker_id: str) -> None:
    """Validate worker_id format to prevent injection attacks.

    Args:
        worker_id: Worker ID to validate

    Raises:
        ValueError: If worker_id contains unsafe characters
    """
    if not worker_id:
        raise ValueError("worker_id cannot be empty")
    if len(worker_id) > 128:
        raise ValueError(f"worker_id too long: {len(worker_id)} chars (max 128)")
    if not SAFE_WORKER_ID_PATTERN.match(worker_id):
        raise ValueError(
            f"Invalid worker_id format: '{worker_id}'. "
            "Only alphanumeric characters, underscores, and hyphens allowed."
        )


class BeadPermissionError(Exception):
    """Raised when worker lacks permission for a beads operation."""

    def __init__(
        self,
        worker_id: str,
        command: str,
        required_level: int,
        actual_level: int,
        bead_id: Optional[str] = None,
    ):
        self.worker_id = worker_id
        self.command = command
        self.required_level = required_level
        self.actual_level = actual_level
        self.bead_id = bead_id

        required_name = PERM_LEVEL_NAMES.get(required_level, str(required_level))
        actual_name = PERM_LEVEL_NAMES.get(actual_level, str(actual_level))

        if bead_id:
            message = (
                f"Worker '{worker_id}' lacks permission for '{command}' on bead '{bead_id}'. "
                f"Required: {required_name}, has: {actual_name}"
            )
        else:
            message = (
                f"Worker '{worker_id}' lacks permission for '{command}'. "
                f"Required: {required_name}, has: {actual_name}"
            )
        super().__init__(message)


def _get_command_from_args(args: list[str]) -> Optional[str]:
    """Extract the bd command from arguments.

    Args:
        args: Command line arguments

    Returns:
        Command name or None
    """
    for arg in args:
        if not arg.startswith("-"):
            return arg
    return None


def _get_bead_id_from_args(args: list[str]) -> Optional[str]:
    """Extract bead ID from command arguments.

    Bead IDs follow the command name and look like 'beads-xxxx' or 'quinnai-xxxx'.

    Args:
        args: Command line arguments

    Returns:
        Bead ID or None
    """
    found_command = False
    for arg in args:
        if arg.startswith("-"):
            continue
        if not found_command:
            found_command = True
            continue
        # This might be a bead ID
        if "-" in arg and not arg.startswith("-"):
            return arg
    return None


def _get_bead_info(
    bead_id: str,
    org_path: Path,
) -> Optional[dict]:
    """Get bead information by running bd show --json.

    Args:
        bead_id: Bead identifier
        org_path: Path to org folder

    Returns:
        Dict with bead info (type, status) or None if not found
    """
    try:
        bd_path = get_bundled_bd_path()
    except FileNotFoundError:
        return None

    env = os.environ.copy()
    beads_dir = get_org_beads_dir(org_path)
    env["BEADS_DIR"] = str(beads_dir)

    try:
        result = subprocess.run(
            [str(bd_path), "show", bead_id, "--json"],
            env=env,
            capture_output=True,
            text=True,
            timeout=BD_COMMAND_TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            return None

        # Parse JSON output
        data = json.loads(result.stdout)
        # Get depends_on from relationships
        depends_on = data.get("depends_on", [])
        if not depends_on:
            # Try alternate field names
            deps = data.get("dependencies", {})
            depends_on = deps.get("depends_on", []) or deps.get("blocks", [])
        return {
            "id": data.get("id", bead_id),
            "type": data.get("type", "default"),
            "status": data.get("status", "open"),
            "depends_on": depends_on,
        }
    except subprocess.TimeoutExpired:
        _logger.warning("bd show %s timed out after %ss", bead_id, BD_COMMAND_TIMEOUT_SECONDS)
        return None
    except json.JSONDecodeError:
        _logger.warning("bd show %s returned non-JSON output", bead_id)
        return None
    except Exception:
        _logger.exception("Unexpected failure resolving bead info for %s", bead_id)
        return None


def _get_open_blockers(
    bead_ids: list[str],
    org_path: Path,
) -> list[str]:
    """Check which of the given beads are still open.

    Args:
        bead_ids: List of bead IDs to check
        org_path: Path to org folder

    Returns:
        List of bead IDs that are still open (not closed/done)
    """
    open_blockers = []
    closed_statuses = {"closed", "done", "rejected", "abandoned", "wontfix", "duplicate", "deferred"}

    for bead_id in bead_ids:
        bead_info = _get_bead_info(bead_id, org_path)
        if bead_info:
            status = bead_info.get("status", "open").lower()
            if status not in closed_statuses:
                open_blockers.append(bead_id)
        # If we can't get bead info, assume it's blocking to be safe

    return open_blockers


def check_lifecycle_transition(
    args: list[str],
    org_path: Path,
    skip_check: bool = False,
) -> None:
    """Check if lifecycle state transition is valid.

    Validates:
    - State transitions on update commands
    - Close operations only allowed in terminal states

    Args:
        args: bd command arguments
        org_path: Path to org folder
        skip_check: If True, skip validation

    Raises:
        InvalidStateTransitionError: If state transition is not allowed
        CannotCloseBeadError: If closing bead not in terminal state
    """
    if skip_check:
        return

    command = _get_command_from_args(args)
    if command not in ("update", "close"):
        return

    bead_id = _get_bead_id_from_args(args)
    if not bead_id:
        return

    # Get current bead info
    bead_info = _get_bead_info(bead_id, org_path)
    if not bead_info:
        # Bead not found or error - let bd handle the error
        return

    bead_type = bead_info["type"]
    current_state = bead_info["status"]

    if command == "close":
        # Validate close is allowed (terminal state check)
        validate_can_close(bead_id, bead_type, current_state)

        # Check for blocking dependencies (can't close if blocked)
        depends_on = bead_info.get("depends_on", [])
        if depends_on:
            # Check if any blocking beads are still open
            blocking_beads = _get_open_blockers(depends_on, org_path)
            if blocking_beads:
                raise BeadBlockedError(bead_id, blocking_beads)

    elif command == "update":
        # Check if status is being updated
        target_state = parse_status_from_args(args)
        if target_state and target_state != current_state:
            # Validate state transition
            validate_state_transition(bead_id, bead_type, current_state, target_state)


def check_bd_permission(
    worker_id: str,
    args: list[str],
    org_path: Path,
    skip_check: bool = False,
) -> None:
    """Check if worker has permission to execute bd command.

    Args:
        worker_id: Worker ID
        args: bd command arguments
        org_path: Path to org folder
        skip_check: If True, skip permission check (for admin operations)

    Raises:
        BeadPermissionError: If worker lacks required permission
    """
    if skip_check:
        return

    command = _get_command_from_args(args)
    if command is None:
        # No command - just help text, allow it
        return

    required_level = BD_COMMAND_PERMISSIONS.get(command)
    if required_level is None:
        # Unknown command - default to read permission
        required_level = PERM_LEVEL_READ

    # For read-only commands, all workers have implicit read access
    if required_level <= PERM_LEVEL_READ:
        return

    # For write/admin commands, check against permissions table
    bead_id = _get_bead_id_from_args(args)

    # Import here to avoid circular imports
    from .db import open_database, get_org_db_path
    from .queries import get_effective_permission, get_permission_for_grantee

    db_path = get_org_db_path(org_path)
    if not db_path.exists():
        # No database - allow operation (org not initialized)
        return

    db = open_database(db_path)
    try:
        actual_level = 0  # Default to no permission

        if bead_id:
            # Check permission for specific bead
            effective = get_effective_permission(db, worker_id, bead_id)
            if effective:
                actual_level = effective.level
            else:
                # Check global permission for worker
                global_perm = get_permission_for_grantee(db, None, "worker", worker_id)
                if global_perm:
                    actual_level = global_perm.level
        else:
            # No bead ID - check global permission
            global_perm = get_permission_for_grantee(db, None, "worker", worker_id)
            if global_perm:
                actual_level = global_perm.level

        if actual_level < required_level:
            raise BeadPermissionError(
                worker_id=worker_id,
                command=command,
                required_level=required_level,
                actual_level=actual_level,
                bead_id=bead_id,
            )

    finally:
        db.close()


def get_bundled_bd_path(prefer_system: bool = False) -> Path:
    """Locate the bd binary.

    Resolution order:
        1. (if prefer_system) system PATH via shutil.which("bd")
        2. cli/bin/bd (or cli/bin/bd.exe on Windows) — explicit bundle
        3. cli/bin/{platform}-{arch}/bd — repo dev builds
        4. system PATH via shutil.which("bd")

    Args:
        prefer_system: If True, prefer the system-installed bd over the
            bundled one. Used for dolt-mode orgs since the bundled bd
            (0.43.x) doesn't fully support dolt --sandbox; modern system
            bd (1.x+) does. (quinn-ai-k9ff)

    Raises:
        FileNotFoundError: If no bd binary can be located.
    """
    import shutil

    if prefer_system:
        system_bd = shutil.which("bd")
        if system_bd:
            return Path(system_bd)

    cli_dir = Path(__file__).parent.parent
    bin_dir = cli_dir / "bin"
    bd_name = "bd.exe" if sys.platform == "win32" else "bd"

    candidates = [bin_dir / bd_name]

    # Repo-dev layout: cli/bin/{platform}-{arch}/bd
    arch = platform.machine().lower()
    if arch == "x86_64":
        arch = "amd64"
    elif arch == "aarch64":
        arch = "arm64"
    os_name = "darwin" if sys.platform == "darwin" else (
        "linux" if sys.platform.startswith("linux") else
        "windows" if sys.platform == "win32" else sys.platform
    )
    candidates.append(bin_dir / f"{os_name}-{arch}" / bd_name)

    for c in candidates:
        if c.exists():
            return c

    system_bd = shutil.which("bd")
    if system_bd:
        return Path(system_bd)

    raise FileNotFoundError(
        "Beads binary 'bd' not found on PATH. Install it from "
        "https://github.com/steveyegge/beads (e.g. 'brew install bd' on macOS) "
        "and ensure it is on your shell's PATH."
    )


def get_org_beads_dir(org_path: Path) -> Path:
    """Get the beads directory for an org.

    Args:
        org_path: Path to org folder

    Returns:
        Path to org's .beads directory
    """
    return org_path / BEADS_DIR


def is_dolt_backend(beads_dir: Path) -> bool:
    """Detect whether an org's beads is in dolt-embedded mode.

    Reads .beads/metadata.json's "backend" field. Default for new orgs
    created by `qn org init` is dolt; legacy orgs (or test fixtures with
    no metadata.json) fall through to sqlite-style behaviour.

    Returns False on missing/unreadable metadata.json (legacy/test path).
    """
    metadata_path = beads_dir / "metadata.json"
    if not metadata_path.exists():
        return False
    try:
        meta = json.loads(metadata_path.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return meta.get("backend") == "dolt"


class OKRLinkWarning(UserWarning):
    """Warning when work item is created without OKR link."""

    pass


class OKRLinkRequiredError(Exception):
    """Error when work item requires OKR link but none provided."""

    def __init__(self, bead_type: str):
        self.bead_type = bead_type
        message = (
            f"Cannot create {bead_type}: OKR link required. "
            "Use --deps 'serves:<okr-id>' to link to an OKR objective."
        )
        super().__init__(message)


def _get_default_config_path() -> Path:
    """Get path to default config using importlib.resources.

    Falls back to __file__-based path if resources are not available.
    This supports both development (editable install) and packaged installs.

    Returns:
        Path to the config directory
    """
    from importlib import resources

    try:
        # Use importlib.resources for proper package data access
        with resources.as_file(resources.files("cli.config")) as config_path:
            return config_path
    except (TypeError, ModuleNotFoundError, FileNotFoundError):
        # Fallback for development: use source-relative path
        # FileNotFoundError: config dir exists but isn't a package (no __init__.py)
        return Path(__file__).parent.parent / "config"


def _load_workflow_config(org_path: Path) -> dict:
    """Load workflow configuration from org's workflow.yaml.

    Args:
        org_path: Path to org folder

    Returns:
        Workflow config dict, or empty dict if not found
    """
    import yaml

    # First check org-specific config
    workflow_path = org_path / "config" / "workflow.yaml"
    if not workflow_path.exists():
        # Fall back to package default config
        default_config = _get_default_config_path()
        workflow_path = default_config / "workflow.yaml"
        if not workflow_path.exists():
            return {}

    try:
        with open(workflow_path) as f:
            return yaml.safe_load(f) or {}
    except (OSError, ValueError) as e:
        # Failed to load workflow config - return empty dict
        _logger.debug(f"Failed to load workflow config: {e}")
        return {}


def _parse_deps_from_args(args: list[str]) -> list[str]:
    """Extract --deps values from command arguments.

    Args:
        args: Command line arguments

    Returns:
        List of dependency strings (e.g., ['serves:okr-123', 'blocks:bd-456'])
    """
    deps = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--deps" and i + 1 < len(args):
            # Value is next argument
            deps.extend(args[i + 1].split(","))
            i += 2
        elif arg.startswith("--deps="):
            deps.extend(arg.split("=", 1)[1].split(","))
            i += 1
        else:
            i += 1
    return [d.strip() for d in deps if d.strip()]


def check_okr_linking(
    args: list[str],
    org_path: Path,
    skip_check: bool = False,
) -> None:
    """Check if OKR linking is required for create commands.

    Args:
        args: bd command arguments
        org_path: Path to org folder
        skip_check: If True, skip OKR check

    Raises:
        OKRLinkRequiredError: If strict_mode and no OKR link provided

    Warnings:
        OKRLinkWarning: If require_okr_link but not strict_mode
    """
    import warnings

    if skip_check or not args:
        return

    # Only check 'create' commands
    command = args[0] if args else ""
    if command not in ("create", "new"):
        return

    # Load workflow config
    config = _load_workflow_config(org_path)
    okr_config = config.get("okr_linking", {})

    if not okr_config.get("require_okr_link", False):
        return

    # Check if deps include a 'serves' relationship
    deps = _parse_deps_from_args(args)
    has_okr_link = any(d.startswith("serves:") for d in deps)

    if has_okr_link:
        return

    # Get bead type from args
    bead_type = BEAD_TYPE_TASK  # default
    for i, arg in enumerate(args):
        if arg in ("-t", "--type") and i + 1 < len(args):
            bead_type = args[i + 1]
            break
        elif arg.startswith("--type="):
            bead_type = arg.split("=", 1)[1]
            break

    # Skip for epics and non-work types
    if bead_type in (BEAD_TYPE_EPIC, BEAD_TYPE_GATE, BEAD_TYPE_AGENT, BEAD_TYPE_ROLE, BEAD_TYPE_RIG, BEAD_TYPE_CONVOY, BEAD_TYPE_EVENT):
        return

    if okr_config.get("strict_mode", False):
        raise OKRLinkRequiredError(bead_type)
    else:
        warnings.warn(
            f"Creating {bead_type} without OKR link. "
            "Consider using --deps 'serves:<okr-id>' to link to an objective.",
            OKRLinkWarning,
            stacklevel=2,
        )


def run_bd(
    args: list[str],
    org_path: Path,
    worker_id: Optional[str] = None,
    capture_output: bool = False,
    skip_permission_check: bool = False,
    skip_lifecycle_check: bool = False,
    skip_okr_check: bool = False,
    timeout: Optional[float] = None,
) -> subprocess.CompletedProcess:
    """Run beads command with org context.

    Sets up environment for org-aware beads operation and executes
    the bd binary with the given arguments.

    Follows "No Config Discovery" principle - org_path must be passed
    explicitly, not discovered from environment variables.

    Args:
        args: Arguments to pass to bd command
        org_path: Path to org folder (required, no env var fallback)
        worker_id: Worker ID for permission checking (optional)
        capture_output: If True, capture stdout/stderr
        skip_permission_check: If True, skip permission check (admin use only)
        skip_lifecycle_check: If True, skip lifecycle validation (admin use only)
        skip_okr_check: If True, skip OKR link requirement check

    Returns:
        CompletedProcess with result

    Raises:
        FileNotFoundError: If bd binary not found
        BeadPermissionError: If worker lacks required permission
        InvalidStateTransitionError: If state transition is not allowed
        CannotCloseBeadError: If closing bead not in terminal state
        OKRLinkRequiredError: If strict_mode and work item lacks OKR link
        ValueError: If worker_id format is invalid
    """

    # Validate worker_id format if provided (security)
    if worker_id:
        validate_worker_id(worker_id)

    # Check permissions before executing
    if worker_id and not skip_permission_check:
        check_bd_permission(worker_id, args, org_path)

    # Validate lifecycle transitions before executing
    if not skip_lifecycle_check:
        check_lifecycle_transition(args, org_path)

    # Check OKR linking requirement for create commands
    if not skip_okr_check:
        check_okr_linking(args, org_path)

    # Get bd binary. Dolt-mode orgs need a 1.x+ bd; the bundled 0.43.x bd
    # doesn't fully support dolt with --sandbox. Prefer system bd in that
    # case. (quinn-ai-k9ff)
    beads_dir_for_detection = get_org_beads_dir(org_path)
    dolt_mode = is_dolt_backend(beads_dir_for_detection)
    bd_path = get_bundled_bd_path(prefer_system=dolt_mode)

    # Set up environment
    env = os.environ.copy()

    # Point beads to org's .beads directory
    beads_dir = beads_dir_for_detection
    env["BEADS_DIR"] = str(beads_dir)

    # Dolt-mode orgs (the default since 1.0+) keep the actual database in
    # .beads/embeddeddolt/, not .beads/beads.db. Passing --db=beads.db there
    # opens a separate, empty/stale sqlite that lacks issue_prefix config —
    # bd then refuses writes ("issue_prefix config is missing"). For dolt
    # orgs, drop the --db= override and the BEADS_DB env var; bd auto-
    # discovers the dolt backend from .beads/metadata.json via BEADS_DIR.
    # (quinn-ai-k9ff)
    if not dolt_mode:
        beads_db = beads_dir / "beads.db"
        env["BEADS_DB"] = str(beads_db)

    # Add worker context if available
    if worker_id:
        env["QUINN_WORKER_ID"] = worker_id
        # Set default assignee for new issues
        env["BEADS_ASSIGNEE"] = worker_id

    # Run bd command
    # Use --sandbox mode to bypass daemon. Legacy sqlite orgs also pin the
    # db file via --db=; dolt orgs let bd auto-discover (see above).
    cmd: list[str] = [str(bd_path), "--sandbox"]
    if not dolt_mode:
        cmd.append(f"--db={beads_dir / 'beads.db'}")
    cmd += args

    # NOTE: timeout is opt-in (default None) so user-facing `qn-bd` long-running
    # commands aren't killed prematurely. Programmatic write callers (especially
    # init-time bootstrap-OKR creation) pass a value to dodge bd's intermittent
    # hang under concurrent test load (quinn-ai-5d4).
    if capture_output:
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    else:
        result = subprocess.run(
            cmd,
            env=env,
            timeout=timeout,
        )

    # Record activity signal if command succeeded and worker_id provided
    if result.returncode == 0 and worker_id:
        _record_bead_activity(args, org_path, worker_id)

    return result


def _record_bead_activity(args: list[str], org_path: Path, worker_id: str) -> None:
    """Record activity signal for successful bead operations.

    Args:
        args: bd command arguments
        org_path: Path to org folder
        worker_id: Worker ID
    """
    from .constants import SIGNAL_STRENGTH_BEAD_UPDATE
    from .db import get_org_db_path, open_database
    from .queries.activity import record_activity_signal

    # Only record for write operations
    command = _get_command_from_args(args)
    if command not in ("create", "update", "close", "dep"):
        return

    # Get bead ID if available
    bead_id = _get_bead_id_from_args(args)
    metadata = {"command": command}
    if bead_id:
        metadata["bead_id"] = bead_id

    # Record the signal
    db_path = get_org_db_path(org_path)
    if not db_path.exists():
        return

    db = open_database(db_path)
    try:
        record_activity_signal(
            db=db,
            worker_id=worker_id,
            activity_type="bead_update",
            signal_strength=SIGNAL_STRENGTH_BEAD_UPDATE,
            metadata=metadata,
        )
    finally:
        db.close()
