"""CLI entry point for the qn-bd command.

Wraps the bd (beads) CLI with org context, passing org path and worker ID
to provide permission-aware beads operations for QuinnAI workers.
"""

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

from cli.core.bd_wrapper import BeadPermissionError, run_bd
from cli.core.lifecycle import LifecycleError


_TMUX_SESSION_PATTERN = re.compile(r"^qn-(wrkr-[a-zA-Z0-9_-]+)$")


def _resolve_from_tmux() -> tuple[Optional[str], Optional[str]]:
    """Recover (worker_id, org_path) from tmux when env propagation failed.

    Every QuinnAI worker session is named 'qn-wrkr-XXX' by tmux_spawner and
    has QUINN_ORG_PATH in its session env. When claude's Bash tool spawns
    qn-bd inside the session, the bash subprocess inherits $TMUX, so:
      - 'tmux display-message -p #S' → 'qn-wrkr-XXX' (worker id)
      - 'tmux show-environment QUINN_ORG_PATH' → 'QUINN_ORG_PATH=/path' (org)

    Bullet-proof against env scrubbing through intermediate shells
    (quinn-ai-3gwh).
    """
    if not os.environ.get("TMUX"):
        return None, None
    worker_id: Optional[str] = None
    org_path: Optional[str] = None
    try:
        r = subprocess.run(
            ["tmux", "display-message", "-p", "#S"],
            capture_output=True, text=True, timeout=2,
        )
        if r.returncode == 0:
            m = _TMUX_SESSION_PATTERN.match(r.stdout.strip())
            if m:
                worker_id = m.group(1)
        r = subprocess.run(
            ["tmux", "show-environment", "QUINN_ORG_PATH"],
            capture_output=True, text=True, timeout=2,
        )
        if r.returncode == 0:
            line = r.stdout.strip()
            if "=" in line:
                key, _, value = line.partition("=")
                if key == "QUINN_ORG_PATH" and value:
                    org_path = value
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        pass
    return worker_id, org_path


def main():
    """Entry point for qn-bd command.

    Passes all arguments to bd with org context.
    Uses explicit CLI arguments for configuration, with env var fallback.
    """
    import argparse

    # Parse our arguments separately from bd arguments
    parser = argparse.ArgumentParser(
        description="Run beads with org context",
        add_help=False,  # Don't intercept --help, pass to bd
    )
    parser.add_argument(
        "--org-path",
        type=Path,
        default=os.environ.get("QUINN_ORG_PATH"),
        help="Path to org folder. Falls back to $QUINN_ORG_PATH, then to tmux session env.",
    )
    parser.add_argument(
        "--worker-id",
        default=os.environ.get("QUINN_WORKER_ID"),
        help="Worker ID. Falls back to $QUINN_WORKER_ID, then to tmux session name.",
    )

    # Parse known args, pass rest to bd
    our_args, bd_args = parser.parse_known_args()

    # Tmux fallback for both fields when env didn't propagate.
    if our_args.org_path is None or our_args.worker_id is None:
        tmux_worker, tmux_org = _resolve_from_tmux()
        if our_args.worker_id is None and tmux_worker is not None:
            our_args.worker_id = tmux_worker
        if our_args.org_path is None and tmux_org is not None:
            our_args.org_path = Path(tmux_org)

    # Validate org_path
    if not our_args.org_path:
        print(
            "Error: org_path required. Use --org-path, set QUINN_ORG_PATH, "
            "or run inside a tmux session named 'qn-wrkr-XXX' (auto-detected).",
            file=sys.stderr,
        )
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
