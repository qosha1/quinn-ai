"""
Failing unit tests for `RuleEngine.evaluate()` severity behavior.

Spec sources (read these, not the bead description — the bead description's
'SOFT/ADVISORY/ENFORCED' vocabulary and 'Decision.allow/warn/block' API are
stale; the t2zb design supersedes them):
- quinn-ai-c5hb §1, §1a, §1b — severity vocabulary and override flow.
- quinn-ai-t2zb §B — `DecisionKind` enum (ALLOW, BLOCK, ALLOW_WITH_NUDGE,
  REQUIRES_JUSTIFY, REQUIRES_OVERRIDE) and the `Decision` dataclass.
- quinn-ai-t2zb §C — `RuleEngine(ruleset, db, logger).evaluate(action, context,
  *, justify_bead_id=None, override_bead_id=None) -> Decision`.
- quinn-ai-t2zb §D — REQUIRED override = direct-manager approval (not board).
- quinn-ai-t2zb §D.3 — ENCOURAGED `--justify` artifact substrate.
- quinn-ai-t2zb §E — every evaluate() emits exactly one audit log line.

Per-severity expectations:
- SUGGESTED: matched -> ALLOW_WITH_NUDGE; not matched -> ALLOW; nudge has a
  non-empty message; audit logs the evaluation; no flag bypasses needed.
- ENCOURAGED: REQUIRES_JUSTIFY when no justify_bead_id; ALLOW when justify-bead
  is worker-owned with a non-empty body; BLOCK when missing/wrong-owner/empty.
  Audit logs the justify bead used.
- REQUIRED: REQUIRES_OVERRIDE when no override_bead_id; ALLOW when override-bead
  is approved AND approver == worker's direct manager; BLOCK otherwise.
  Audit logs the override usage.
- ABSOLUTE: always BLOCK; override_bead_id and justify_bead_id are ignored —
  bead presence does NOT change the outcome. Audit logs the rejection.

These tests fail today because `cli.core.rules` does not exist. Imports happen
inside test bodies so pytest collects each test individually.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helper builders — they all import from cli.core.rules inside the function so
# import failures surface per-test (not at collection time).
# ---------------------------------------------------------------------------


def _make_rule(
    *,
    rule_id: str,
    severity_name: str,
    actions: tuple[str, ...] = ("qn-bd.create",),
    description: str = "test rule",
) -> Any:
    """Construct a Rule object with the requested severity."""
    from cli.core.rules.types import Rule, Severity

    return Rule(
        id=rule_id,
        severity=Severity[severity_name],
        actions=actions,
        description=description,
    )


def _make_ruleset(rules: tuple[Any, ...]) -> Any:
    from cli.core.rules.types import RuleSet

    return RuleSet(version=1, rules=rules, source_path="/tmp/rules.yaml")


def _make_engine(
    ruleset: Any,
    *,
    bead_lookup: dict[str, dict[str, Any]] | None = None,
    manager_of: dict[str, str] | None = None,
) -> tuple[Any, MagicMock]:
    """Construct a RuleEngine wired to fake db + audit logger.

    The fake db answers two operations the engine needs (per t2zb §D):
    - `get_bead(bead_id)` -> {"owner": ..., "status": ..., "approver_id": ...,
      "body": ...} or None when not found.
    - `get_direct_manager(worker_id)` -> manager worker_id or None.

    Returns (engine, audit_logger_mock) so each test can assert on audit calls.
    """
    from cli.core.rules.engine import RuleEngine

    db = MagicMock()
    bead_lookup = bead_lookup or {}
    manager_of = manager_of or {}

    db.get_bead.side_effect = lambda bid: bead_lookup.get(bid)
    db.get_direct_manager.side_effect = lambda wid: manager_of.get(wid)

    audit_logger = MagicMock()

    engine = RuleEngine(ruleset, db, audit_logger)
    return engine, audit_logger


def _basic_context(worker_id: str = "wrk-alice") -> dict[str, Any]:
    return {
        "worker_id": worker_id,
        "worker_role": "Engineer",
        "worker_role_level": 2,
        "env": "dev",
        "args": {},
        "body": "some body",
        "target_paths": [],
    }


# ===========================================================================
# SUGGESTED — 4 tests
# ===========================================================================


class TestSuggestedSeverity:
    """SUGGESTED: matched -> ALLOW_WITH_NUDGE; unmatched -> ALLOW."""

    def test_matched_suggested_returns_allow_with_nudge(self) -> None:
        from cli.core.rules.types import DecisionKind

        rule = _make_rule(
            rule_id="prefer-bead-over-broadcast",
            severity_name="SUGGESTED",
            actions=("msgr.send",),
            description="route task-shaped messages through beads",
        )
        engine, _audit = _make_engine(_make_ruleset((rule,)))

        decision = engine.evaluate("msgr.send", _basic_context())

        assert decision.kind == DecisionKind.ALLOW_WITH_NUDGE
        assert decision.rule is not None
        assert decision.rule.id == "prefer-bead-over-broadcast"

    def test_unmatched_action_returns_plain_allow(self) -> None:
        """A SUGGESTED rule scoped to msgr.send should NOT fire on qn-org.hire."""
        from cli.core.rules.types import DecisionKind

        rule = _make_rule(
            rule_id="prefer-bead-over-broadcast",
            severity_name="SUGGESTED",
            actions=("msgr.send",),
        )
        engine, _audit = _make_engine(_make_ruleset((rule,)))

        decision = engine.evaluate("qn-org.hire", _basic_context())

        assert decision.kind == DecisionKind.ALLOW
        assert decision.rule is None

    def test_suggested_message_is_non_empty(self) -> None:
        """The nudge message that workers see must not be blank."""
        rule = _make_rule(
            rule_id="pr-title-prefix",
            severity_name="SUGGESTED",
            actions=("qn-bd.create",),
            description="prefix PRs touching cli/core/ with the module name",
        )
        engine, _audit = _make_engine(_make_ruleset((rule,)))

        decision = engine.evaluate("qn-bd.create", _basic_context())

        assert decision.message is not None
        assert len(decision.message.strip()) > 0

    def test_suggested_evaluation_writes_audit_log(self) -> None:
        """SUGGESTED matches still produce one audit log entry per t2zb §E."""
        rule = _make_rule(
            rule_id="no-trivial-ceo-dm",
            severity_name="SUGGESTED",
            actions=("msgr.send",),
        )
        engine, audit = _make_engine(_make_ruleset((rule,)))

        engine.evaluate("msgr.send", _basic_context())

        assert audit.log.called or audit.write.called or audit.record.called, (
            "SUGGESTED evaluation must emit exactly one audit log line"
        )


# ===========================================================================
# ENCOURAGED — 4 tests
# ===========================================================================


class TestEncouragedSeverity:
    """ENCOURAGED: requires a worker-owned non-empty justify bead."""

    def test_encouraged_no_justify_returns_requires_justify(self) -> None:
        from cli.core.rules.types import DecisionKind

        rule = _make_rule(
            rule_id="tests-before-merge",
            severity_name="ENCOURAGED",
            actions=("qn-bd.create",),
        )
        engine, _audit = _make_engine(_make_ruleset((rule,)))

        decision = engine.evaluate(
            "qn-bd.create", _basic_context(), justify_bead_id=None
        )

        assert decision.kind == DecisionKind.REQUIRES_JUSTIFY
        assert decision.rule is not None
        assert decision.rule.id == "tests-before-merge"

    def test_encouraged_valid_justify_returns_allow(self) -> None:
        """justify-bead is owned by the worker AND has non-empty body -> ALLOW."""
        from cli.core.rules.types import DecisionKind

        rule = _make_rule(
            rule_id="okr-link-on-features",
            severity_name="ENCOURAGED",
            actions=("qn-bd.create",),
        )
        beads = {
            "bd-ok-1": {
                "owner": "wrk-alice",
                "status": "open",
                "body": "test results pasted here, all green",
            },
        }
        engine, audit = _make_engine(_make_ruleset((rule,)), bead_lookup=beads)

        decision = engine.evaluate(
            "qn-bd.create", _basic_context("wrk-alice"), justify_bead_id="bd-ok-1"
        )

        assert decision.kind == DecisionKind.ALLOW
        # And the audit log records which bead was used to justify.
        assert (
            audit.log.called or audit.write.called or audit.record.called
        ), "ENCOURAGED ALLOW must emit an audit log line"

    @pytest.mark.parametrize(
        "case_label,bead_record",
        [
            (
                "wrong-owner",
                {"owner": "wrk-bob", "status": "open", "body": "real body"},
            ),
            (
                "empty-body",
                {"owner": "wrk-alice", "status": "open", "body": "   "},
            ),
            (
                "missing",
                None,  # _make_engine treats absence as "bead not found"
            ),
        ],
    )
    def test_encouraged_invalid_justify_returns_block(
        self, case_label: str, bead_record: dict[str, Any] | None
    ) -> None:
        """Wrong-owner / empty-body / missing justify bead all BLOCK."""
        from cli.core.rules.types import DecisionKind

        rule = _make_rule(
            rule_id="coverage-floor",
            severity_name="ENCOURAGED",
            actions=("qn-bd.create",),
        )
        beads: dict[str, dict[str, Any]] = {}
        if bead_record is not None:
            beads["bd-bad"] = bead_record

        engine, _audit = _make_engine(_make_ruleset((rule,)), bead_lookup=beads)

        decision = engine.evaluate(
            "qn-bd.create",
            _basic_context("wrk-alice"),
            justify_bead_id="bd-bad",
        )

        assert decision.kind == DecisionKind.BLOCK, (
            f"case={case_label!r} should BLOCK but got {decision.kind!r}"
        )

    def test_encouraged_audit_records_justify_bead_id(self) -> None:
        """Audit log includes the justify_bead_id field per t2zb §E."""
        rule = _make_rule(
            rule_id="okr-link-on-features",
            severity_name="ENCOURAGED",
            actions=("qn-bd.create",),
        )
        beads = {
            "bd-justify-42": {
                "owner": "wrk-alice",
                "status": "open",
                "body": "linked OKR rationale here",
            },
        }
        engine, audit = _make_engine(_make_ruleset((rule,)), bead_lookup=beads)

        engine.evaluate(
            "qn-bd.create",
            _basic_context("wrk-alice"),
            justify_bead_id="bd-justify-42",
        )

        # Check any of the plausible audit method names; collect their calls.
        all_calls = (
            list(audit.log.call_args_list)
            + list(audit.write.call_args_list)
            + list(audit.record.call_args_list)
        )
        flat_repr = repr(all_calls)
        assert "bd-justify-42" in flat_repr, (
            "audit log must include justify_bead_id used"
        )


# ===========================================================================
# REQUIRED — 4 tests
# ===========================================================================


class TestRequiredSeverity:
    """REQUIRED: needs an override bead approved by the worker's direct manager."""

    def test_required_no_override_returns_requires_override(self) -> None:
        from cli.core.rules.types import DecisionKind

        rule = _make_rule(
            rule_id="no-fire-without-replacement-plan",
            severity_name="REQUIRED",
            actions=("qn-org.fire",),
        )
        engine, _audit = _make_engine(
            _make_ruleset((rule,)),
            manager_of={"wrk-alice": "wrk-mgr"},
        )

        decision = engine.evaluate(
            "qn-org.fire",
            _basic_context("wrk-alice"),
            override_bead_id=None,
        )

        assert decision.kind == DecisionKind.REQUIRES_OVERRIDE
        assert decision.rule is not None
        assert decision.rule.id == "no-fire-without-replacement-plan"

    def test_required_valid_override_by_direct_manager_returns_allow(self) -> None:
        """status=approved AND approver_id == worker's direct manager -> ALLOW."""
        from cli.core.rules.types import DecisionKind

        rule = _make_rule(
            rule_id="cross-team-hire",
            severity_name="REQUIRED",
            actions=("qn-org.hire",),
        )
        beads = {
            "bd-override-7": {
                "owner": "wrk-alice",
                "status": "approved",
                "approver_id": "wrk-mgr",
                "body": "approved by manager",
            },
        }
        engine, audit = _make_engine(
            _make_ruleset((rule,)),
            bead_lookup=beads,
            manager_of={"wrk-alice": "wrk-mgr"},
        )

        decision = engine.evaluate(
            "qn-org.hire",
            _basic_context("wrk-alice"),
            override_bead_id="bd-override-7",
        )

        assert decision.kind == DecisionKind.ALLOW
        # Audit log should record the override bead id.
        all_calls = (
            list(audit.log.call_args_list)
            + list(audit.write.call_args_list)
            + list(audit.record.call_args_list)
        )
        assert "bd-override-7" in repr(all_calls), (
            "audit log must include the override bead id used"
        )

    @pytest.mark.parametrize(
        "case_label,bead_record,manager_map",
        [
            (
                "approved-but-wrong-approver",
                {
                    "owner": "wrk-alice",
                    "status": "approved",
                    "approver_id": "wrk-some-other-vp",  # NOT alice's direct manager
                    "body": "approved",
                },
                {"wrk-alice": "wrk-mgr"},
            ),
            (
                "open-not-approved",
                {
                    "owner": "wrk-alice",
                    "status": "open",
                    "approver_id": "wrk-mgr",
                    "body": "still open",
                },
                {"wrk-alice": "wrk-mgr"},
            ),
            (
                "rejected",
                {
                    "owner": "wrk-alice",
                    "status": "rejected",
                    "approver_id": "wrk-mgr",
                    "body": "manager said no",
                },
                {"wrk-alice": "wrk-mgr"},
            ),
            (
                "missing-bead",
                None,
                {"wrk-alice": "wrk-mgr"},
            ),
        ],
    )
    def test_required_invalid_override_returns_block(
        self,
        case_label: str,
        bead_record: dict[str, Any] | None,
        manager_map: dict[str, str],
    ) -> None:
        """status != approved OR wrong approver OR missing -> BLOCK."""
        from cli.core.rules.types import DecisionKind

        rule = _make_rule(
            rule_id="budget-allocation-cap",
            severity_name="REQUIRED",
            actions=("qn-org.budget-allocate",),
        )
        beads: dict[str, dict[str, Any]] = {}
        if bead_record is not None:
            beads["bd-override-bad"] = bead_record

        engine, _audit = _make_engine(
            _make_ruleset((rule,)),
            bead_lookup=beads,
            manager_of=manager_map,
        )

        decision = engine.evaluate(
            "qn-org.budget-allocate",
            _basic_context("wrk-alice"),
            override_bead_id="bd-override-bad",
        )

        assert decision.kind == DecisionKind.BLOCK, (
            f"case={case_label!r} should BLOCK but got {decision.kind!r}"
        )

    def test_required_resolves_manager_via_org_chart(self) -> None:
        """Engine looks up worker's direct manager via db.get_direct_manager."""
        from cli.core.rules.types import DecisionKind

        rule = _make_rule(
            rule_id="okr-set-mid-quarter",
            severity_name="REQUIRED",
            actions=("qn-org.okr-set",),
        )
        beads = {
            "bd-1": {
                "owner": "wrk-alice",
                "status": "approved",
                "approver_id": "wrk-mgr",
                "body": "ok",
            },
        }
        engine, _audit = _make_engine(
            _make_ruleset((rule,)),
            bead_lookup=beads,
            manager_of={"wrk-alice": "wrk-mgr"},
        )

        decision = engine.evaluate(
            "qn-org.okr-set",
            _basic_context("wrk-alice"),
            override_bead_id="bd-1",
        )

        assert decision.kind == DecisionKind.ALLOW
        # Verify the engine actually consulted the org-chart resolver.
        engine.db.get_direct_manager.assert_called_with("wrk-alice")


# ===========================================================================
# ABSOLUTE — 4 tests
# ===========================================================================


class TestAbsoluteSeverity:
    """ABSOLUTE: always BLOCK; override/justify are ignored."""

    def test_absolute_blocks_with_no_flags(self) -> None:
        from cli.core.rules.types import DecisionKind

        rule = _make_rule(
            rule_id="no-drop-database",
            severity_name="ABSOLUTE",
            actions=("qn-bd.create",),
        )
        engine, _audit = _make_engine(_make_ruleset((rule,)))

        decision = engine.evaluate("qn-bd.create", _basic_context())

        assert decision.kind == DecisionKind.BLOCK
        assert decision.rule is not None
        assert decision.rule.id == "no-drop-database"

    def test_absolute_ignores_override_bead(self) -> None:
        """Even an approved override bead does NOT unblock an ABSOLUTE rule."""
        from cli.core.rules.types import DecisionKind

        rule = _make_rule(
            rule_id="no-rm-rf-storage",
            severity_name="ABSOLUTE",
            actions=("qn-bd.create",),
        )
        beads = {
            "bd-approved": {
                "owner": "wrk-alice",
                "status": "approved",
                "approver_id": "wrk-mgr",
                "body": "approved by manager",
            },
        }
        engine, _audit = _make_engine(
            _make_ruleset((rule,)),
            bead_lookup=beads,
            manager_of={"wrk-alice": "wrk-mgr"},
        )

        decision = engine.evaluate(
            "qn-bd.create",
            _basic_context("wrk-alice"),
            override_bead_id="bd-approved",
        )

        assert decision.kind == DecisionKind.BLOCK, (
            "ABSOLUTE rules must ignore override beads"
        )

    def test_absolute_ignores_justify_bead(self) -> None:
        """Even a perfect justify bead does NOT unblock an ABSOLUTE rule."""
        from cli.core.rules.types import DecisionKind

        rule = _make_rule(
            rule_id="no-force-push-main",
            severity_name="ABSOLUTE",
            actions=("qn-bd.create",),
        )
        beads = {
            "bd-justify": {
                "owner": "wrk-alice",
                "status": "open",
                "body": "I really really need to do this",
            },
        }
        engine, _audit = _make_engine(_make_ruleset((rule,)), bead_lookup=beads)

        decision = engine.evaluate(
            "qn-bd.create",
            _basic_context("wrk-alice"),
            justify_bead_id="bd-justify",
        )

        assert decision.kind == DecisionKind.BLOCK, (
            "ABSOLUTE rules must ignore justify beads"
        )

    def test_absolute_evaluation_writes_audit_log(self) -> None:
        """ABSOLUTE rejection is audited (the most important kind to record)."""
        rule = _make_rule(
            rule_id="no-secret-commit",
            severity_name="ABSOLUTE",
            actions=("qn-bd.create",),
        )
        engine, audit = _make_engine(_make_ruleset((rule,)))

        engine.evaluate("qn-bd.create", _basic_context())

        assert audit.log.called or audit.write.called or audit.record.called, (
            "ABSOLUTE rejections must emit an audit log line"
        )


# ===========================================================================
# Cross-severity sanity: 4 + 4 + 4 + 4 = 16 dedicated tests above. The block
# below adds two more tests that don't belong to a single severity but exercise
# the engine API surface.
# ===========================================================================


class TestEngineApiSurface:
    """Cross-cutting engine behavior."""

    def test_evaluate_with_no_rules_returns_plain_allow(self) -> None:
        from cli.core.rules.types import DecisionKind

        engine, _audit = _make_engine(_make_ruleset(()))

        decision = engine.evaluate("qn-bd.create", _basic_context())

        assert decision.kind == DecisionKind.ALLOW
        assert decision.rule is None

    def test_evaluate_action_not_in_any_rule_returns_allow(self) -> None:
        """Rules scoped to other actions don't fire on this action."""
        from cli.core.rules.types import DecisionKind

        rule = _make_rule(
            rule_id="r-msgr",
            severity_name="ABSOLUTE",
            actions=("msgr.send",),
        )
        engine, _audit = _make_engine(_make_ruleset((rule,)))

        decision = engine.evaluate("qn-org.hire", _basic_context())

        assert decision.kind == DecisionKind.ALLOW
        assert decision.rule is None
