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
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

from .constants import (
    BD_COMMAND_PERMISSIONS,
    PERM_LEVEL_NAMES,
    PERM_LEVEL_READ,
    PERM_LEVEL_WRITE,
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
            timeout=10,
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
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
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


def get_bundled_bd_path() -> Path:
    """Get path to bundled bd binary.

    Returns:
        Path to bd binary in cli/bin/

    Raises:
        FileNotFoundError: If binary not found
    """
    # Binary is in cli/bin/ relative to this file
    cli_dir = Path(__file__).parent.parent
    bin_dir = cli_dir / "bin"

    # Check for platform-specific binary
    if sys.platform == "win32":
        bd_path = bin_dir / "bd.exe"
    else:
        bd_path = bin_dir / "bd"

    if bd_path.exists():
        return bd_path

    # Fall back to system bd if bundled not found
    import shutil
    system_bd = shutil.which("bd")
    if system_bd:
        return Path(system_bd)

    raise FileNotFoundError(
        "Beads binary not found. Run 'scripts/build-beads.sh' to bundle it."
    )


def get_org_beads_dir(org_path: Path) -> Path:
    """Get the beads directory for an org.

    Args:
        org_path: Path to org folder

    Returns:
        Path to org's .beads directory
    """
    return org_path / ".beads"


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
    except Exception:
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
    bead_type = "task"  # default
    for i, arg in enumerate(args):
        if arg in ("-t", "--type") and i + 1 < len(args):
            bead_type = args[i + 1]
            break
        elif arg.startswith("--type="):
            bead_type = arg.split("=", 1)[1]
            break

    # Skip for epics and non-work types
    if bead_type in ("epic", "gate", "agent", "role", "rig", "convoy", "event"):
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

    # Get bd binary
    bd_path = get_bundled_bd_path()

    # Set up environment
    env = os.environ.copy()

    # Point beads to org's .beads directory
    beads_dir = get_org_beads_dir(org_path)
    beads_db = beads_dir / "beads.db"
    env["BEADS_DIR"] = str(beads_dir)
    env["BEADS_DB"] = str(beads_db)

    # Add worker context if available
    if worker_id:
        env["QUINN_WORKER_ID"] = worker_id
        # Set default assignee for new issues
        env["BEADS_ASSIGNEE"] = worker_id

    # Run bd command
    # Use --sandbox mode to bypass daemon and --db to explicitly specify database
    # This is necessary for isolated testing and when using custom org paths
    cmd = [str(bd_path), "--sandbox", f"--db={beads_db}"] + args

    if capture_output:
        return subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
        )
    else:
        return subprocess.run(
            cmd,
            env=env,
        )


def main():
    """Entry point for qn-bd command.

    Passes all arguments to bd with org context.
    Uses explicit CLI arguments for configuration, with env var fallback.
    """
    import argparse
    import sys

    # Parse our arguments separately from bd arguments
    parser = argparse.ArgumentParser(
        description="Run beads with org context",
        add_help=False,  # Don't intercept --help, pass to bd
    )
    parser.add_argument(
        "--org-path",
        type=Path,
        default=os.environ.get("QUINN_ORG_PATH"),
        help="Path to org folder. Falls back to QUINN_ORG_PATH env var.",
    )
    parser.add_argument(
        "--worker-id",
        default=os.environ.get("QUINN_WORKER_ID"),
        help="Worker ID. Falls back to QUINN_WORKER_ID env var.",
    )

    # Parse known args, pass rest to bd
    our_args, bd_args = parser.parse_known_args()

    # Validate org_path
    if not our_args.org_path:
        print("Error: org_path required. Use --org-path or set QUINN_ORG_PATH.", file=sys.stderr)
        sys.exit(1)

    org_path = Path(our_args.org_path)

    try:
        result = run_bd(
            args=bd_args,
            org_path=org_path,
            worker_id=our_args.worker_id,
        )
        sys.exit(result.returncode)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except BeadPermissionError as e:
        print(f"Permission denied: {e}", file=sys.stderr)
        sys.exit(1)
    except LifecycleError as e:
        print(f"Lifecycle error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
