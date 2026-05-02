"""Detached continuation engine daemon.

Spawned by `qn org start` via subprocess with start_new_session=True.
Runs the ContinuationEngine until the org stops or the process is killed.
Writes its PID to <org>/live/continuation-engine.pid.

Usage (internal — not a user-facing command):
    python -m cli.commands.continuation_daemon --org-path /path/to/org
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="QuinnAI continuation engine daemon")
    parser.add_argument("--org-path", required=True, type=Path)
    parser.add_argument("--poll-interval", type=float, default=None)
    args = parser.parse_args()

    org_path = args.org_path
    pid_file = org_path / "live" / "continuation-engine.pid"

    try:
        from cli.core.continuation_engine import ContinuationEngine
        from cli.core.constants import CONTINUATION_ENGINE_POLL_INTERVAL

        poll_interval = args.poll_interval or CONTINUATION_ENGINE_POLL_INTERVAL
        engine = ContinuationEngine(org_path, poll_interval=poll_interval)
        engine.start()
        print(f"continuation-engine started for {org_path} (poll={poll_interval}s)", flush=True)

        def _shutdown(sig, frame):
            engine.stop()
            pid_file.unlink(missing_ok=True)
            sys.exit(0)

        signal.signal(signal.SIGTERM, _shutdown)
        signal.signal(signal.SIGINT, _shutdown)

        # Keep alive until org stops or we're killed
        while engine.is_running():
            time.sleep(5)
            # Check if org is still running
            try:
                from cli.core.db import open_database, get_org_db_path
                db = open_database(get_org_db_path(org_path))
                row = db.fetchone("SELECT status FROM org_state WHERE id='default'")
                db.close()
                if row and row["status"] not in ("running",):
                    print(f"org status={row['status']}, stopping daemon", flush=True)
                    break
            except Exception:
                pass

        engine.stop()
    except Exception as e:
        print(f"continuation-engine error: {e}", flush=True)
        sys.exit(1)
    finally:
        pid_file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
