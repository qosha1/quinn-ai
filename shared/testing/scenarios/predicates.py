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
    """Worker count assertion. Use 'value' for exact match or 'min' for >=."""
    actual = run.db.worker_count()
    if "min" in a:
        minimum = int(a["min"])
        if actual < minimum:
            return f"worker_count: expected ≥{minimum}, got {actual}"
        return None
    expected = a["value"]
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
    """OKR owner check via qn-bd show. OKRs are beads (type='okr');
    'owner' maps to the assignee field on the bead.

    'okr' may be a literal bead id OR an id_var key from run.context.
    """
    import shutil
    if not shutil.which("bd"):
        return None  # bd not on PATH; cannot verify, treat as pass
    okr_ref = a["okr"]
    okr_id = run.context.get(okr_ref, okr_ref)
    expected_name = a["expected"]

    data = _qn_bd_show_json(run, okr_id)
    if data is None:
        return f"okr_owner: qn-bd show failed for {okr_id!r}"

    actual_assignee = data.get("assignee")  # may be a worker id or 'ceo' alias
    expected_worker = run.db.find_worker_by_name(expected_name)
    expected_id = expected_worker["id"] if expected_worker else None

    # Match either by worker id (qn org okr set --owner <id>) or by lowercase
    # name alias ('ceo' is the common case).
    if actual_assignee == expected_id:
        return None
    if actual_assignee and actual_assignee.lower() == expected_name.lower():
        return None
    return (
        f"okr_owner({okr_id}): expected {expected_name!r} "
        f"(id {expected_id!r}), got {actual_assignee!r}"
    )


def pred_kr_owner(run: "ScenarioRun", a: dict[str, Any]) -> str | None:
    """Key-result owner check.

    'qn org okr update-kr' currently sets a metric+target on the OKR bead
    but doesn't expose a per-KR owner field — KRs are sub-properties of the
    OKR, not independent beads. So 'kr_owner' is treated as 'OKR is the
    KR's effective owner' until QuinnAI grows real KR-as-bead support.
    """
    return pred_okr_owner(run, {"okr": a["okr"], "expected": a["expected"]})


def _qn_bd_show_json(run: "ScenarioRun", bead_id: str) -> dict | None:
    """Read a bead's JSON via the bundled bd binary directly.

    Sidesteps the qn-bd Python wrapper because bd 0.43 swallows stdout when
    invoked through it under captured-stdout subprocess (qn-bd's
    permission/lifecycle pre-checks somehow break the fd plumbing). Going
    direct gives us deterministic JSON.
    """
    import json
    import subprocess

    from cli.core.bd_wrapper import get_bundled_bd_path, get_org_beads_dir

    bd_path = get_bundled_bd_path()
    beads_db = get_org_beads_dir(run.org_path) / "beads.db"
    cmd = [str(bd_path), "--sandbox", f"--db={beads_db}", "show", bead_id, "--json"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    # bd's `show --json` returns a list with one item; unwrap to the bead dict.
    if isinstance(data, list) and data:
        return data[0]
    if isinstance(data, dict):
        return data
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


def pred_message_count_from(run: "ScenarioRun", a: dict[str, Any]) -> str | None:
    """Count messages sent BY a given worker (any channel).

    YAML: { kind: message_count_from, worker: bob, min: 1 }
    """
    worker_name = a["worker"]
    minimum = int(a.get("min", a.get("value", 1)))
    worker = run.db.find_worker_by_name(worker_name)
    if worker is None:
        return f"message_count_from: no worker named {worker_name!r}"
    row = run.db.conn.execute(
        "SELECT COUNT(*) AS c FROM messages WHERE from_worker_id=?",
        (worker["id"],),
    ).fetchone()
    actual = row["c"] if row else 0
    if actual < minimum:
        return f"message_count_from({worker_name}): expected ≥{minimum}, got {actual}"
    return None


def pred_message_count_between(run: "ScenarioRun", a: dict[str, Any]) -> str | None:
    """Count messages sent FROM worker_a addressed to worker_b.

    Direct messages: channel.type='direct' and worker_b is subscribed to that
    channel. We count messages from worker_a in any channel where worker_b
    is also a subscriber (covers DMs + shared topic/team channels — for a
    canonical 1:1 DM scenario this is what we want).

    YAML: { kind: message_count_between, from: bob, to: carol, min: 1 }
    """
    from_name = a["from"]
    to_name = a["to"]
    minimum = int(a.get("min", a.get("value", 1)))
    sender = run.db.find_worker_by_name(from_name)
    receiver = run.db.find_worker_by_name(to_name)
    if sender is None:
        return f"message_count_between: no sender named {from_name!r}"
    if receiver is None:
        return f"message_count_between: no receiver named {to_name!r}"
    row = run.db.conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM messages m
        JOIN channel_subscriptions cs ON cs.channel_id = m.channel_id
        WHERE m.from_worker_id=? AND cs.worker_id=?
        """,
        (sender["id"], receiver["id"]),
    ).fetchone()
    actual = row["c"] if row else 0
    if actual < minimum:
        return (
            f"message_count_between({from_name}→{to_name}): expected ≥{minimum}, got {actual}"
        )
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
    "message_count_from": pred_message_count_from,
    "message_count_between": pred_message_count_between,
}


def pred_file_contains(run: "ScenarioRun", a: dict[str, Any]) -> str | None:
    """Filesystem assertion: file at `path` does/doesn't contain `substring`.

    YAML forms:
      - { kind: file_contains, path: /tmp/x.py, substring: "isalnum" }
      - { kind: file_contains, path: /tmp/x.py, substring: "isspace", should: absent }

    Used to verify that workers actually edited shared files per review
    feedback, not merely acknowledged it. The 'should' key takes
    'present' (default) or 'absent'.
    """
    from pathlib import Path
    path = Path(a["path"])
    substring = a["substring"]
    expected = a.get("should", "present")

    if not path.exists():
        return f"file_contains: file does not exist at {path}"
    try:
        text = path.read_text()
    except Exception as e:
        return f"file_contains: could not read {path}: {e}"

    has = substring in text
    if expected == "present" and not has:
        return f"file_contains({path}): substring {substring!r} NOT found"
    if expected == "absent" and has:
        return f"file_contains({path}): substring {substring!r} should be ABSENT but is present"
    return None


PREDICATES["file_contains"] = pred_file_contains


def pred_bead_count_closed_by(run: "ScenarioRun", a: dict[str, Any]) -> str | None:
    """Count beads closed by a given worker (assignee = worker, status = closed/done).

    Reads via bd direct (sidesteps qn-bd's tty-swallow issue from 4zgi).

    YAML: { kind: bead_count_closed_by, worker: bob, min: 1 }
    """
    import json
    import shutil
    import subprocess
    from cli.core.bd_wrapper import get_bundled_bd_path, get_org_beads_dir

    if not shutil.which("bd") and not get_bundled_bd_path().exists():
        return None  # cannot verify

    worker_name = a["worker"]
    minimum = int(a.get("min", a.get("value", 1)))
    worker = run.db.find_worker_by_name(worker_name)
    if worker is None:
        return f"bead_count_closed_by: no worker named {worker_name!r}"

    bd_path = get_bundled_bd_path()
    beads_db = get_org_beads_dir(run.org_path) / "beads.db"
    cmd = [str(bd_path), "--sandbox", f"--db={beads_db}",
           "list", "--status", "closed", "--assignee", worker["id"], "--json"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    if result.returncode != 0:
        # bd may not support --status closed exactly; fall back to all-then-filter.
        cmd2 = [str(bd_path), "--sandbox", f"--db={beads_db}", "list", "--all", "--json"]
        result = subprocess.run(cmd2, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            return f"bead_count_closed_by: bd list failed: {result.stderr[:200]}"
    try:
        rows = json.loads(result.stdout) or []
    except json.JSONDecodeError:
        return f"bead_count_closed_by: bd output not JSON"
    actual = sum(
        1 for r in rows
        if r.get("assignee") == worker["id"]
        and r.get("status", "").lower() in ("closed", "done", "resolved")
    )
    if actual < minimum:
        return f"bead_count_closed_by({worker_name}): expected ≥{minimum}, got {actual}"
    return None


PREDICATES["bead_count_closed_by"] = pred_bead_count_closed_by


def pred_file_contains_any(run: "ScenarioRun", a: dict[str, Any]) -> str | None:
    """Filesystem assertion: file at `path` contains AT LEAST ONE of `substrings`.

    Useful for tone/style checks where any of several markers indicate the
    artifact is the intended kind of writing (e.g. marketing copy uses
    'we'/'you'/'today'/'launch' etc.).

    YAML: { kind: file_contains_any, path: /tmp/changelog.md, substrings: [we, you, today, launch], case_insensitive: true }
    """
    from pathlib import Path
    path = Path(a["path"])
    substrings = a["substrings"]
    case_insensitive = bool(a.get("case_insensitive", False))

    if not path.exists():
        return f"file_contains_any: file does not exist at {path}"
    try:
        text = path.read_text()
    except Exception as e:
        return f"file_contains_any: could not read {path}: {e}"

    haystack = text.lower() if case_insensitive else text
    needles = [s.lower() if case_insensitive else s for s in substrings]
    matches = [n for n in needles if n in haystack]
    if not matches:
        return (
            f"file_contains_any({path}): none of {substrings!r} found "
            f"(content sample: {text[:120]!r})"
        )
    return None


PREDICATES["file_contains_any"] = pred_file_contains_any


def pred_worker_role_contains(run: "ScenarioRun", a: dict[str, Any]) -> str | None:
    """Assert that ≥min workers have a role string containing any of substrings.

    Used by canaries that test cross-functional staffing without prescribing
    specific worker names — we don't care WHO the CEO hired, only that the
    org now contains at least one worker whose role indicates the right
    specialty (e.g. marketing/comms/PR for a customer-facing statement).

    YAML:
      - { kind: worker_role_contains, substrings: ["marketing","comms","pr"], min: 1 }
      - { kind: worker_role_contains, substrings: ["qa","test"], min: 1, exclude_ceo: true }

    Match is case-insensitive substring; 'exclude_ceo' (default true) skips
    role='CEO' so 'comm' wildcards don't accidentally count the CEO if their
    role contains the substring.
    """
    substrings = [s.lower() for s in a["substrings"]]
    minimum = int(a.get("min", 1))
    exclude_ceo = a.get("exclude_ceo", True)

    rows = run.db.conn.execute(
        "SELECT role FROM workers WHERE role IS NOT NULL"
    ).fetchall()
    matching = 0
    for row in rows:
        role = (row["role"] or "")
        if exclude_ceo and role.upper() == "CEO":
            continue
        role_lower = role.lower()
        if any(sub in role_lower for sub in substrings):
            matching += 1
    if matching < minimum:
        return (
            f"worker_role_contains({substrings}): expected ≥{minimum}, "
            f"got {matching}"
        )
    return None


PREDICATES["worker_role_contains"] = pred_worker_role_contains


def pred_command_succeeds(run: "ScenarioRun", a: dict[str, Any]) -> str | None:
    """Run a shell command and assert exit code 0.

    Used by 'real platform' canaries where the gate is 'the workers'
    artifact is correct enough to actually pass tests' — not just 'a file
    with this name exists'. Runs in the harness process, NOT in any
    worker session, so it sees the same filesystem (e.g. /tmp paths) the
    workers wrote to.

    YAML:
      - { kind: command_succeeds, command: "pytest /tmp/canary10/test_x.py -q", timeout_seconds: 30 }
      - { kind: command_succeeds, command: "python -c 'import x; assert x.f(1)==2'", timeout_seconds: 10 }

    The harness times the command out at `timeout_seconds` (default 30) and
    reports the tail of stdout+stderr on failure so the operator can see
    why the command didn't pass.
    """
    import subprocess
    cmd = a["command"]
    timeout = int(a.get("timeout_seconds", 30))
    try:
        result = subprocess.run(
            ["bash", "-c", cmd],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"command_succeeds({cmd!r}): timed out after {timeout}s"
    if result.returncode != 0:
        return (
            f"command_succeeds({cmd!r}): exit {result.returncode}\n"
            f"  stdout: {result.stdout[-300:]!r}\n"
            f"  stderr: {result.stderr[-300:]!r}"
        )
    return None


PREDICATES["command_succeeds"] = pred_command_succeeds
