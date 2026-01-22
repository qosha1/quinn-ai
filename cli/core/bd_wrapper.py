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


def run_bd(
    args: list[str],
    org_path: Path,
    worker_id: Optional[str] = None,
    capture_output: bool = False,
    skip_permission_check: bool = False,
    skip_lifecycle_check: bool = False,
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

    Returns:
        CompletedProcess with result

    Raises:
        FileNotFoundError: If bd binary not found
        BeadPermissionError: If worker lacks required permission
        InvalidStateTransitionError: If state transition is not allowed
        CannotCloseBeadError: If closing bead not in terminal state
    """

    # Check permissions before executing
    if worker_id and not skip_permission_check:
        check_bd_permission(worker_id, args, org_path)

    # Validate lifecycle transitions before executing
    if not skip_lifecycle_check:
        check_lifecycle_transition(args, org_path)

    # Get bd binary
    bd_path = get_bundled_bd_path()

    # Set up environment
    env = os.environ.copy()

    # Point beads to org's .beads directory
    beads_dir = get_org_beads_dir(org_path)
    env["BEADS_DIR"] = str(beads_dir)

    # Add worker context if available
    if worker_id:
        env["QUINN_WORKER_ID"] = worker_id
        # Set default assignee for new issues
        env["BEADS_ASSIGNEE"] = worker_id

    # Run bd command
    cmd = [str(bd_path)] + args

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
