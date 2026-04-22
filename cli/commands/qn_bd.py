"""CLI entry point for the qn-bd command.

Wraps the bd (beads) CLI with org context, passing org path and worker ID
to provide permission-aware beads operations for QuinnAI workers.
"""

import os
import sys
from pathlib import Path

from core.bd_wrapper import BeadPermissionError, run_bd
from core.lifecycle import LifecycleError


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
