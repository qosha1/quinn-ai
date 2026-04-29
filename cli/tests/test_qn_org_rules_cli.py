"""Tests for `qn org rules {list,show,validate,test,disable,add}`.

Spec: quinn-ai-63y1, quinn-ai-zm8a §1.

The subcommand group lives at `cli.core.rules.cli` and is registered into
`qn org` via `cli.commands.org.__init__`. These tests drive it via Click's
CliRunner against tmp_path-backed orgs.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def org_path(tmp_path: Path) -> Path:
    """Org root that has nothing in it. The rules subcommands operate against
    `<org>/config/rules.yaml`, falling back to the bundled default catalog
    when absent."""
    return tmp_path


def _seed_rules(org_path: Path, body: str) -> Path:
    config_dir = org_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    target = config_dir / "rules.yaml"
    target.write_text(body)
    return target


# ---------------------------------------------------------------------------
# qn org rules list
# ---------------------------------------------------------------------------


class TestRulesList:
    def test_list_default_catalog_when_no_rules_yaml(self, runner: CliRunner, org_path: Path) -> None:
        """When org has no rules.yaml, list shows the bundled 14-rule catalog."""
        from cli.commands.main import qn

        result = runner.invoke(qn, ["--org-path", str(org_path), "org", "rules", "list"])
        assert result.exit_code == 0, result.output
        # Header + 14 rules from default catalog (per c5hb §3).
        assert "id" in result.output
        assert "severity" in result.output
        # Rule ids from each severity tier in the default catalog.
        assert "no-drop-database" in result.output  # ABSOLUTE
        assert "tests-before-merge" in result.output  # ENCOURAGED
        assert "no-fire-without-replacement-plan" in result.output  # REQUIRED
        assert "pr-title-prefix" in result.output  # SUGGESTED
        # Severity values render with their string form.
        assert "ABSOLUTE" in result.output
        assert "SUGGESTED" in result.output

    def test_list_empty_rules(self, runner: CliRunner, org_path: Path) -> None:
        """`version: 1` + `rules: []` is valid; list prints '(no rules)'."""
        from cli.commands.main import qn

        _seed_rules(org_path, "version: 1\nrules: []\n")

        result = runner.invoke(qn, ["--org-path", str(org_path), "org", "rules", "list"])
        assert result.exit_code == 0, result.output
        assert "no rules" in result.output.lower()


# ---------------------------------------------------------------------------
# qn org rules show
# ---------------------------------------------------------------------------


class TestRulesShow:
    def test_show_known_rule(self, runner: CliRunner, org_path: Path) -> None:
        from cli.commands.main import qn

        result = runner.invoke(
            qn, ["--org-path", str(org_path), "org", "rules", "show", "no-drop-database"]
        )
        assert result.exit_code == 0, result.output
        assert "no-drop-database" in result.output
        assert "ABSOLUTE" in result.output
        # Pattern block should render for this rule.
        assert "pattern" in result.output

    def test_show_unknown_rule_exits_nonzero(self, runner: CliRunner, org_path: Path) -> None:
        from cli.commands.main import qn

        result = runner.invoke(
            qn, ["--org-path", str(org_path), "org", "rules", "show", "no-such-rule"]
        )
        assert result.exit_code != 0
        assert "not found" in result.output.lower()


# ---------------------------------------------------------------------------
# qn org rules validate
# ---------------------------------------------------------------------------


class TestRulesValidate:
    def test_validate_accepts_valid_yaml(self, runner: CliRunner, org_path: Path) -> None:
        from cli.commands.main import qn

        _seed_rules(
            org_path,
            "version: 1\n"
            "rules:\n"
            "  - id: my-rule\n"
            "    severity: SUGGESTED\n"
            "    actions: ['msgr.send']\n"
            "    description: 'a rule'\n",
        )
        result = runner.invoke(qn, ["--org-path", str(org_path), "org", "rules", "validate"])
        assert result.exit_code == 0, result.output
        assert "OK" in result.output

    def test_validate_rejects_missing_required_fields(
        self, runner: CliRunner, org_path: Path
    ) -> None:
        """Missing `severity` makes the loader fail; CLI exits non-zero."""
        from cli.commands.main import qn

        _seed_rules(
            org_path,
            "version: 1\n"
            "rules:\n"
            "  - id: bad-rule\n"
            "    actions: ['msgr.send']\n"
            "    description: 'no severity'\n",
        )
        result = runner.invoke(qn, ["--org-path", str(org_path), "org", "rules", "validate"])
        assert result.exit_code != 0
        # The error message should mention the rule that failed (or the file).
        assert "bad-rule" in result.output or "severity" in result.output.lower()

    def test_validate_rejects_malformed_yaml(self, runner: CliRunner, org_path: Path) -> None:
        from cli.commands.main import qn

        _seed_rules(
            org_path,
            "version: 1\nrules:\n  - id: broken\n    severity: [unclosed\n",
        )
        result = runner.invoke(qn, ["--org-path", str(org_path), "org", "rules", "validate"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# qn org rules test <action>
# ---------------------------------------------------------------------------


class TestRulesTest:
    def test_test_action_with_no_match_returns_allow(
        self, runner: CliRunner, org_path: Path
    ) -> None:
        """An action that no rule targets prints decision=allow."""
        from cli.commands.main import qn

        result = runner.invoke(
            qn,
            [
                "--org-path",
                str(org_path),
                "org",
                "rules",
                "test",
                "completely.fake.action",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "allow" in result.output.lower()

    def test_test_action_triggers_absolute_rule(
        self, runner: CliRunner, org_path: Path
    ) -> None:
        """Sending a body that matches no-drop-database's pattern blocks."""
        from cli.commands.main import qn

        result = runner.invoke(
            qn,
            [
                "--org-path",
                str(org_path),
                "org",
                "rules",
                "test",
                "qn-bd.create",
                "--body",
                "DROP TABLE users",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "block" in result.output.lower()
        assert "no-drop-database" in result.output

    def test_test_action_triggers_required_without_override(
        self, runner: CliRunner, org_path: Path
    ) -> None:
        """qn-org.fire is REQUIRED in the catalog; with no --override, expect requires_override.

        The default catalog scopes REQUIRED rules to env=prod, so we pass
        `--env prod` to make the rule fire.
        """
        from cli.commands.main import qn

        result = runner.invoke(
            qn,
            [
                "--org-path",
                str(org_path),
                "org",
                "rules",
                "test",
                "qn-org.fire",
                "--env",
                "prod",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "requires_override" in result.output.lower()


# ---------------------------------------------------------------------------
# qn org rules disable <rule-id>
# ---------------------------------------------------------------------------


class TestRulesDisable:
    def test_disable_comments_out_the_rule(
        self, runner: CliRunner, org_path: Path
    ) -> None:
        from cli.commands.main import qn

        rules_path = _seed_rules(
            org_path,
            "version: 1\n"
            "rules:\n"
            "  - id: rule-a\n"
            "    severity: SUGGESTED\n"
            "    actions: ['msgr.send']\n"
            "    description: 'a'\n"
            "  - id: rule-b\n"
            "    severity: SUGGESTED\n"
            "    actions: ['msgr.send']\n"
            "    description: 'b'\n",
        )

        result = runner.invoke(
            qn, ["--org-path", str(org_path), "org", "rules", "disable", "rule-a"]
        )
        assert result.exit_code == 0, result.output

        new_text = rules_path.read_text()
        # rule-a's lines are commented out. rule-b is left alone.
        assert "# " in new_text  # at least one commented line
        assert "# " in [
            line for line in new_text.splitlines() if "rule-a" in line
        ][0]
        # rule-b's `- id: rule-b` line is still uncommented.
        rule_b_lines = [
            line for line in new_text.splitlines() if "rule-b" in line
        ]
        assert any(not line.lstrip().startswith("#") for line in rule_b_lines)

    def test_disable_unknown_rule_exits_nonzero(
        self, runner: CliRunner, org_path: Path
    ) -> None:
        from cli.commands.main import qn

        _seed_rules(
            org_path,
            "version: 1\n"
            "rules:\n"
            "  - id: rule-x\n"
            "    severity: SUGGESTED\n"
            "    actions: ['msgr.send']\n"
            "    description: 'x'\n",
        )
        result = runner.invoke(
            qn,
            ["--org-path", str(org_path), "org", "rules", "disable", "no-such-rule"],
        )
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_disable_with_no_rules_yaml_exits_nonzero(
        self, runner: CliRunner, org_path: Path
    ) -> None:
        """`disable` only edits the org's own file; can't comment out the bundled catalog."""
        from cli.commands.main import qn

        result = runner.invoke(
            qn,
            ["--org-path", str(org_path), "org", "rules", "disable", "no-drop-database"],
        )
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# qn org rules add
# ---------------------------------------------------------------------------


class TestRulesAdd:
    def test_add_appends_new_rule(self, runner: CliRunner, org_path: Path) -> None:
        from cli.commands.main import qn

        # Seed an empty rules.yaml so add appends a real rule.
        _seed_rules(org_path, "version: 1\nrules: []\n")

        # click.prompt reads from stdin; supply each prompt's answer line by
        # line. SUGGESTED severity -> no pattern prompts.
        # Order: id, severity, actions, description.
        stdin_input = "\n".join([
            "my-new-rule",
            "SUGGESTED",
            "msgr.send",
            "a brand new rule",
            "",
        ])

        result = runner.invoke(
            qn,
            ["--org-path", str(org_path), "org", "rules", "add"],
            input=stdin_input,
        )
        assert result.exit_code == 0, result.output

        # The new rule shows up in the file.
        rules_path = org_path / "config" / "rules.yaml"
        new_text = rules_path.read_text()
        assert "my-new-rule" in new_text
        assert "SUGGESTED" in new_text
        assert "msgr.send" in new_text

        # And the loader still validates afterwards.
        result_v = runner.invoke(
            qn, ["--org-path", str(org_path), "org", "rules", "validate"]
        )
        assert result_v.exit_code == 0, result_v.output

    def test_add_creates_rules_yaml_when_missing(
        self, runner: CliRunner, org_path: Path
    ) -> None:
        """If <org>/config/rules.yaml doesn't exist, add creates it."""
        from cli.commands.main import qn

        rules_path = org_path / "config" / "rules.yaml"
        assert not rules_path.exists()

        stdin_input = "\n".join([
            "first-rule",
            "SUGGESTED",
            "msgr.send",
            "first one",
            "",
        ])

        result = runner.invoke(
            qn,
            ["--org-path", str(org_path), "org", "rules", "add"],
            input=stdin_input,
        )
        assert result.exit_code == 0, result.output
        assert rules_path.exists()
        assert "first-rule" in rules_path.read_text()
