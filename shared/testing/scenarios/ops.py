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


def op_delegate_authority(run: "ScenarioRun", op: dict[str, Any]) -> None:
    """Grant hiring authority + budget to a worker so they can hire reports.

    YAML form:
      - { op: delegate_authority, to: bob, level: team-lead, budget: 200, max_reports: 5 }
    """
    target_id = run._resolve_worker_id(op["to"])
    args = ["org", "delegate-authority", "--to", target_id, "--force"]
    if "level" in op:
        args += ["--level", op["level"]]
    if "from" in op:
        from_id = run._resolve_worker_id(op["from"])
        args += ["--from", from_id]
    if "budget" in op:
        args += ["--budget", str(op["budget"])]
    if "max_reports" in op:
        args += ["--max-reports", str(op["max_reports"])]
    if "max_cost" in op:
        args += ["--max-cost", str(op["max_cost"])]
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
    """Create an OKR via 'qn org okr set'. OKRs are stored as beads of type 'okr'.

    Captures the generated bead id from the 'Created issue: <id>' line so
    later ops/assertions can reference it via id_var.

    Canary OKRs are intentionally exploratory test scaffolding, not real
    organizational OKRs — they exist to drive a CEO session through a
    specific decision shape, not to be measured against. Default to
    --no-krs-needed so canaries continue to work after qn org okr set
    started enforcing measurable KRs. Specs that DO want to exercise the
    KR path can pass `key_results: [{metric:..., target:..., unit:...}]`
    in the op YAML.
    """
    from cli.commands.main import qn

    args = ["--org-path", str(run.org_path), "org", "okr", "set", "--title", op["objective"]]
    if "owner" in op:
        worker_id = run._resolve_worker_id(op["owner"])
        args += ["--owner", worker_id]
    if "description" in op:
        args += ["--description", op["description"]]

    key_results = op.get("key_results") or []
    if key_results:
        for kr in key_results:
            metric = kr["metric"]
            target = kr["target"]
            unit = kr["unit"]
            args += ["--kr", f"{metric}:{target}:{unit}"]
    else:
        args += ["--no-krs-needed"]

    result = run.runner.invoke(qn, args, catch_exceptions=False)
    if result.exit_code != 0:
        raise RuntimeError(
            f"qn org okr set failed (exit {result.exit_code}):\n{result.output}"
        )
    # Parse 'Created issue: quinnai-XXXX' from output
    okr_id = None
    for line in result.output.splitlines():
        if "Created issue:" in line:
            parts = line.split("Created issue:", 1)[1].strip().split()
            if parts:
                okr_id = parts[0]
                break
    if "id_var" in op and okr_id:
        run.context[op["id_var"]] = okr_id


def op_assign_kr(run: "ScenarioRun", op: dict[str, Any]) -> None:
    """Add or update a key result on an OKR via 'qn org okr update-kr'.

    Resolves op['okr'] from run.context if it matches an id_var; otherwise
    treats it as a literal bead id.
    """
    okr_ref = op["okr"]
    okr_id = run.context.get(okr_ref, okr_ref)
    args = [
        "org", "okr", "update-kr",
        okr_id,
        "--metric", op.get("kr", op.get("metric", "kr")),
        "--target", str(op.get("target", 1)),
    ]
    _run_qn(run, args)


def _bd_direct(run: "ScenarioRun", bd_args: list[str]) -> "subprocess.CompletedProcess":
    """Invoke the bundled bd binary directly with --sandbox + --db.

    Sidesteps the qn-bd Python wrapper which has fd-plumbing issues that
    swallow stdout under captured-subprocess invocation. Used for ops that
    need to read bd's output (e.g. capturing a created bead id).
    """
    import subprocess
    from cli.core.bd_wrapper import get_bundled_bd_path, get_org_beads_dir

    bd_path = get_bundled_bd_path()
    beads_db = get_org_beads_dir(run.org_path) / "beads.db"
    cmd = [str(bd_path), "--sandbox", f"--db={beads_db}"] + bd_args
    return subprocess.run(cmd, capture_output=True, text=True, timeout=30)


def op_create_bead(run: "ScenarioRun", op: dict[str, Any]) -> None:
    """Create a bead via the bundled bd binary directly."""
    if not shutil.which("bd") and not _bundled_bd_exists():
        import pytest
        pytest.skip("bd binary not available — skipping bead-dependent scenario")

    bd_args = [
        "create",
        "--title", op["title"],
        "--type", op.get("type", "task"),
    ]
    if "priority" in op:
        bd_args += ["--priority", str(op["priority"])]
    result = _bd_direct(run, bd_args)
    if result.returncode != 0:
        raise RuntimeError(
            f"bd create failed (exit {result.returncode}):\n"
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
    """Update a bead's status + assignee via the bundled bd binary directly."""
    if not shutil.which("bd") and not _bundled_bd_exists():
        import pytest
        pytest.skip("bd binary not available")

    bead_id = run.context.get(op["bead"], op["bead"])
    worker_id = run._resolve_worker_id(op["worker"])
    result = _bd_direct(run, [
        "update", bead_id,
        "--status", "in_progress",
        "--assignee", worker_id,
    ])
    if result.returncode != 0:
        raise RuntimeError(
            f"bd update failed: stdout={result.stdout} stderr={result.stderr}"
        )


def _bundled_bd_exists() -> bool:
    try:
        from cli.core.bd_wrapper import get_bundled_bd_path
        return get_bundled_bd_path().exists()
    except Exception:
        return False


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
    "delegate_authority": op_delegate_authority,
    "create_okr": op_create_okr,
    "assign_kr": op_assign_kr,
    "create_bead": op_create_bead,
    "claim_bead": op_claim_bead,
    "induce_escalation": op_induce_escalation,
    "resolve_escalation": op_resolve_escalation,
}
