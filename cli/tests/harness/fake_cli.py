#!/usr/bin/env python3
"""Fake CLI agent — controllable stand-in for `claude` / `codex` / etc.

Runs as the `command` in a real SessionConfig so Layer-2 tests can spawn an
actual tmux session and verify QuinnAI's tmux integration without touching a
real LLM CLI (no API costs, no auth).

Behaviors (stdlib only — must run with the venv's python and nothing else):
- Prints a banner with worker_id (from QUINN_WORKER_ID env var if set, else --worker arg)
- Sleeps in a configurable loop (default 0.5s); each tick prints a timestamped heartbeat
- Reads stdin line-by-line, echoes each line prefixed with "ECHO: "
- Exits cleanly on SIGTERM / SIGINT
- Optional --crash-after N seconds: exit(42) after N seconds (for crash-path tests)
- Optional --silent: don't print heartbeats (just banner + stdin echo)
- Optional --max-iters N: exit cleanly after N heartbeats (for finite-run tests)

Invocation as a session:
    python -m cli.tests.harness.fake_cli [--worker WID] [--interval 0.5] [--crash-after N]
"""

import argparse
import os
import signal
import sys
import threading
import time
from datetime import datetime


_should_stop = threading.Event()


def _handle_signal(signum, frame):
    _should_stop.set()


def _stdin_echo_loop():
    """Read stdin, echo each line prefixed. Stops when stdin closes or signal."""
    try:
        for line in sys.stdin:
            if _should_stop.is_set():
                break
            sys.stdout.write(f"ECHO: {line}")
            sys.stdout.flush()
    except (KeyboardInterrupt, BrokenPipeError):
        pass


def main():
    parser = argparse.ArgumentParser(description="QuinnAI fake CLI agent for tests")
    parser.add_argument("--worker", default=None, help="Worker id (overrides QUINN_WORKER_ID)")
    parser.add_argument("--interval", type=float, default=0.5, help="Seconds between heartbeats")
    parser.add_argument("--crash-after", type=float, default=None, help="Exit(42) after N seconds")
    parser.add_argument("--silent", action="store_true", help="No heartbeat output")
    parser.add_argument("--max-iters", type=int, default=None, help="Exit cleanly after N ticks")

    args = parser.parse_args()

    worker_id = args.worker or os.environ.get("QUINN_WORKER_ID", "unknown")

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    # Banner — first thing tests look for
    print(f"FAKE-CLI: ready worker={worker_id} pid={os.getpid()}", flush=True)

    # Background stdin echo so tests can drive input via send-keys
    stdin_thread = threading.Thread(target=_stdin_echo_loop, daemon=True)
    stdin_thread.start()

    start_time = time.time()
    iteration = 0
    try:
        while not _should_stop.is_set():
            elapsed = time.time() - start_time
            if args.crash_after is not None and elapsed >= args.crash_after:
                print(f"FAKE-CLI: crash-after triggered at t={elapsed:.2f}s", flush=True)
                sys.exit(42)
            if args.max_iters is not None and iteration >= args.max_iters:
                print(f"FAKE-CLI: max-iters reached", flush=True)
                break

            if not args.silent:
                ts = datetime.now().isoformat(timespec="seconds")
                print(f"FAKE-CLI: heartbeat t={ts} iter={iteration}", flush=True)
            iteration += 1
            _should_stop.wait(args.interval)
    finally:
        print(f"FAKE-CLI: exit worker={worker_id}", flush=True)


if __name__ == "__main__":
    main()
