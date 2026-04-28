"""Canary-specific op handlers — registered into Tier 2's OPS registry.

These ops only make sense in a live LLM context where the CEO session can
actually respond to messages. In Tier 2 (FakeSpawner) they're no-ops.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from shared.testing.scenarios import OPS, PREDICATES

if TYPE_CHECKING:
    from shared.testing.scenarios import ScenarioRun


def op_start_org(run: "ScenarioRun", op: dict[str, Any]) -> None:
    """qn org start — boots the CEO session via the configured provider."""
    from shared.testing.scenarios.ops import _run_qn

    _run_qn(run, ["org", "start"])


def op_send_to_worker(run: "ScenarioRun", op: dict[str, Any]) -> None:
    """msgr send — deliver a directive to a worker's inbox."""
    from shared.testing.scenarios.ops import _run_qn

    worker_id = run._resolve_worker_id(op["worker"])
    # Use the msgr CLI; assume direct-message channel @<worker_id>
    args = ["msgr", "send", f"@{worker_id}", op["message"]]
    _run_qn(run, args)


def op_wait_until(run: "ScenarioRun", op: dict[str, Any]) -> None:
    """Poll a predicate until it passes or a per-op timeout elapses.

    YAML form:
      - { op: wait_until, predicate: { kind: worker_count, value: 2 }, timeout_seconds: 240 }
    """
    timeout = op.get("timeout_seconds", 60)
    poll_interval = op.get("poll_interval_seconds", 2)
    predicate = op["predicate"]

    deadline = time.monotonic() + timeout
    last_violation: str | None = None
    while time.monotonic() < deadline:
        last_violation = run.check(predicate)
        if last_violation is None:
            return
        time.sleep(poll_interval)
    raise RuntimeError(
        f"wait_until timed out after {timeout}s; last violation: {last_violation}"
    )


# Register into Tier 2's shared registry. Idempotent — safe to import multiple times.
OPS.setdefault("start_org", op_start_org)
OPS.setdefault("send_to_worker", op_send_to_worker)
OPS.setdefault("wait_until", op_wait_until)
