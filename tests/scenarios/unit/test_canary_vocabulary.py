"""Unit tests for canary vocabulary added by quinn-ai-4etf.

Covers:
  Ops (canary_ops.py):
    - rules_yaml_seed
    - templates_yaml_seed
  Predicates (predicates.py):
    - audit_log_contains
    - bead_does_not_exist
    - team_count
    - channel_exists
    - team_parent_is

These ops/predicates support canaries 11 (board-rules-blocks-action) and
12 (template-driven-hiring). The tests stand each one up against a fake
ScenarioRun so we can assert behaviour without spinning a full org.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

# Importing the canary package registers ops into the shared OPS dict via
# canary_ops.py's setdefault calls. The tests below pull the ops/predicates
# back out of the registry so they exercise the same code path as production.
import shared.testing.canary  # noqa: F401  (registration side effect)
from shared.testing.scenarios import OPS, PREDICATES


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class FakeRun:
    """Minimal stand-in for ScenarioRun.

    Only exposes the attributes the ops/predicates touch. DB-backed
    predicates take a sqlite3.Connection wired to row_factory=Row so they
    look up columns by name like the real DBHandle.
    """

    def __init__(self, org_path: Path, conn: sqlite3.Connection | None = None):
        self.org_path = org_path
        self.context: dict = {}
        self.db = SimpleNamespace(conn=conn) if conn is not None else None


def _empty_db_conn() -> sqlite3.Connection:
    """In-memory DB with just the tables the new predicates query."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE teams (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            parent_team_id TEXT
        );
        CREATE TABLE channels (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL
        );
        """
    )
    return conn


# ---------------------------------------------------------------------------
# Ops
# ---------------------------------------------------------------------------


def test_rules_yaml_seed_writes_file(tmp_path: Path):
    op = OPS["rules_yaml_seed"]
    run = FakeRun(tmp_path)
    content = "version: 1\nrules:\n  - id: no-drop-database\n"
    op(run, {"op": "rules_yaml_seed", "content": content})
    target = tmp_path / "config" / "rules.yaml"
    assert target.exists()
    assert target.read_text() == content


def test_rules_yaml_seed_creates_config_dir(tmp_path: Path):
    op = OPS["rules_yaml_seed"]
    run = FakeRun(tmp_path)
    assert not (tmp_path / "config").exists()
    op(run, {"op": "rules_yaml_seed", "content": "version: 1\n"})
    assert (tmp_path / "config").is_dir()


def test_rules_yaml_seed_requires_content(tmp_path: Path):
    op = OPS["rules_yaml_seed"]
    run = FakeRun(tmp_path)
    with pytest.raises(ValueError, match="content"):
        op(run, {"op": "rules_yaml_seed"})


def test_templates_yaml_seed_writes_file(tmp_path: Path):
    op = OPS["templates_yaml_seed"]
    run = FakeRun(tmp_path)
    content = "version: 1\ntemplates: []\n"
    op(run, {"op": "templates_yaml_seed", "content": content})
    target = tmp_path / "config" / "templates.yaml"
    assert target.exists()
    assert target.read_text() == content


def test_templates_yaml_seed_requires_content(tmp_path: Path):
    op = OPS["templates_yaml_seed"]
    run = FakeRun(tmp_path)
    with pytest.raises(ValueError, match="content"):
        op(run, {"op": "templates_yaml_seed", "content": 42})


# ---------------------------------------------------------------------------
# audit_log_contains
# ---------------------------------------------------------------------------


def _write_audit(org_path: Path, lines: list[dict]) -> Path:
    audit_dir = org_path / "live"
    audit_dir.mkdir(parents=True, exist_ok=True)
    target = audit_dir / "rules-audit.jsonl"
    target.write_text("\n".join(json.dumps(entry) for entry in lines) + "\n")
    return target


def test_audit_log_contains_matches_subset(tmp_path: Path):
    pred = PREDICATES["audit_log_contains"]
    _write_audit(
        tmp_path,
        [
            {"rule_id": "no-drop-database", "decision": "block", "action": "qn-bd.create"},
        ],
    )
    run = FakeRun(tmp_path)
    assert pred(run, {"rule_id": "no-drop-database", "decision": "block"}) is None


def test_audit_log_contains_returns_violation_when_missing(tmp_path: Path):
    pred = PREDICATES["audit_log_contains"]
    _write_audit(
        tmp_path,
        [
            {"rule_id": "other", "decision": "allow"},
        ],
    )
    run = FakeRun(tmp_path)
    msg = pred(run, {"rule_id": "no-drop-database", "decision": "block"})
    assert msg is not None
    assert "audit_log_contains" in msg


def test_audit_log_contains_no_file(tmp_path: Path):
    pred = PREDICATES["audit_log_contains"]
    run = FakeRun(tmp_path)
    msg = pred(run, {"rule_id": "x", "decision": "block"})
    assert msg is not None
    assert "does not exist" in msg


def test_audit_log_contains_explicit_match_dict(tmp_path: Path):
    pred = PREDICATES["audit_log_contains"]
    _write_audit(
        tmp_path,
        [{"rule_id": "r1", "decision": "block", "extra": "ignored"}],
    )
    run = FakeRun(tmp_path)
    assert pred(run, {"match": {"rule_id": "r1", "decision": "block"}}) is None


def test_audit_log_contains_min_threshold(tmp_path: Path):
    pred = PREDICATES["audit_log_contains"]
    _write_audit(
        tmp_path,
        [
            {"rule_id": "r1", "decision": "block"},
            {"rule_id": "r1", "decision": "block"},
        ],
    )
    run = FakeRun(tmp_path)
    assert pred(run, {"rule_id": "r1", "decision": "block", "min": 2}) is None
    msg = pred(run, {"rule_id": "r1", "decision": "block", "min": 3})
    assert msg is not None and "expected ≥3" in msg


def test_audit_log_contains_skips_invalid_json(tmp_path: Path):
    pred = PREDICATES["audit_log_contains"]
    audit_path = tmp_path / "live" / "rules-audit.jsonl"
    audit_path.parent.mkdir(parents=True)
    audit_path.write_text(
        "not json at all\n"
        + json.dumps({"rule_id": "r1", "decision": "block"})
        + "\n"
    )
    run = FakeRun(tmp_path)
    assert pred(run, {"rule_id": "r1", "decision": "block"}) is None


def test_audit_log_contains_requires_match(tmp_path: Path):
    pred = PREDICATES["audit_log_contains"]
    _write_audit(tmp_path, [{"x": 1}])
    run = FakeRun(tmp_path)
    msg = pred(run, {})
    assert msg is not None and "must contain at least one" in msg


# ---------------------------------------------------------------------------
# bead_does_not_exist (skipped when bd unavailable; otherwise mock subprocess)
# ---------------------------------------------------------------------------


def test_bead_does_not_exist_zero_matches(tmp_path: Path, monkeypatch):
    pred = PREDICATES["bead_does_not_exist"]

    # Force the "bd is available" path so we exercise the subprocess shim.
    import shared.testing.scenarios.predicates as predmod  # noqa

    def fake_run(cmd, capture_output, text, timeout):
        result = SimpleNamespace()
        result.returncode = 0
        result.stdout = json.dumps([{"id": "b1", "title": "unrelated work"}])
        result.stderr = ""
        return result

    # Make 'bd' appear available so the early-return short-circuit doesn't fire.
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/bd")
    # Patch subprocess.run inside the predicates module's call site.
    monkeypatch.setattr("subprocess.run", fake_run)

    # Stub the bd_wrapper helpers so we don't depend on a real bundled binary.
    import cli.core.bd_wrapper as bdw

    monkeypatch.setattr(bdw, "get_bundled_bd_path", lambda: Path("/usr/bin/bd"))
    monkeypatch.setattr(bdw, "get_org_beads_dir", lambda p: tmp_path / ".beads")

    run = FakeRun(tmp_path)
    assert pred(run, {"title_substring": "schema migration"}) is None


def test_bead_does_not_exist_match_returns_violation(tmp_path: Path, monkeypatch):
    pred = PREDICATES["bead_does_not_exist"]

    def fake_run(cmd, capture_output, text, timeout):
        result = SimpleNamespace()
        result.returncode = 0
        result.stdout = json.dumps(
            [
                {"id": "b1", "title": "schema migration v0 plan"},
                {"id": "b2", "title": "irrelevant"},
            ]
        )
        result.stderr = ""
        return result

    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/bd")
    monkeypatch.setattr("subprocess.run", fake_run)
    import cli.core.bd_wrapper as bdw

    monkeypatch.setattr(bdw, "get_bundled_bd_path", lambda: Path("/usr/bin/bd"))
    monkeypatch.setattr(bdw, "get_org_beads_dir", lambda p: tmp_path / ".beads")

    run = FakeRun(tmp_path)
    msg = pred(run, {"title_substring": "schema migration v0"})
    assert msg is not None
    assert "bead_does_not_exist" in msg
    assert "b1" in msg


def test_bead_does_not_exist_skipped_when_bd_missing(tmp_path: Path, monkeypatch):
    pred = PREDICATES["bead_does_not_exist"]

    monkeypatch.setattr("shutil.which", lambda name: None)
    import cli.core.bd_wrapper as bdw

    fake_path = tmp_path / "no-such-bd"
    monkeypatch.setattr(bdw, "get_bundled_bd_path", lambda: fake_path)

    run = FakeRun(tmp_path)
    # Predicate returns None (skip) when bd unavailable, matching bead_status_is.
    assert pred(run, {"title_substring": "anything"}) is None


# ---------------------------------------------------------------------------
# team_count
# ---------------------------------------------------------------------------


def test_team_count_value_exact_match(tmp_path: Path):
    pred = PREDICATES["team_count"]
    conn = _empty_db_conn()
    conn.execute("INSERT INTO teams (id, name) VALUES ('t1', 'engineering')")
    conn.execute("INSERT INTO teams (id, name) VALUES ('t2', 'design')")
    run = FakeRun(tmp_path, conn=conn)
    assert pred(run, {"value": 2}) is None
    msg = pred(run, {"value": 3})
    assert msg is not None and "expected 3" in msg


def test_team_count_min_threshold(tmp_path: Path):
    pred = PREDICATES["team_count"]
    conn = _empty_db_conn()
    conn.execute("INSERT INTO teams (id, name) VALUES ('t1', 'a')")
    conn.execute("INSERT INTO teams (id, name) VALUES ('t2', 'b')")
    conn.execute("INSERT INTO teams (id, name) VALUES ('t3', 'c')")
    run = FakeRun(tmp_path, conn=conn)
    assert pred(run, {"min": 3}) is None
    assert pred(run, {"min": 2}) is None
    msg = pred(run, {"min": 5})
    assert msg is not None and "≥5" in msg


def test_team_count_requires_value_or_min(tmp_path: Path):
    pred = PREDICATES["team_count"]
    conn = _empty_db_conn()
    run = FakeRun(tmp_path, conn=conn)
    msg = pred(run, {})
    assert msg is not None and "must specify" in msg


# ---------------------------------------------------------------------------
# channel_exists
# ---------------------------------------------------------------------------


def test_channel_exists_present(tmp_path: Path):
    pred = PREDICATES["channel_exists"]
    conn = _empty_db_conn()
    conn.execute(
        "INSERT INTO channels (id, name, type) VALUES ('c1', 'product-mobile-app', 'team')"
    )
    run = FakeRun(tmp_path, conn=conn)
    assert pred(run, {"name": "product-mobile-app"}) is None


def test_channel_exists_missing(tmp_path: Path):
    pred = PREDICATES["channel_exists"]
    conn = _empty_db_conn()
    run = FakeRun(tmp_path, conn=conn)
    msg = pred(run, {"name": "does-not-exist"})
    assert msg is not None
    assert "does-not-exist" in msg


# ---------------------------------------------------------------------------
# team_parent_is
# ---------------------------------------------------------------------------


def test_team_parent_is_correct_parent(tmp_path: Path):
    pred = PREDICATES["team_parent_is"]
    conn = _empty_db_conn()
    conn.execute("INSERT INTO teams (id, name, parent_team_id) VALUES ('t-mob', 'mobile-app', NULL)")
    conn.execute(
        "INSERT INTO teams (id, name, parent_team_id) VALUES ('t-auth', 'auth-redesign', 't-mob')"
    )
    run = FakeRun(tmp_path, conn=conn)
    assert pred(run, {"child": "auth-redesign", "parent": "mobile-app"}) is None


def test_team_parent_is_wrong_parent(tmp_path: Path):
    pred = PREDICATES["team_parent_is"]
    conn = _empty_db_conn()
    conn.execute("INSERT INTO teams (id, name, parent_team_id) VALUES ('t-mob', 'mobile-app', NULL)")
    conn.execute("INSERT INTO teams (id, name, parent_team_id) VALUES ('t-other', 'other', NULL)")
    conn.execute(
        "INSERT INTO teams (id, name, parent_team_id) VALUES ('t-auth', 'auth-redesign', 't-other')"
    )
    run = FakeRun(tmp_path, conn=conn)
    msg = pred(run, {"child": "auth-redesign", "parent": "mobile-app"})
    assert msg is not None
    assert "expected parent_team_id" in msg


def test_team_parent_is_missing_child(tmp_path: Path):
    pred = PREDICATES["team_parent_is"]
    conn = _empty_db_conn()
    conn.execute("INSERT INTO teams (id, name, parent_team_id) VALUES ('t-mob', 'mobile-app', NULL)")
    run = FakeRun(tmp_path, conn=conn)
    msg = pred(run, {"child": "missing", "parent": "mobile-app"})
    assert msg is not None
    assert "no team named 'missing'" in msg


def test_team_parent_is_missing_parent(tmp_path: Path):
    pred = PREDICATES["team_parent_is"]
    conn = _empty_db_conn()
    conn.execute(
        "INSERT INTO teams (id, name, parent_team_id) VALUES ('t-auth', 'auth-redesign', NULL)"
    )
    run = FakeRun(tmp_path, conn=conn)
    msg = pred(run, {"child": "auth-redesign", "parent": "missing"})
    assert msg is not None
    assert "no parent team named 'missing'" in msg
