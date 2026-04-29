"""
Failing unit tests for the board-rules loader.

Spec sources:
- quinn-ai-c5hb §3 — the 14-rule default catalog ships with QuinnAI and is
  loaded automatically when an org has no rules.yaml of its own.
- quinn-ai-t2zb §G — `cli.core.rules.loader.load_rules(org_path: Path) -> RuleSet`
  reads `<org_path>/config/rules.yaml`. Falls back to the bundled default
  catalog when the file is absent. Fails closed on parse errors.
- quinn-ai-t2zb §I — empty `rules: []` (with `version: 1`) is valid and
  produces a RuleSet with zero rules — operator's explicit choice.

These tests fail today because `cli.core.rules` does not exist. Imports happen
inside test bodies so pytest can collect each test individually and report
per-test ImportError rather than a single collection error.
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
# 1. Default-catalog fallback when no rules.yaml exists
# ---------------------------------------------------------------------------


class TestDefaultCatalogFallback:
    """`load_rules(org_path)` with no rules.yaml falls back to the default
    14-rule catalog (per c5hb §3) — NOT empty, NOT an error."""

    def test_missing_rules_yaml_loads_default_catalog(self, org_path: Path) -> None:
        from cli.core.rules import loader as rules_loader
        from cli.core.rules.types import RuleSet

        # Note: org_path has no config/rules.yaml.
        ruleset = rules_loader.load_rules(org_path)

        assert isinstance(ruleset, RuleSet)
        # The default catalog has 14 rules per quinn-ai-c5hb §3.
        assert len(ruleset.rules) == 14, (
            "expected the bundled 14-rule default catalog when no rules.yaml is present"
        )

    def test_default_catalog_covers_all_four_severities(self, org_path: Path) -> None:
        """The default catalog spans SUGGESTED, ENCOURAGED, REQUIRED, ABSOLUTE."""
        from cli.core.rules import loader as rules_loader
        from cli.core.rules.types import Severity

        ruleset = rules_loader.load_rules(org_path)
        severities_seen = {r.severity for r in ruleset.rules}

        assert Severity.SUGGESTED in severities_seen
        assert Severity.ENCOURAGED in severities_seen
        assert Severity.REQUIRED in severities_seen
        assert Severity.ABSOLUTE in severities_seen

    def test_default_catalog_includes_named_absolute_rules(
        self, org_path: Path
    ) -> None:
        """Per c5hb §3, the default catalog includes specific ABSOLUTE rules."""
        from cli.core.rules import loader as rules_loader

        ruleset = rules_loader.load_rules(org_path)
        rule_ids = {r.id for r in ruleset.rules}

        # Rules 11-14 in c5hb §3.
        for expected_id in (
            "no-drop-database",
            "no-rm-rf-storage",
            "no-force-push-main",
            "no-secret-commit",
        ):
            assert expected_id in rule_ids, (
                f"expected {expected_id} in default catalog"
            )


# ---------------------------------------------------------------------------
# 2. Malformed YAML -> descriptive fail-closed error
# ---------------------------------------------------------------------------


class TestMalformedYaml:
    """Malformed YAML raises a descriptive error citing file path + parse location."""

    def test_malformed_yaml_raises_descriptive_error(self, org_path: Path) -> None:
        from cli.core.rules import loader as rules_loader

        target = _write_rules_yaml(
            org_path,
            "version: 1\nrules:\n  - id: broken\n    severity: [unclosed-list\n",
        )

        with pytest.raises(Exception) as exc_info:
            rules_loader.load_rules(org_path)

        msg = str(exc_info.value)
        # Path to the offending file should appear in the error.
        assert str(target) in msg or "rules.yaml" in msg
        # Parse-level signal should be present (line/column or 'parse'/'yaml').
        lower = msg.lower()
        assert any(token in lower for token in ("line", "yaml", "parse", "column"))


# ---------------------------------------------------------------------------
# 3. Loader idempotency
# ---------------------------------------------------------------------------


class TestLoaderIdempotency:
    """Calling load_rules twice with same input yields equal RuleSets."""

    def test_loader_is_idempotent(self, org_path: Path) -> None:
        from cli.core.rules import loader as rules_loader

        _write_rules_yaml(
            org_path,
            """
version: 1
rules:
  - id: r-one
    severity: SUGGESTED
    actions: ["msgr.send"]
    description: "first"
  - id: r-two
    severity: ABSOLUTE
    actions: ["qn-bd.create"]
    description: "second"
""",
        )

        rs_a = rules_loader.load_rules(org_path)
        rs_b = rules_loader.load_rules(org_path)

        assert rs_a == rs_b
        assert tuple(r.id for r in rs_a.rules) == tuple(r.id for r in rs_b.rules)


# ---------------------------------------------------------------------------
# 4. Deterministic sort order
# ---------------------------------------------------------------------------


class TestDeterministicOrder:
    """Rules are sorted deterministically by id so the engine sees a stable order."""

    def test_rules_sorted_by_id(self, org_path: Path) -> None:
        from cli.core.rules import loader as rules_loader

        _write_rules_yaml(
            org_path,
            """
version: 1
rules:
  - id: zebra-rule
    severity: SUGGESTED
    actions: ["msgr.send"]
    description: "z"
  - id: alpha-rule
    severity: ABSOLUTE
    actions: ["qn-bd.create"]
    description: "a"
  - id: middle-rule
    severity: REQUIRED
    actions: ["qn-org.fire"]
    description: "m"
""",
        )

        ruleset = rules_loader.load_rules(org_path)
        observed_ids = [r.id for r in ruleset.rules]

        assert observed_ids == sorted(observed_ids), (
            "rules must come out sorted by id for deterministic engine order"
        )
        assert observed_ids == ["alpha-rule", "middle-rule", "zebra-rule"]


# ---------------------------------------------------------------------------
# 5. Empty `rules: []` is valid (operator's explicit choice)
# ---------------------------------------------------------------------------


class TestExplicitlyEmptyRules:
    """`version: 1` with `rules: []` is valid — operator turned everything off."""

    def test_empty_rules_yields_zero_rule_ruleset(self, org_path: Path) -> None:
        from cli.core.rules import loader as rules_loader
        from cli.core.rules.types import RuleSet

        _write_rules_yaml(
            org_path,
            """
version: 1
rules: []
""",
        )

        ruleset = rules_loader.load_rules(org_path)

        assert isinstance(ruleset, RuleSet)
        assert ruleset.version == 1
        assert ruleset.rules == ()  # no rules, no error
        # And critically: this is NOT the default catalog; an explicit empty list
        # must not silently expand to the 14-rule fallback.
        assert len(ruleset.rules) == 0


# ---------------------------------------------------------------------------
# Bonus: source_path round-trips when a file is present
# ---------------------------------------------------------------------------


def test_loader_records_source_path_when_yaml_present(tmp_path: Path) -> None:
    """When rules.yaml exists, the resulting RuleSet should remember its origin."""
    from cli.core.rules import loader as rules_loader

    org_path = tmp_path
    target = _write_rules_yaml(
        org_path,
        """
version: 1
rules:
  - id: r-one
    severity: SUGGESTED
    actions: ["msgr.send"]
    description: "one"
""",
    )

    ruleset = rules_loader.load_rules(org_path)

    # source_path is documented in t2zb §B as "absolute path to rules.yaml that
    # produced this set". When loading from disk, it should match the target file.
    assert hasattr(ruleset, "source_path")
    assert str(target) == ruleset.source_path or str(target.resolve()) == ruleset.source_path
