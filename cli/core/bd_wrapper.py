"""
Beads (bd) wrapper for QuinnAI workers.

Provides org-aware beads integration by:
1. Setting BEADS_DIR to the org's .beads directory
2. Adding worker context to beads operations
3. Executing the bundled bd binary with proper environment

Workers use this via `qn-bd` or programmatically via run_bd().
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional


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
    org_path: Optional[Path] = None,
    worker_id: Optional[str] = None,
    capture_output: bool = False,
) -> subprocess.CompletedProcess:
    """Run beads command with org context.

    Sets up environment for org-aware beads operation and executes
    the bd binary with the given arguments.

    Args:
        args: Arguments to pass to bd command
        org_path: Path to org folder (uses QUINN_ORG_PATH if not provided)
        worker_id: Worker ID (uses QUINN_WORKER_ID if not provided)
        capture_output: If True, capture stdout/stderr

    Returns:
        CompletedProcess with result

    Raises:
        FileNotFoundError: If bd binary not found
        ValueError: If org_path not provided and QUINN_ORG_PATH not set
    """
    # Get org path
    if org_path is None:
        org_path_str = os.environ.get("QUINN_ORG_PATH")
        if not org_path_str:
            raise ValueError(
                "org_path not provided and QUINN_ORG_PATH not set"
            )
        org_path = Path(org_path_str)

    # Get worker ID
    if worker_id is None:
        worker_id = os.environ.get("QUINN_WORKER_ID")

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
    """
    import sys

    # Get args (skip script name)
    args = sys.argv[1:]

    try:
        result = run_bd(args)
        sys.exit(result.returncode)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("Set QUINN_ORG_PATH or use --org-path option", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
