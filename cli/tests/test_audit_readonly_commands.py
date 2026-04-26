"""Audit tests for read-only commands. One bead per logical command.

Beads covered in this file:
- quinn-ai-dg8: qn org provider list
- quinn-ai-jwi: qn org budget status
- quinn-ai-9vw: qn org okr list
- quinn-ai-czh: qn org delegations
- quinn-ai-1pq: qn config validate

Each test class corresponds to one bead so closes can cite the specific class.
"""

import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from cli.commands.main import qn


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def initialized_org():
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir)
        runner = CliRunner()
        result = runner.invoke(qn, [
            "--org-path", str(org_path), "org", "init",
            "--ceo-name", "AuditCEO", "--skip-okrs",
        ])
        assert result.exit_code == 0, result.output
        yield org_path


# ============================================================
# quinn-ai-dg8: qn org provider list
# ============================================================
class TestProviderList:
    def test_lists_all_default_providers(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "provider", "list",
        ])
        assert result.exit_code == 0, result.output
        assert "Available CLI Providers" in result.output
        # Default registry has these four
        for name in ("claude_code", "codex", "gemini", "openai"):
            assert name in result.output, f"Provider '{name}' missing from output:\n{result.output}"

    def test_shows_capabilities_per_provider(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "provider", "list",
        ])
        assert result.exit_code == 0
        # claude_code's capabilities should include shell + file_edit
        assert "shell" in result.output
        assert "file_edit" in result.output

    def test_shows_total_count(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "provider", "list",
        ])
        assert result.exit_code == 0
        assert "Total:" in result.output
        assert "provider(s)" in result.output


# ============================================================
# quinn-ai-jwi: qn org budget status
# ============================================================
class TestBudgetStatus:
    def test_shows_org_budget_pool(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "budget", "status",
        ])
        assert result.exit_code == 0, result.output
        assert "Budget Pools" in result.output
        # Default org-main pool: 1000 credits, 30-day period
        assert "org-main" in result.output
        assert "1000.00" in result.output

    def test_shows_pool_period(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "budget", "status",
        ])
        assert result.exit_code == 0
        assert "Period:" in result.output


# ============================================================
# quinn-ai-9vw: qn org okr list
# ============================================================
class TestOkrList:
    def test_empty_when_no_okrs_in_beads(self, runner, initialized_org):
        # --skip-okrs creates the SQLite bootstrap OKR but no bead.
        # `qn org okr list` (without --from-db) reads beads, so should be empty.
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "list",
        ])
        assert result.exit_code == 0, result.output
        assert "No OKRs found" in result.output

    def test_from_db_shows_bootstrap_okr(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "list", "--from-db",
        ])
        assert result.exit_code == 0, result.output
        # The bootstrap OKR is auto-created during init
        assert "OKR:" in result.output
        # Bootstrap OKR has KRs (team_size, processes_documented per _create_bootstrap_okr)
        assert "Key Results:" in result.output

    def test_lists_okr_after_set(self, runner, initialized_org):
        # Create an OKR via qn org okr set
        runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "set",
            "--title", "Audit OKR target",
            "-d", "audit description",
            "--owner", "ceo",
            "-p", "1",
        ])
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "list",
        ])
        assert result.exit_code == 0, result.output
        assert "Audit OKR target" in result.output


# ============================================================
# quinn-ai-czh: qn org delegations
# ============================================================
class TestDelegations:
    def test_default_view_empty_on_fresh_org(self, runner, initialized_org):
        """Default view shows ISSUED delegations (grants A→B). On a fresh org
        with only a CEO, none exist yet — output should say so cleanly."""
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "delegations",
        ])
        assert result.exit_code == 0, result.output
        assert "DELEGATIONS" in result.output
        assert "0 active" in result.output
        assert "No active delegations found" in result.output

    def test_tree_view_shows_ceo_intrinsic_authority(self, runner, initialized_org):
        """--tree includes the CEO's own hiring scope at the root."""
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "delegations", "--tree",
        ])
        assert result.exit_code == 0, result.output
        assert "AuditCEO" in result.output
        assert "all roles" in result.output

    def test_tree_flag_renders_tree_format(self, runner, initialized_org):
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "delegations", "--tree",
        ])
        assert result.exit_code == 0
        assert "DELEGATION TREE" in result.output

    def test_json_output_returns_valid_json(self, runner, initialized_org):
        import json
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "delegations", "--json-output",
        ])
        assert result.exit_code == 0, result.output
        # Output should be parseable JSON
        try:
            data = json.loads(result.output)
        except json.JSONDecodeError as e:
            pytest.fail(f"--json-output produced invalid JSON: {e}\n{result.output}")
        assert isinstance(data, (list, dict))


# ============================================================
# quinn-ai-1pq: qn config validate
# ============================================================
class TestConfigValidate:
    def test_validates_env_only_without_org_path(self, runner, monkeypatch):
        # No --org-path → should still validate env vars (just not providers.yaml)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test-fake")
        result = runner.invoke(qn, ["config", "validate"])
        assert result.exit_code == 0, result.output
        assert "Environment Variables" in result.output
        assert "ANTHROPIC_API_KEY" in result.output
        assert "Validation passed" in result.output

    def test_validates_providers_yaml_with_org_path(self, runner, initialized_org, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake")
        result = runner.invoke(qn, [
            "config", "validate", "--org-path", str(initialized_org),
        ])
        assert result.exit_code == 0, result.output
        assert "Providers Configuration" in result.output
        assert "Configuration valid" in result.output

    def test_reports_missing_keys(self, runner, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        result = runner.invoke(qn, ["config", "validate"])
        # Validation may still pass overall (claude_code uses system auth)
        # but the env-vars block should mark them as not set
        assert "ANTHROPIC_API_KEY" in result.output
        assert "NOT SET" in result.output or "not set" in result.output.lower()
