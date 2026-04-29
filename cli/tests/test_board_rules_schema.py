"""
Failing unit tests for the board-rules YAML schema parser & validator.

Spec sources (read these, not the bead description):
- quinn-ai-c5hb: user requirements (severity vocabulary SUGGESTED/ENCOURAGED/
  REQUIRED/ABSOLUTE; REQUIRED override = direct-manager approval, NOT board).
- quinn-ai-t2zb: system design — defines the rules.yaml schema (§A) and the
  in-memory data model in `cli.core.rules.types` (§B), specifically:
    - `Severity` enum (SUGGESTED|ENCOURAGED|REQUIRED|ABSOLUTE)
    - `Rule`, `RuleSet`, `Pattern`, `Scope` dataclasses
    - `load_rules(org_path)` loader entrypoint at `cli.core.rules.loader`

These tests fail today because `cli.core.rules` does not exist. Imports happen
inside test bodies (not at module top) so pytest can still *collect* each test
and report a per-test ImportError, giving a proper failing-test count.
Phase-4 implementation work makes them green.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def _write_rules_yaml(org_path: Path, body: str) -> Path:
    """Write rules.yaml under <org_path>/config/ and return its path."""
    config_dir = org_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    target = config_dir / "rules.yaml"
    target.write_text(body)
    return target


@pytest.fixture
def org_path(tmp_path: Path) -> Path:
    """A throwaway org root."""
    return tmp_path


# ---------------------------------------------------------------------------
# 1. Minimal-valid round-trip
# ---------------------------------------------------------------------------


class TestMinimalRoundTrip:
    """A minimal valid rules.yaml parses into a RuleSet with the right Rule objects."""

    def test_minimal_valid_yaml_round_trips_to_ruleset(self, org_path: Path) -> None:
        from cli.core.rules import loader as rules_loader
        from cli.core.rules.types import Rule, RuleSet, Severity

        _write_rules_yaml(
            org_path,
            """
version: 1
rules:
  - id: no-drop-database
    severity: ABSOLUTE
    actions:
      - "qn-bd.create"
    description: "Refuse SQL containing DROP TABLE / DROP DATABASE / TRUNCATE."
""",
        )

        ruleset: RuleSet = rules_loader.load_rules(org_path)

        assert isinstance(ruleset, RuleSet)
        assert ruleset.version == 1
        assert len(ruleset.rules) == 1

        rule: Rule = ruleset.rules[0]
        assert isinstance(rule, Rule)
        assert rule.id == "no-drop-database"
        assert rule.severity == Severity.ABSOLUTE
        assert rule.actions == ("qn-bd.create",)
        assert "DROP TABLE" in rule.description

    def test_minimal_valid_yaml_round_trips_all_four_severities(
        self, org_path: Path
    ) -> None:
        """All four severity strings parse into the Severity enum."""
        from cli.core.rules import loader as rules_loader
        from cli.core.rules.types import Severity

        _write_rules_yaml(
            org_path,
            """
version: 1
rules:
  - id: r-suggested
    severity: SUGGESTED
    actions: ["msgr.send"]
    description: "soft nudge"
  - id: r-encouraged
    severity: ENCOURAGED
    actions: ["qn-bd.create"]
    description: "produce an artifact"
  - id: r-required
    severity: REQUIRED
    actions: ["qn-org.fire"]
    description: "manager approval"
  - id: r-absolute
    severity: ABSOLUTE
    actions: ["qn-bd.create"]
    description: "hard refusal"
""",
        )

        ruleset = rules_loader.load_rules(org_path)
        sev_by_id = {r.id: r.severity for r in ruleset.rules}

        assert sev_by_id["r-suggested"] == Severity.SUGGESTED
        assert sev_by_id["r-encouraged"] == Severity.ENCOURAGED
        assert sev_by_id["r-required"] == Severity.REQUIRED
        assert sev_by_id["r-absolute"] == Severity.ABSOLUTE


# ---------------------------------------------------------------------------
# 2. Severity validation
# ---------------------------------------------------------------------------


class TestSeverityValidation:
    """Unknown severity strings rejected with a clear, actionable error."""

    @pytest.mark.parametrize(
        "bogus_severity",
        [
            "soft",
            "ADVISORY",  # the stale vocabulary; loader must reject
            "ENFORCED",
            "warn",
            "absolute",  # case-sensitive, lowercase rejected
            "MAYBE",
        ],
    )
    def test_unknown_severity_rejected(
        self, org_path: Path, bogus_severity: str
    ) -> None:
        from cli.core.rules import loader as rules_loader

        _write_rules_yaml(
            org_path,
            f"""
version: 1
rules:
  - id: bad-rule
    severity: {bogus_severity!r}
    actions: ["qn-bd.create"]
    description: "x"
""",
        )

        with pytest.raises(Exception) as exc_info:
            rules_loader.load_rules(org_path)

        msg = str(exc_info.value).lower()
        # Error must name the offending field; be lenient on exact phrasing.
        assert "severity" in msg


# ---------------------------------------------------------------------------
# 3. Required-field validation
# ---------------------------------------------------------------------------


class TestRequiredFields:
    """Rules missing required fields (id/severity/actions/description) rejected."""

    @pytest.mark.parametrize(
        "missing_field,yaml_body",
        [
            (
                "id",
                """
version: 1
rules:
  - severity: SUGGESTED
    actions: ["msgr.send"]
    description: "no id"
""",
            ),
            (
                "severity",
                """
version: 1
rules:
  - id: no-sev
    actions: ["msgr.send"]
    description: "no severity"
""",
            ),
            (
                "actions",
                """
version: 1
rules:
  - id: no-actions
    severity: SUGGESTED
    description: "no actions"
""",
            ),
            (
                "description",
                """
version: 1
rules:
  - id: no-desc
    severity: SUGGESTED
    actions: ["msgr.send"]
""",
            ),
        ],
    )
    def test_missing_required_field_rejected(
        self, org_path: Path, missing_field: str, yaml_body: str
    ) -> None:
        from cli.core.rules import loader as rules_loader

        _write_rules_yaml(org_path, yaml_body)

        with pytest.raises(Exception) as exc_info:
            rules_loader.load_rules(org_path)

        msg = str(exc_info.value).lower()
        assert missing_field in msg


# ---------------------------------------------------------------------------
# 4. Duplicate-id validation
# ---------------------------------------------------------------------------


class TestDuplicateIds:
    """Duplicate rule ids within the same file are rejected."""

    def test_duplicate_ids_rejected(self, org_path: Path) -> None:
        from cli.core.rules import loader as rules_loader

        _write_rules_yaml(
            org_path,
            """
version: 1
rules:
  - id: dup-rule
    severity: SUGGESTED
    actions: ["msgr.send"]
    description: "first"
  - id: dup-rule
    severity: ABSOLUTE
    actions: ["qn-bd.create"]
    description: "second"
""",
        )

        with pytest.raises(Exception) as exc_info:
            rules_loader.load_rules(org_path)

        msg = str(exc_info.value).lower()
        assert "dup-rule" in msg or "duplicate" in msg


# ---------------------------------------------------------------------------
# 5. Pattern-block validation
# ---------------------------------------------------------------------------


class TestPatternValidation:
    """Invalid regex in pattern.expr is rejected at load (fail-closed)."""

    def test_invalid_regex_rejected_at_load(self, org_path: Path) -> None:
        from cli.core.rules import loader as rules_loader

        _write_rules_yaml(
            org_path,
            """
version: 1
rules:
  - id: bad-regex
    severity: ABSOLUTE
    actions: ["qn-bd.create"]
    description: "pattern won't compile"
    pattern:
      kind: regex
      target: body
      expr: "(unbalanced"
""",
        )

        with pytest.raises(Exception) as exc_info:
            rules_loader.load_rules(org_path)

        msg = str(exc_info.value).lower()
        assert "regex" in msg or "pattern" in msg or "compile" in msg

    def test_valid_pattern_block_parses(self, org_path: Path) -> None:
        """A well-formed pattern block lands on the Rule as a Pattern instance."""
        from cli.core.rules import loader as rules_loader
        from cli.core.rules.types import Pattern

        _write_rules_yaml(
            org_path,
            r"""
version: 1
rules:
  - id: drop-tables
    severity: ABSOLUTE
    actions: ["qn-bd.create"]
    description: "no drop tables"
    pattern:
      kind: regex
      target: body
      expr: "(?i)\\bDROP\\s+TABLE\\b"
""",
        )

        ruleset = rules_loader.load_rules(org_path)
        rule = ruleset.rules[0]
        assert isinstance(rule.pattern, Pattern)
        assert rule.pattern.kind == "regex"
        assert rule.pattern.target == "body"
        assert "DROP" in rule.pattern.expr


# ---------------------------------------------------------------------------
# 6. Scope-block parsing
# ---------------------------------------------------------------------------


class TestScopeBlockParsing:
    """The scope block parses correctly into a Scope object."""

    def test_scope_block_parses_all_keys(self, org_path: Path) -> None:
        from cli.core.rules import loader as rules_loader

        _write_rules_yaml(
            org_path,
            """
version: 1
rules:
  - id: prod-only-rule
    severity: REQUIRED
    actions: ["qn-org.fire"]
    description: "only fires in prod"
    scope:
      env: prod
      worker_role: Engineer
      worker_role_min_level: 2
""",
        )

        ruleset = rules_loader.load_rules(org_path)
        rule = ruleset.rules[0]
        assert rule.scope is not None
        assert rule.scope.env == "prod"
        assert rule.scope.worker_role == "Engineer"
        assert rule.scope.worker_role_min_level == 2

    def test_scope_block_absent_yields_none_scope(self, org_path: Path) -> None:
        from cli.core.rules import loader as rules_loader

        _write_rules_yaml(
            org_path,
            """
version: 1
rules:
  - id: global-rule
    severity: SUGGESTED
    actions: ["msgr.send"]
    description: "applies everywhere"
""",
        )

        ruleset = rules_loader.load_rules(org_path)
        rule = ruleset.rules[0]
        assert rule.scope is None


# ---------------------------------------------------------------------------
# Smoke-level type assertion: the public types module exposes the names the
# design pins. Phase-4 loader code depends on these existing.
# ---------------------------------------------------------------------------


def test_public_types_module_exports_expected_names() -> None:
    from cli.core.rules.types import Pattern, Rule, RuleSet, Severity

    for obj, name in (
        (Severity, "Severity"),
        (Rule, "Rule"),
        (RuleSet, "RuleSet"),
        (Pattern, "Pattern"),
    ):
        assert obj is not None, f"{name} missing from cli.core.rules.types"
