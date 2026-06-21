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


def _mark_host_mode(run: "ScenarioRun") -> None:
    """Set org_state.project_root so is_host_mode() returns True.

    In production, 'qn org init --host-mode' sets this. The harness
    writes it directly so scenarios can opt into host-mode without a
    separate CLI path (quinn-ai-jofi).
    """
    # org_path for host-mode is <project_root>/.quinnai/ — parent is the root.
    project_root = run.org_path.parent
    conn = _writable_db(run)
    try:
        conn.execute(
            "UPDATE org_state SET project_root = ? WHERE id = 'default'",
            (str(project_root),),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Op implementations
# ---------------------------------------------------------------------------


def op_init(run: "ScenarioRun", op: dict[str, Any]) -> None:
    setup = run.spec.setup.get("init", {}) or {}
    args = ["org", "init", "--skip-okrs"]
    if "ceo_name" in setup:
        args += ["--ceo-name", setup["ceo_name"]]
    # Host-mode: mark the org as host-mode so is_host_mode() returns True.
    # qn org init doesn't expose --host-mode at CLI level; we write the
    # marker file directly after init so the harness scenario mirrors what
    # 'qn org init --host-mode' does in production (quinn-ai-jofi).
    _run_qn(run, args)
    if run.spec.setup.get("host_mode"):
        _mark_host_mode(run)


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
    """Invoke bd directly (capturing stdout) against the org's beads backend.

    Sidesteps the qn-bd Python wrapper which has fd-plumbing issues that
    swallow stdout under captured-subprocess invocation. Routes through the
    shared dolt-aware bd_exec so writes target the org's real backend
    (quinn-ai-k9ff / boov), not an empty sqlite.
    """
    from .bd_exec import bd_exec

    return bd_exec(run.org_path, bd_args)


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
