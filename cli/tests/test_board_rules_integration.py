"""
Failing integration tests for BOARD-RULES wiring into real Click CLI commands.

Spec sources (read these — the bead description for quinn-ai-9luv uses STALE
vocabulary: "SOFT/ADVISORY/ENFORCED" and `approver_role: board`. The captured
user requirements supersede that wording. Live spec:

- quinn-ai-c5hb §1, §1a, §1b — severity vocabulary is
  SUGGESTED / ENCOURAGED / REQUIRED / ABSOLUTE; REQUIRED override is
  *direct-manager* approval (NOT board); ABSOLUTE is unoverridable.
- quinn-ai-c5hb §3 — 14-rule catalog (including no-drop-database for the
  ABSOLUTE-on-qn-bd-create test below).
- quinn-ai-c5hb §4 — 12 v0 CLI surfaces; this file exercises four of them
  (`qn org hire`, `qn-bd create`, `qn org fire`, plus the kill-switch path).
- quinn-ai-t2zb §C / §C.2 — `requires_rule_check(action)` Click decorator;
  reads --justify / --override flags from kwargs; pulls `ctx.obj.rules` and
  `ctx.obj.rules_audit` for engine + audit logger.
- quinn-ai-t2zb §E — every evaluation produces exactly one audit JSONL line.
- quinn-ai-zm8a §3, §5 — DI via `ctx.obj.rules` and `ctx.obj.rules_audit`;
  `--justify` and `--override` Click options are attached PROGRAMMATICALLY by
  the decorator (not by the wrapped command), so they're available on every
  rule-aware command without per-command boilerplate.
- quinn-ai-zm8a §3 — `QUINNAI_RULES_DISABLED=1` swaps the engine for a
  `DisabledRuleEngine` whose decisions all carry `kill_switch_used=True` in
  the audit log.
- quinn-ai-zm8a §5 — Decorator stack: `@requires_permission` is OUTER (auth
  gate runs first); `@requires_rule_check` is INNER. If permission denies,
  no rule eval and no audit log entry happen.

These tests fail today because:
  - `cli.core.rules` does not yet exist.
  - The 12 CLI surfaces are not yet decorated with `@requires_rule_check`.
  - `org/config/rules.yaml` is not yet loaded by `qn org init`.

Imports are inside test bodies so each test fails with a clean ImportError
(or AttributeError on a partial impl) rather than failing the whole module
at collection time. Pattern matches `cli/tests/test_board_rules_engine.py`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from click.testing import CliRunner


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def runner() -> CliRunner:
    """Click test runner.

    Note: Click 8.2+ removed `mix_stderr=False` so stderr is mixed into
    `result.output`. Tests that look for nudge / block messages search the
    combined stream rather than `result.stderr`.
    """
    return CliRunner()


def _combined_output(result) -> str:
    """Return stdout + stderr if available; else stdout only.

    Click <8.2 supports `mix_stderr=False` and exposes `result.stderr`;
    Click >=8.2 mixes them into `result.output`. This helper makes the
    assertions stable across both versions.
    """
    out = result.output or ""
    try:
        err = result.stderr or ""
    except (AttributeError, ValueError):
        err = ""
    return out + err


@pytest.fixture
def rules_org(tmp_path: Path, runner: CliRunner) -> Path:
    """An initialized org whose rules.yaml has been seeded by the test.

    Tests pass a `rules_yaml` string via `_seed_rules` to point this fixture
    at a particular catalog. The fixture only handles `qn org init`; rule
    seeding is per-test.
    """
    from cli.commands.main import qn

    result = runner.invoke(
        qn,
        ["--org-path", str(tmp_path), "org", "init", "--ceo-name", "Alice"],
    )
    if result.exit_code != 0:
        pytest.fail(f"org init failed: {_combined_output(result)}")
    return tmp_path


def _seed_rules(org_path: Path, rules_yaml: str) -> Path:
    """Write the given rules.yaml content into org/config/rules.yaml."""
    config_dir = org_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    rules_path = config_dir / "rules.yaml"
    rules_path.write_text(rules_yaml)
    return rules_path


def _resolve_ceo_id(org_path: Path) -> str:
    """Look up the CEO's auto-generated worker_id created by `qn org init`."""
    from cli.core.db import open_database, get_org_db_path

    db = open_database(get_org_db_path(org_path))
    try:
        row = db.fetchone(
            "SELECT id FROM workers WHERE manager_id IS NULL LIMIT 1"
        )
        if not row:
            pytest.fail("could not find CEO worker after `qn org init`")
        return row["id"]
    finally:
        db.close()


def _seed_worker(
    org_path: Path,
    *,
    name: str,
    role: str,
    manager_name: str | None = None,
) -> str:
    """Insert a worker directly into the org's database (bypassing CLI).

    Returns the worker_id. Uses the existing `create_worker` query — the
    default team is created by `qn org init`. `manager_name` may be None
    (top-level worker) or "alice" / any other name to look up the manager
    by name. Resolution happens here so tests don't have to track UUIDs.
    """
    from cli.core.db import open_database, get_org_db_path
    from cli.core.queries.worker import create_worker

    db = open_database(get_org_db_path(org_path))
    try:
        row = db.fetchone("SELECT id FROM teams LIMIT 1")
        team_id = row["id"] if row else "team-default"

        manager_id: str | None = None
        if manager_name:
            mrow = db.fetchone(
                "SELECT id FROM workers WHERE LOWER(name) = LOWER(?)",
                (manager_name,),
            )
            if mrow:
                manager_id = mrow["id"]
            else:
                # Allow tests to pass an already-resolved worker id directly.
                manager_id = manager_name

        worker = create_worker(
            db,
            name=name,
            role=role,
            team_id=team_id,
            cost=30,
            manager_id=manager_id,
        )
        return worker.id
    finally:
        db.close()


def _read_audit_log(org_path: Path) -> list[dict[str, Any]]:
    """Read the rules-audit.jsonl file. Empty list if file missing."""
    audit_path = org_path / "live" / "rules-audit.jsonl"
    if not audit_path.exists():
        return []
    return [
        json.loads(line)
        for line in audit_path.read_text().splitlines()
        if line.strip()
    ]


# ---------------------------------------------------------------------------
# Test catalog: one rule per severity, plus an ABSOLUTE pattern-match rule.
# ---------------------------------------------------------------------------

_SUGGESTED_RULES_YAML = """\
version: 1
rules:
  - id: pr-title-prefix
    severity: SUGGESTED
    actions: ["qn-org.hire"]
    description: "Prefer naming conventions on hire."
"""

_ENCOURAGED_RULES_YAML = """\
version: 1
rules:
  - id: tests-before-merge
    severity: ENCOURAGED
    actions: ["qn-bd.create"]
    description: "Justify with test results before filing the bead."
"""

_REQUIRED_RULES_YAML = """\
version: 1
rules:
  - id: no-fire-without-replacement-plan
    severity: REQUIRED
    actions: ["qn-org.fire"]
    description: "Direct-manager must approve via override bead."
"""

_ABSOLUTE_PATTERN_RULES_YAML = """\
version: 1
rules:
  - id: no-drop-database
    severity: ABSOLUTE
    actions: ["qn-bd.create"]
    description: "Refuse SQL containing DROP TABLE / DROP DATABASE / TRUNCATE."
    pattern:
      kind: regex
      target: body
      expr: "(?i)\\\\b(DROP\\\\s+TABLE|DROP\\\\s+DATABASE|TRUNCATE)\\\\b"
"""


# ===========================================================================
# Test 1 — SUGGESTED on qn org hire: proceeds, nudges to stderr, audits once.
# ===========================================================================


class TestSuggestedSeverityOnHire:
    """A SUGGESTED rule on qn-org.hire warns to stderr but proceeds."""

    def test_suggested_rule_warns_and_proceeds(
        self,
        runner: CliRunner,
        rules_org: Path,
    ) -> None:
        from cli.commands.main import qn
        from cli.core.rules.types import DecisionKind  # noqa: F401  (fail-import marker)

        _seed_rules(rules_org, _SUGGESTED_RULES_YAML)

        result = runner.invoke(
            qn,
            [
                "--org-path", str(rules_org),
                "org", "hire",
                "--name", "Bob",
                "--role", "engineer",
                "--manager", "alice",
                "--cost", "30",
            ],
        )

        # SUGGESTED proceeds (exit 0), nudges via stderr (or combined stream
        # depending on Click version).
        combined = _combined_output(result)
        assert result.exit_code == 0, (
            f"SUGGESTED must proceed; combined={combined!r}"
        )
        # The rule id (or its description fragment) MUST appear in stderr.
        assert "pr-title-prefix" in combined, (
            f"Expected nudge to mention rule id; combined={combined!r}"
        )

        # Audit log has exactly one entry for this evaluation.
        entries = _read_audit_log(rules_org)
        suggested_entries = [e for e in entries if e.get("rule_id") == "pr-title-prefix"]
        assert len(suggested_entries) == 1, (
            f"Expected exactly one audit entry for SUGGESTED rule; got {entries}"
        )
        assert suggested_entries[0]["action"] == "qn-org.hire"


# ===========================================================================
# Test 2 — ENCOURAGED on qn-bd create: blocks without --justify;
#                                       proceeds with worker-owned, non-empty bead.
# ===========================================================================


class TestEncouragedSeverityOnQnBdCreate:
    """ENCOURAGED requires --justify referencing a worker-owned non-empty bead."""

    def test_encouraged_blocks_without_justify(
        self,
        runner: CliRunner,
        rules_org: Path,
    ) -> None:
        from cli.commands.main import qn
        from cli.core.rules.types import DecisionKind  # noqa: F401

        _seed_rules(rules_org, _ENCOURAGED_RULES_YAML)
        worker_id = _seed_worker(rules_org, name="Eve", role="engineer", manager_name="Alice")

        with patch.dict(os.environ, {"QUINN_WORKER_ID": worker_id, "QUINN_ORG_PATH": str(rules_org)}):
            result = runner.invoke(
                qn,
                [
                    "--org-path", str(rules_org),
                    "qn-bd", "create",
                    "--type", "task",
                    "--title", "ship feature X",
                    # No --justify provided.
                ],
            )

        combined = _combined_output(result)
        assert result.exit_code != 0, (
            f"ENCOURAGED must BLOCK without --justify; got exit=0 combined={combined!r}"
        )
        assert "tests-before-merge" in combined, (
            "Block message must mention rule id"
        )

    def test_encouraged_with_valid_justify_proceeds(
        self,
        runner: CliRunner,
        rules_org: Path,
    ) -> None:
        from cli.commands.main import qn
        from cli.core.rules.types import DecisionKind  # noqa: F401

        _seed_rules(rules_org, _ENCOURAGED_RULES_YAML)
        worker_id = _seed_worker(rules_org, name="Eve", role="engineer", manager_name="Alice")

        # Pre-create a justify bead OWNED by `worker_id` with non-empty body.
        # The integration test relies on the (yet-to-exist) helper that the
        # qn-bd surface uses for bead lookup; until then we stub a minimal
        # JSONL bead record so the engine can find it.
        beads_dir = rules_org / ".beads"
        beads_dir.mkdir(parents=True, exist_ok=True)
        justify_bead_id = "quinn-ai-justify-1"
        bead_record = {
            "id": justify_bead_id,
            "owner": worker_id,
            "status": "open",
            "body": "test results pasted here, all green",
        }
        (beads_dir / "issues.jsonl").write_text(json.dumps(bead_record) + "\n")

        with patch.dict(os.environ, {"QUINN_WORKER_ID": worker_id, "QUINN_ORG_PATH": str(rules_org)}):
            result = runner.invoke(
                qn,
                [
                    "--org-path", str(rules_org),
                    "qn-bd", "create",
                    "--type", "task",
                    "--title", "ship feature X",
                    "--justify", justify_bead_id,
                ],
            )

        assert result.exit_code == 0, (
            f"ENCOURAGED with valid justify must proceed; combined={_combined_output(result)!r}"
        )

        # Audit log records the justify_bead used.
        entries = _read_audit_log(rules_org)
        matching = [
            e for e in entries
            if e.get("rule_id") == "tests-before-merge"
            and e.get("justify_bead") == justify_bead_id
        ]
        assert matching, (
            f"Audit log must record justify_bead={justify_bead_id}; got {entries}"
        )


# ===========================================================================
# Test 3 — REQUIRED on qn org fire: blocks without --override;
#                                    valid override (approver=manager) ALLOWS;
#                                    invalid override (wrong approver) BLOCKS.
# ===========================================================================


class TestRequiredSeverityOnFire:
    """REQUIRED needs --override <bead-id> approved by worker's *direct manager*."""

    def test_required_blocks_without_override(
        self,
        runner: CliRunner,
        rules_org: Path,
    ) -> None:
        from cli.commands.main import qn
        from cli.core.rules.types import DecisionKind  # noqa: F401

        _seed_rules(rules_org, _REQUIRED_RULES_YAML)
        # Alice (CEO) firing Bob; the firing worker (CEO) has no manager so
        # the engine should still BLOCK because no --override flag is set.
        bob_id = _seed_worker(rules_org, name="Bob", role="engineer", manager_name="Alice")

        result = runner.invoke(
            qn,
            [
                "--org-path", str(rules_org),
                "org", "fire",
                bob_id,
                "--reason", "performance",
            ],
        )

        combined = _combined_output(result)
        assert result.exit_code != 0, (
            f"REQUIRED must BLOCK without --override; combined={combined!r}"
        )
        assert "no-fire-without-replacement-plan" in combined

    def test_required_with_valid_override_proceeds(
        self,
        runner: CliRunner,
        rules_org: Path,
    ) -> None:
        from cli.commands.main import qn
        from cli.core.rules.types import DecisionKind  # noqa: F401

        _seed_rules(rules_org, _REQUIRED_RULES_YAML)
        bob_id = _seed_worker(rules_org, name="Bob", role="engineer", manager_name="Alice")
        # Worker doing the firing is "alice" the CEO. For this scenario, the
        # engine looks up alice's *direct manager*. CEO has no manager, so
        # for this test we run a non-CEO firing path: charlie (manager_id=alice)
        # tries to fire bob; charlie's direct manager is alice.
        charlie_id = _seed_worker(rules_org, name="Charlie", role="director", manager_name="Alice")

        # Pre-create the override bead, status=approved, approver_id == alice.
        beads_dir = rules_org / ".beads"
        beads_dir.mkdir(parents=True, exist_ok=True)
        override_bead_id = "quinn-ai-override-1"
        bead_record = {
            "id": override_bead_id,
            "owner": charlie_id,
            "status": "approved",
            "approver_id": "alice",
            "body": "approved by manager alice",
        }
        (beads_dir / "issues.jsonl").write_text(json.dumps(bead_record) + "\n")

        with patch.dict(os.environ, {"QUINN_WORKER_ID": charlie_id, "QUINN_ORG_PATH": str(rules_org)}):
            result = runner.invoke(
                qn,
                [
                    "--org-path", str(rules_org),
                    "org", "fire",
                    bob_id,
                    "--reason", "reorg",
                    "--override", override_bead_id,
                ],
            )

        assert result.exit_code == 0, (
            f"REQUIRED with valid manager-approved override must proceed; "
            f"combined={_combined_output(result)!r}"
        )

        # Audit log records override_bead.
        entries = _read_audit_log(rules_org)
        matching = [
            e for e in entries
            if e.get("rule_id") == "no-fire-without-replacement-plan"
            and e.get("override_bead") == override_bead_id
        ]
        assert matching, f"Audit log must record override_bead; got {entries}"

    def test_required_with_wrong_approver_still_blocks(
        self,
        runner: CliRunner,
        rules_org: Path,
    ) -> None:
        from cli.commands.main import qn
        from cli.core.rules.types import DecisionKind  # noqa: F401

        _seed_rules(rules_org, _REQUIRED_RULES_YAML)
        bob_id = _seed_worker(rules_org, name="Bob", role="engineer", manager_name="Alice")
        charlie_id = _seed_worker(rules_org, name="Charlie", role="director", manager_name="Alice")

        # Override bead is "approved" but approver_id is NOT charlie's direct
        # manager (alice). So the engine MUST still BLOCK.
        beads_dir = rules_org / ".beads"
        beads_dir.mkdir(parents=True, exist_ok=True)
        override_bead_id = "quinn-ai-override-bad"
        bead_record = {
            "id": override_bead_id,
            "owner": charlie_id,
            "status": "approved",
            "approver_id": "wrk-some-other-vp",  # NOT charlie's manager.
            "body": "approved by the wrong person",
        }
        (beads_dir / "issues.jsonl").write_text(json.dumps(bead_record) + "\n")

        with patch.dict(os.environ, {"QUINN_WORKER_ID": charlie_id, "QUINN_ORG_PATH": str(rules_org)}):
            result = runner.invoke(
                qn,
                [
                    "--org-path", str(rules_org),
                    "org", "fire",
                    bob_id,
                    "--reason", "reorg",
                    "--override", override_bead_id,
                ],
            )

        combined = _combined_output(result)
        assert result.exit_code != 0, (
            "REQUIRED with wrong-approver override must STILL BLOCK; "
            f"got exit=0 combined={combined!r}"
        )
        # Block must be from THE RULE (not e.g. unrelated permission failures)
        # — proves the engine is actually wired.
        assert "no-fire-without-replacement-plan" in combined, (
            "Block message must mention the rule id (engine must be the gate, "
            f"not some other failure mode); combined={combined!r}"
        )
        # Audit log records the BLOCK with the ineligible override bead.
        entries = _read_audit_log(rules_org)
        block_entries = [
            e for e in entries
            if e.get("rule_id") == "no-fire-without-replacement-plan"
            and e.get("decision") in ("block", "BLOCK")
        ]
        assert block_entries, (
            f"Audit log must record the rule-driven BLOCK; got entries={entries}"
        )


# ===========================================================================
# Test 4 — ABSOLUTE on qn-bd create with body containing DROP TABLE.
# ===========================================================================


class TestAbsoluteSeverityRefusesDropTable:
    """ABSOLUTE: --override and --justify are ignored. Block always."""

    def test_absolute_pattern_match_refuses_unconditionally(
        self,
        runner: CliRunner,
        rules_org: Path,
    ) -> None:
        from cli.commands.main import qn
        from cli.core.rules.types import DecisionKind  # noqa: F401

        _seed_rules(rules_org, _ABSOLUTE_PATTERN_RULES_YAML)
        worker_id = _seed_worker(rules_org, name="Eve", role="engineer", manager_name="Alice")

        # Even an "approved" override bead must NOT bypass an ABSOLUTE rule.
        beads_dir = rules_org / ".beads"
        beads_dir.mkdir(parents=True, exist_ok=True)
        override_bead_id = "quinn-ai-override-pretend"
        bead_record = {
            "id": override_bead_id,
            "owner": worker_id,
            "status": "approved",
            "approver_id": "alice",
            "body": "I really need this",
        }
        (beads_dir / "issues.jsonl").write_text(json.dumps(bead_record) + "\n")

        with patch.dict(os.environ, {"QUINN_WORKER_ID": worker_id, "QUINN_ORG_PATH": str(rules_org)}):
            result = runner.invoke(
                qn,
                [
                    "--org-path", str(rules_org),
                    "qn-bd", "create",
                    "--type", "task",
                    "--title", "schema migration",
                    "--notes", "Going to run: DROP TABLE old_users;",
                    "--override", override_bead_id,  # MUST be ignored.
                ],
            )

        combined = _combined_output(result)
        assert result.exit_code != 0, (
            f"ABSOLUTE must refuse unconditionally; combined={combined!r}"
        )
        assert "no-drop-database" in combined

        # Audit log records the block AND that the override flag was ignored.
        entries = _read_audit_log(rules_org)
        matching = [e for e in entries if e.get("rule_id") == "no-drop-database"]
        assert matching, f"Audit log must record ABSOLUTE block; got {entries}"
        assert matching[0]["decision"] in ("block", "BLOCK"), (
            f"Decision must be a BLOCK; got {matching[0]}"
        )


# ===========================================================================
# Test 5 — Decorator stacking: @requires_permission OUTER, @requires_rule_check INNER.
#                              Unauthorized worker → no rule eval, audit log empty.
# ===========================================================================


class TestDecoratorStackingOrder:
    """Per zm8a §5: permission gate runs first; rule gate only sees authorized calls."""

    def test_unauthorized_worker_does_not_trigger_rule_eval(
        self,
        runner: CliRunner,
        rules_org: Path,
    ) -> None:
        """If @requires_permission denies, no rule evaluation happens.

        Verification proxy: audit log has NO entry for the action because the
        rule check was never reached. (zm8a §5: "If permission denies, no rule
        eval happens — saves audit-log noise on unauthorized attempts.")
        """
        from cli.commands.main import qn
        from cli.core.rules.types import DecisionKind  # noqa: F401

        # Seed a SUGGESTED rule that WOULD log if reached.
        _seed_rules(rules_org, _SUGGESTED_RULES_YAML)

        # Try to invoke `qn org hire` as a worker who lacks hire permission.
        # We stage an unauthorized worker (Engineer-level, no hiring authority)
        # and put their id in QUINN_WORKER_ID.
        no_auth_id = _seed_worker(
            rules_org, name="Grunt", role="engineer", manager_name="Alice"
        )

        with patch.dict(os.environ, {"QUINN_WORKER_ID": no_auth_id, "QUINN_ORG_PATH": str(rules_org)}):
            result = runner.invoke(
                qn,
                [
                    "--org-path", str(rules_org),
                    "org", "hire",
                    "--name", "Bob",
                    "--role", "engineer",
                    "--manager", no_auth_id,
                    "--cost", "30",
                ],
            )

        # Permission gate denies → exit non-zero.
        assert result.exit_code != 0, (
            f"Unauthorized worker should be blocked at the permission gate; "
            f"combined={_combined_output(result)!r}"
        )

        # Crucial assertion: NO rule evaluation occurred → audit log is empty
        # for this action. (Earlier permission errors do NOT append to it.)
        entries = _read_audit_log(rules_org)
        rule_entries_for_hire = [e for e in entries if e.get("action") == "qn-org.hire"]
        assert rule_entries_for_hire == [], (
            f"Permission denial must not trigger rule evaluation; "
            f"got audit entries: {rule_entries_for_hire}"
        )


# ===========================================================================
# Test 6 — Kill-switch: QUINNAI_RULES_DISABLED=1 → all rules ALLOW with
#                       kill_switch_used=True flag in audit log.
# ===========================================================================


class TestKillSwitchEnvVar:
    """zm8a §3: env var swaps RuleEngine for DisabledRuleEngine."""

    def test_kill_switch_allows_absolute_rule_with_audit_flag(
        self,
        runner: CliRunner,
        rules_org: Path,
    ) -> None:
        from cli.commands.main import qn
        from cli.core.rules.types import DecisionKind  # noqa: F401

        # Even an ABSOLUTE rule on DROP TABLE should be allowed when the
        # kill-switch is set — operator emergency-override only.
        _seed_rules(rules_org, _ABSOLUTE_PATTERN_RULES_YAML)
        worker_id = _seed_worker(rules_org, name="Eve", role="engineer", manager_name="Alice")

        with patch.dict(
            os.environ,
            {
                "QUINNAI_RULES_DISABLED": "1",
                "QUINN_WORKER_ID": worker_id,
                "QUINN_ORG_PATH": str(rules_org),
            },
        ):
            result = runner.invoke(
                qn,
                [
                    "--org-path", str(rules_org),
                    "qn-bd", "create",
                    "--type", "task",
                    "--title", "schema migration",
                    "--notes", "Going to run: DROP TABLE old_users;",
                ],
            )

        # Kill switch → action proceeds even on ABSOLUTE rule.
        assert result.exit_code == 0, (
            f"QUINNAI_RULES_DISABLED=1 must let an ABSOLUTE-violating action through; "
            f"combined={_combined_output(result)!r}"
        )

        # And the audit log must mark this entry as kill-switch-used.
        entries = _read_audit_log(rules_org)
        kill_switch_entries = [e for e in entries if e.get("kill_switch_used") is True]
        assert kill_switch_entries, (
            f"Audit log must record kill_switch_used=True flag; got entries={entries}"
        )
