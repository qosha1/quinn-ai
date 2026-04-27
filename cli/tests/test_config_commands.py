"""
Tests for qn config command group - CLI-level tests for config validate and
config set-provider commands.

The lower-level config loading tests live in test_config.py and
test_config_validate.py. These tests cover the CLI command behavior.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml
from click.testing import CliRunner

from cli.commands.main import qn
from cli.commands.config import check_env_vars


@pytest.fixture
def runner():
    """Get Click test runner."""
    return CliRunner()


@pytest.fixture
def temp_org_with_providers():
    """Create temp org with a providers.yaml having multiple providers."""
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir)
        config_path = org_path / "config"
        config_path.mkdir()

        providers_yaml = config_path / "providers.yaml"
        providers_yaml.write_text(
            "default: anthropic\n"
            "providers:\n"
            "  anthropic:\n"
            "    enabled: true\n"
            "    api_key: ${ANTHROPIC_API_KEY}\n"
            "    timeout: 60\n"
            "  claude_code:\n"
            "    enabled: true\n"
            "    api_key: ${ANTHROPIC_API_KEY}\n"
            "    timeout: 60\n"
            "  openai:\n"
            "    enabled: false\n"
            "    api_key: ${OPENAI_API_KEY}\n"
            "    timeout: 60\n"
        )
        yield org_path


@pytest.fixture
def temp_org_dir():
    """Create temp org with minimal providers.yaml."""
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir)
        config_path = org_path / "config"
        config_path.mkdir()

        providers_yaml = config_path / "providers.yaml"
        providers_yaml.write_text(
            "default: anthropic\n"
            "providers:\n"
            "  anthropic:\n"
            "    enabled: true\n"
            "    api_key: ${ANTHROPIC_API_KEY}\n"
            "    timeout: 60\n"
        )
        yield org_path


class TestConfigGroup:
    """Test qn config group registration and help."""

    def test_config_group_shows_help(self, runner):
        """qn config --help should show subcommands."""
        result = runner.invoke(qn, ["config", "--help"])
        assert result.exit_code == 0

    def test_config_group_shows_validate_and_set_provider(self, runner):
        """qn config --help should list validate and set-provider subcommands."""
        result = runner.invoke(qn, ["config", "--help"])
        assert result.exit_code == 0
        assert "validate" in result.output
        assert "set-provider" in result.output

    def test_config_registered_in_main(self, runner):
        """qn --help should show config command group."""
        result = runner.invoke(qn, ["--help"])
        assert result.exit_code == 0
        assert "config" in result.output


class TestCheckEnvVarsFunction:
    """Test check_env_vars returns correct structure."""

    def test_returns_dict_with_both_providers(self, monkeypatch):
        """check_env_vars should return dict with anthropic and openai keys."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        results = check_env_vars()

        assert isinstance(results, dict)
        assert "anthropic" in results
        assert "openai" in results

    def test_each_entry_is_bool_and_string_tuple(self, monkeypatch):
        """Each check_env_vars entry should be (bool, str) tuple."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        results = check_env_vars()

        for provider, value in results.items():
            assert isinstance(value, tuple)
            assert len(value) == 2
            assert isinstance(value[0], bool)
            assert isinstance(value[1], str)

    def test_anthropic_true_when_set(self, monkeypatch):
        """anthropic entry should be True when ANTHROPIC_API_KEY is set."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        results = check_env_vars()
        assert results["anthropic"][0] is True

    def test_openai_false_when_not_set(self, monkeypatch):
        """openai entry should be False when OPENAI_API_KEY not set."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        results = check_env_vars()
        assert results["openai"][0] is False

    def test_env_var_names_correct(self, monkeypatch):
        """check_env_vars should return the actual env var names."""
        results = check_env_vars()
        assert results["anthropic"][1] == "ANTHROPIC_API_KEY"
        assert results["openai"][1] == "OPENAI_API_KEY"


class TestConfigValidateCommand:
    """Test qn config validate CLI behavior."""

    def test_validate_missing_all_keys_exits_1(self, runner, monkeypatch):
        """validate with no API keys should show warning and exit 1."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        result = runner.invoke(qn, ["config", "validate"])

        assert result.exit_code == 1
        assert "No API keys found" in result.output

    def test_validate_all_keys_set_shows_masked_values(self, runner, monkeypatch):
        """validate with both keys set should show masked values."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-testkey123456789012345678")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-key123456789012345678901234")

        result = runner.invoke(qn, ["config", "validate"])

        assert result.exit_code == 0
        assert "SET" in result.output
        # Keys should be masked - should show stars
        assert "***" in result.output or "*" in result.output

    def test_validate_partial_key_set_passes(self, runner, monkeypatch):
        """validate with at least one key set should pass."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-testkey123456789012345678")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        result = runner.invoke(qn, ["config", "validate"])

        assert result.exit_code == 0
        assert "Validation passed" in result.output

    def test_validate_with_valid_providers_yaml(self, runner, monkeypatch, temp_org_dir):
        """validate with valid providers.yaml should show 'Configuration valid'."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-testkey123456789012345678")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        result = runner.invoke(qn, ["config", "validate", "--org-path", str(temp_org_dir)])

        assert result.exit_code == 0
        assert "Configuration valid" in result.output

    def test_validate_with_missing_providers_yaml(self, runner, monkeypatch):
        """validate --org-path with no providers.yaml should show error and exit 1."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-testkey123456789012345678")

        with tempfile.TemporaryDirectory() as tmpdir:
            org_path = Path(tmpdir)
            config_path = org_path / "config"
            config_path.mkdir()
            # No providers.yaml

            result = runner.invoke(qn, ["config", "validate", "--org-path", str(org_path)])

        assert result.exit_code == 1
        assert "providers.yaml" in result.output.lower()

    def test_validate_verbose_shows_provider_details(self, runner, monkeypatch, temp_org_dir):
        """validate --verbose should show provider details."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-testkey123456789012345678")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        result = runner.invoke(qn, ["config", "validate", "--org-path", str(temp_org_dir), "-v"])

        assert result.exit_code == 0
        assert "Providers:" in result.output
        assert "anthropic:" in result.output
        assert "enabled" in result.output

    def test_validate_with_plaintext_api_keys_shows_warning(self, runner, monkeypatch):
        """validate should warn about plaintext API keys in providers.yaml."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-testkey123456789012345678")

        with tempfile.TemporaryDirectory() as tmpdir:
            org_path = Path(tmpdir)
            config_path = org_path / "config"
            config_path.mkdir()

            providers_yaml = config_path / "providers.yaml"
            providers_yaml.write_text(
                "default: anthropic\n"
                "providers:\n"
                "  anthropic:\n"
                "    enabled: true\n"
                "    api_key: sk-ant-api03-plaintextkey12345678901234\n"
                "    timeout: 60\n"
            )

            result = runner.invoke(qn, ["config", "validate", "--org-path", str(org_path)])

        assert "Plaintext API keys detected" in result.output


class TestConfigValidateTestConnection:
    """Test qn config validate --test-connection behavior."""

    def test_test_connection_skips_missing_key(self, runner, monkeypatch):
        """validate --test-connection should skip providers with no key."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        result = runner.invoke(qn, ["config", "validate", "--test-connection"])

        assert "SKIPPED" in result.output

    def test_test_connection_shows_api_connectivity_section(self, runner, monkeypatch):
        """validate --test-connection should show 'API Connectivity Tests' section."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-invalidkey12345678901234567890")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        result = runner.invoke(qn, ["config", "validate", "--test-connection"])

        assert "API Connectivity Tests" in result.output
        assert "anthropic:" in result.output

    def test_test_connection_bad_key_shows_failed(self, runner, monkeypatch):
        """validate --test-connection with bad key should show FAILED."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-invalidbadkeyfortesting12345")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        # Mock the connection check to return failure
        with patch("cli.commands.config.check_provider_connection", return_value=(False, "Authentication failed")):
            result = runner.invoke(qn, ["config", "validate", "--test-connection"])

        assert "FAILED" in result.output or "failed" in result.output.lower()

    def test_test_connection_success_shows_ok(self, runner, monkeypatch):
        """validate --test-connection success should show OK."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-validkeyfortesting1234567890")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        # Mock the connection check to return success
        with patch("cli.commands.config.check_provider_connection", return_value=(True, "Connected successfully (model: claude-3-opus)")):
            result = runner.invoke(qn, ["config", "validate", "--test-connection"])

        assert "OK" in result.output


class TestConfigSetProvider:
    """Test qn config set-provider command."""

    def test_set_provider_requires_org_path(self, runner):
        """config set-provider should require --org-path."""
        result = runner.invoke(qn, ["config", "set-provider", "anthropic"])
        assert result.exit_code != 0
        assert "org-path" in result.output.lower() or "--org-path" in result.output or "Missing option" in result.output

    def test_set_provider_invalid_choice_rejected(self, runner):
        """config set-provider with invalid provider should be rejected by Click."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.invoke(qn, [
                "config", "set-provider", "invalid-provider",
                "--org-path", tmpdir
            ])
        assert result.exit_code != 0

    def test_set_provider_missing_providers_yaml_exits_1(self, runner):
        """config set-provider with missing providers.yaml should exit 1."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org_path = Path(tmpdir)
            config_path = org_path / "config"
            config_path.mkdir()
            # No providers.yaml created

            result = runner.invoke(qn, [
                "config", "set-provider", "anthropic",
                "--org-path", str(org_path)
            ])
        assert result.exit_code == 1
        assert "providers.yaml" in result.output.lower()

    def test_set_provider_not_in_yaml_exits_1(self, runner, temp_org_dir):
        """config set-provider with provider not in yaml should exit 1."""
        # temp_org_dir only has 'anthropic' provider
        result = runner.invoke(qn, [
            "config", "set-provider", "openai",
            "--org-path", str(temp_org_dir)
        ])
        assert result.exit_code == 1
        assert "not found" in result.output.lower() or "openai" in result.output.lower()

    def test_set_provider_updates_default(self, runner, temp_org_with_providers):
        """config set-provider should update the default in providers.yaml."""
        # Current default is 'anthropic', change to 'claude_code'
        result = runner.invoke(qn, [
            "config", "set-provider", "claude_code",
            "--org-path", str(temp_org_with_providers)
        ])
        assert result.exit_code == 0

        # Verify the providers.yaml was updated
        providers_path = temp_org_with_providers / "config" / "providers.yaml"
        with open(providers_path) as f:
            updated = yaml.safe_load(f)
        assert updated["default"] == "claude_code"

    def test_set_provider_shows_old_and_new(self, runner, temp_org_with_providers):
        """config set-provider should show old->new transition in output."""
        result = runner.invoke(qn, [
            "config", "set-provider", "claude_code",
            "--org-path", str(temp_org_with_providers)
        ])
        assert result.exit_code == 0
        # Should show the transition
        assert "anthropic" in result.output
        assert "claude_code" in result.output

    def test_set_provider_help_shows_choices(self, runner):
        """config set-provider --help should show valid provider choices."""
        result = runner.invoke(qn, ["config", "set-provider", "--help"])
        assert result.exit_code == 0
        assert "claude_code" in result.output or "anthropic" in result.output
