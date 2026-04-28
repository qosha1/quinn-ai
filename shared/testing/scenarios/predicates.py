"""Assertion predicates — functions that read DB and return None or a violation message."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from .harness import ScenarioRun


# A predicate returns None when satisfied, otherwise a descriptive message.
Predicate = Callable[["ScenarioRun", dict[str, Any]], "str | None"]


def _fmt(actual: Any, expected: Any) -> str:
    return f"expected {expected!r}, got {actual!r}"


def pred_org_status(run: "ScenarioRun", a: dict[str, Any]) -> str | None:
    expected = a["value"]
    actual = run.db.org_status()
    if actual != expected:
        return f"org_status: {_fmt(actual, expected)}"
    return None


def pred_worker_count(run: "ScenarioRun", a: dict[str, Any]) -> str | None:
    expected = a["value"]
    actual = run.db.worker_count()
    if actual != expected:
        return f"worker_count: {_fmt(actual, expected)}"
    return None


def pred_worker_lifecycle_is(run: "ScenarioRun", a: dict[str, Any]) -> str | None:
    name = a["name"]
    expected = a["value"]
    worker = run.db.find_worker_by_name(name)
    if worker is None:
        return f"worker_lifecycle_is: no worker named {name!r}"
    actual = worker["status"]
    if actual != expected:
        return f"worker_lifecycle_is({name}): {_fmt(actual, expected)}"
    return None


def pred_manager_subordinates(run: "ScenarioRun", a: dict[str, Any]) -> str | None:
    manager = a["manager"]
    expected = sorted(s.lower() for s in a["expected"])
    actual = sorted(run.db.subordinate_names(manager))
    if actual != expected:
        return f"manager_subordinates({manager}): {_fmt(actual, expected)}"
    return None


def pred_org_chart_depth(run: "ScenarioRun", a: dict[str, Any]) -> str | None:
    expected = a["value"]
    actual = run.db.org_chart_depth()
    if actual != expected:
        return f"org_chart_depth: {_fmt(actual, expected)}"
    return None


def pred_okr_owner(run: "ScenarioRun", a: dict[str, Any]) -> str | None:
    okr_id = a["okr"]
    expected_name = a["expected"]
    expected = run.db.find_worker_by_name(expected_name)
    expected_id = expected["id"] if expected else None

    row = run.db.conn.execute(
        "SELECT owner_id FROM okrs WHERE id=?", (okr_id,)
    ).fetchone()
    if row is None:
        return f"okr_owner: no okr with id {okr_id!r}"
    if row["owner_id"] != expected_id:
        return f"okr_owner({okr_id}): expected owner {expected_name!r}, got id {row['owner_id']!r}"
    return None


def pred_kr_owner(run: "ScenarioRun", a: dict[str, Any]) -> str | None:
    okr_id = a["okr"]
    kr_id = a["kr"]
    expected_name = a["expected"]
    expected = run.db.find_worker_by_name(expected_name)
    expected_id = expected["id"] if expected else None

    # The KR table layout depends on the schema. Try common shapes.
    cur = run.db.conn.execute(
        "SELECT * FROM key_results WHERE id=? AND okr_id=?", (kr_id, okr_id)
    )
    row = cur.fetchone()
    if row is None:
        return f"kr_owner: no kr {kr_id!r} under {okr_id!r}"
    actual = row["owner_id"] if "owner_id" in row.keys() else None
    if actual != expected_id:
        return f"kr_owner({okr_id}/{kr_id}): expected {expected_name!r}, got id {actual!r}"
    return None


def _qn_bd_show_json(run: "ScenarioRun", bead_id: str) -> dict | None:
    """Run `qn-bd show <id> --json` via subprocess; return parsed dict or None."""
    import json
    import subprocess
    import sys

    cmd = [
        sys.executable, "-m", "cli.commands.qn_bd",
        "--org-path", str(run.org_path),
        "show", bead_id, "--json",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def pred_bead_status_is(run: "ScenarioRun", a: dict[str, Any]) -> str | None:
    """Bead status check via qn-bd show. Skipped if bd unavailable."""
    import shutil
    if not shutil.which("bd"):
        return None
    bead_var = a["bead_var"]
    bead_id = run.context.get(bead_var)
    if not bead_id:
        return f"bead_status_is: id_var {bead_var!r} not found in context"
    data = _qn_bd_show_json(run, bead_id)
    if data is None:
        return f"bead_status_is: qn-bd show failed for {bead_id}"
    actual = data.get("status")
    expected = a["value"]
    if actual != expected:
        return f"bead_status_is({bead_id}): {_fmt(actual, expected)}"
    return None


def pred_bead_assignee(run: "ScenarioRun", a: dict[str, Any]) -> str | None:
    import shutil
    if not shutil.which("bd"):
        return None
    bead_var = a["bead_var"]
    bead_id = run.context.get(bead_var)
    if not bead_id:
        return f"bead_assignee: id_var {bead_var!r} not found"
    data = _qn_bd_show_json(run, bead_id)
    if data is None:
        return f"bead_assignee: qn-bd show failed for {bead_id}"
    expected_name = a["expected"]
    expected = run.db.find_worker_by_name(expected_name)
    expected_id = expected["id"] if expected else None
    actual = data.get("assignee")
    if actual != expected_id:
        return f"bead_assignee({bead_id}): expected {expected_name!r}, got {actual!r}"
    return None


def pred_escalation_state_is(run: "ScenarioRun", a: dict[str, Any]) -> str | None:
    worker_name = a["worker"]
    expected = a["value"]
    worker = run.db.find_worker_by_name(worker_name)
    if worker is None:
        return f"escalation_state_is: no worker named {worker_name!r}"
    row = run.db.conn.execute(
        "SELECT current_state FROM worker_escalation_state WHERE worker_id=?",
        (worker["id"],),
    ).fetchone()
    if row is None:
        actual = "normal"  # default state when no row exists
    else:
        actual = row["current_state"]
    if actual != expected:
        return f"escalation_state_is({worker_name}): {_fmt(actual, expected)}"
    return None


PREDICATES: dict[str, Predicate] = {
    "org_status": pred_org_status,
    "worker_count": pred_worker_count,
    "worker_lifecycle_is": pred_worker_lifecycle_is,
    "manager_subordinates": pred_manager_subordinates,
    "org_chart_depth": pred_org_chart_depth,
    "okr_owner": pred_okr_owner,
    "kr_owner": pred_kr_owner,
    "bead_status_is": pred_bead_status_is,
    "bead_assignee": pred_bead_assignee,
    "escalation_state_is": pred_escalation_state_is,
}
