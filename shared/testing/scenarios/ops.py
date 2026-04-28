"""Operation handlers — wrap CLI commands or perform direct DB writes."""
from __future__ import annotations

import shutil
import sqlite3
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from .harness import ScenarioRun


# Type alias for an op handler.
OpHandler = Callable[["ScenarioRun", dict[str, Any]], None]


def _run_qn(run: "ScenarioRun", args: list[str]) -> None:
    """Invoke 'qn' via Click's CliRunner inside the scenario."""
    from cli.commands.main import qn

    cli_args = ["--org-path", str(run.org_path)] + args
    result = run.runner.invoke(qn, cli_args, catch_exceptions=False)
    if result.exit_code != 0:
        raise RuntimeError(
            f"qn {' '.join(args)} failed (exit {result.exit_code}):\n"
            f"{result.output}"
        )


def _writable_db(run: "ScenarioRun") -> sqlite3.Connection:
    """Open a write-capable connection for direct DB ops (transitions, etc.)."""
    db_path = run.org_path / "live" / "quinn.db"
    return sqlite3.connect(str(db_path))


# ---------------------------------------------------------------------------
# Op implementations
# ---------------------------------------------------------------------------


def op_init(run: "ScenarioRun", op: dict[str, Any]) -> None:
    setup = run.spec.setup.get("init", {}) or {}
    args = ["org", "init", "--skip-okrs"]
    if "ceo_name" in setup:
        args += ["--ceo-name", setup["ceo_name"]]
    # 'qn org init' does not expose --ceo-role at the CLI by design; the
    # underlying Org.init() Python API still accepts a ceo_role kwarg.
    # Scenario YAML 'ceo_role' is intentionally silently dropped.
    _run_qn(run, args)


def op_hire(run: "ScenarioRun", op: dict[str, Any]) -> None:
    args = [
        "org", "hire",
        "--name", op["name"],
        "--role", op["role"],
        "--manager", op["manager"],
    ]
    if "cost" in op:
        args += ["--cost", str(op["cost"])]
    if "skills" in op:
        args += ["--skills", op["skills"]]
    _run_qn(run, args)


def op_fire(run: "ScenarioRun", op: dict[str, Any]) -> None:
    worker_id = run._resolve_worker_id(op["worker"])
    # --force skips the interactive confirmation prompt; CliRunner has no stdin.
    args = ["org", "fire", worker_id, "--force", "--reason", op.get("reason", "scenario")]
    _run_qn(run, args)


def op_promote(run: "ScenarioRun", op: dict[str, Any]) -> None:
    worker_id = run._resolve_worker_id(op["worker"])
    args = ["org", "promote", worker_id, "--to", op.get("to", "team-lead"), "--force"]
    if "reason" in op:
        args += ["--reason", op["reason"]]
    _run_qn(run, args)


def op_demote(run: "ScenarioRun", op: dict[str, Any]) -> None:
    worker_id = run._resolve_worker_id(op["worker"])
    args = ["org", "demote", worker_id, "--force"]
    if "reason" in op:
        args += ["--reason", op["reason"]]
    _run_qn(run, args)


def op_transition_lifecycle(run: "ScenarioRun", op: dict[str, Any]) -> None:
    """Direct DB push of worker.status."""
    worker_id = run._resolve_worker_id(op["worker"])
    target = op["to"]
    conn = _writable_db(run)
    try:
        conn.execute(
            "UPDATE workers SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (target, worker_id),
        )
        conn.commit()
    finally:
        conn.close()


def op_transition_runtime(run: "ScenarioRun", op: dict[str, Any]) -> None:
    """Direct DB push of worker_state.runtime_status."""
    worker_id = run._resolve_worker_id(op["worker"])
    target = op["to"]
    conn = _writable_db(run)
    try:
        conn.execute(
            "INSERT INTO worker_state (worker_id, runtime_status) VALUES (?, ?) "
            "ON CONFLICT(worker_id) DO UPDATE SET runtime_status=excluded.runtime_status, "
            "updated_at=CURRENT_TIMESTAMP",
            (worker_id, target),
        )
        conn.commit()
    finally:
        conn.close()


def op_create_okr(run: "ScenarioRun", op: dict[str, Any]) -> None:
    """Create an OKR via 'qn org okr set'. OKRs are stored as beads of type 'okr'."""
    args = ["org", "okr", "set", "--title", op["objective"]]
    if "owner" in op:
        worker_id = run._resolve_worker_id(op["owner"])
        args += ["--owner", worker_id]
    if "description" in op:
        args += ["--description", op["description"]]
    _run_qn(run, args)


def op_assign_kr(run: "ScenarioRun", op: dict[str, Any]) -> None:
    """Add or update a key result on an OKR via 'qn org okr update-kr'."""
    args = [
        "org", "okr", "update-kr",
        op["okr"],  # OKR id is positional
        "--metric", op.get("kr", op.get("metric", "kr")),
        "--target", str(op.get("target", 1)),
    ]
    _run_qn(run, args)


def op_create_bead(run: "ScenarioRun", op: dict[str, Any]) -> None:
    """Create a bead via qn-bd subprocess. Skipped if bd not on PATH."""
    if not shutil.which("bd"):
        import pytest
        pytest.skip("bd binary not on PATH — skipping bead-dependent scenario")
    import subprocess
    import sys

    cmd = [
        sys.executable, "-m", "cli.commands.qn_bd",
        "--org-path", str(run.org_path),
        "create",
        "--title", op["title"],
        "--type", op.get("type", "task"),
    ]
    if "priority" in op:
        cmd += ["--priority", str(op["priority"])]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(
            f"qn-bd create failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    bead_id = None
    for line in result.stdout.splitlines():
        if "Created issue:" in line:
            parts = line.split("Created issue:", 1)[1].strip().split()
            bead_id = parts[0] if parts else None
            break
    if "id_var" in op and bead_id:
        run.context[op["id_var"]] = bead_id


def op_claim_bead(run: "ScenarioRun", op: dict[str, Any]) -> None:
    if not shutil.which("bd"):
        import pytest
        pytest.skip("bd binary not on PATH")
    import subprocess
    import sys

    bead_id = run.context.get(op["bead"], op["bead"])
    worker_id = run._resolve_worker_id(op["worker"])
    cmd = [
        sys.executable, "-m", "cli.commands.qn_bd",
        "--org-path", str(run.org_path),
        "update", bead_id,
        "--status", "in_progress",
        "--assignee", worker_id,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(
            f"qn-bd claim failed: stdout={result.stdout} stderr={result.stderr}"
        )


def op_induce_escalation(run: "ScenarioRun", op: dict[str, Any]) -> None:
    """Direct DB push of worker_escalation_state.current_state.

    NOTE: schema column is 'current_state' (not 'escalation_state'); also
    requires last_activity_at on insert per NOT NULL constraint.
    """
    worker_id = run._resolve_worker_id(op["worker"])
    target = op["kind"]
    conn = _writable_db(run)
    try:
        conn.execute(
            "INSERT INTO worker_escalation_state (worker_id, current_state, last_activity_at) "
            "VALUES (?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(worker_id) DO UPDATE SET current_state=excluded.current_state, "
            "updated_at=CURRENT_TIMESTAMP",
            (worker_id, target),
        )
        conn.commit()
    finally:
        conn.close()


def op_resolve_escalation(run: "ScenarioRun", op: dict[str, Any]) -> None:
    """Push escalation back to 'normal'."""
    worker_id = run._resolve_worker_id(op["worker"])
    conn = _writable_db(run)
    try:
        conn.execute(
            "INSERT INTO worker_escalation_state (worker_id, current_state, last_activity_at) "
            "VALUES (?, 'normal', CURRENT_TIMESTAMP) "
            "ON CONFLICT(worker_id) DO UPDATE SET current_state='normal', "
            "updated_at=CURRENT_TIMESTAMP",
            (worker_id,),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Registry — adding a new op kind = registering a function here.
# ---------------------------------------------------------------------------

OPS: dict[str, OpHandler] = {
    "init": op_init,
    "hire": op_hire,
    "fire": op_fire,
    "promote": op_promote,
    "demote": op_demote,
    "transition_lifecycle": op_transition_lifecycle,
    "transition_runtime": op_transition_runtime,
    "create_okr": op_create_okr,
    "assign_kr": op_assign_kr,
    "create_bead": op_create_bead,
    "claim_bead": op_claim_bead,
    "induce_escalation": op_induce_escalation,
    "resolve_escalation": op_resolve_escalation,
}
