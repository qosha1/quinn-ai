"""
Tests for the qn config validate command.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from commands.main import qn
from commands.config import check_env_vars, check_provider_connection


@pytest.fixture
def runner():
    """Create CLI runner."""
    return CliRunner()


@pytest.fixture
def temp_org_dir():
    """Create temporary org directory with config."""
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir)
        config_path = org_path / "config"
        config_path.mkdir()

        # Create providers.yaml
        providers_yaml = config_path / "providers.yaml"
        providers_yaml.write_text("""
default: anthropic
providers:
  anthropic:
    enabled: true
    api_key: ${ANTHROPIC_API_KEY}
    timeout: 60
  openai:
    enabled: false
    api_key: ${OPENAI_API_KEY}
    timeout: 60
""")
        yield org_path


class TestCheckEnvVars:
    """Test environment variable checking."""

    def test_check_with_anthropic_key_set(self, monkeypatch):
        """Should detect ANTHROPIC_API_KEY when set."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        results = check_env_vars()

        assert results["anthropic"][0] is True
        assert results["anthropic"][1] == "ANTHROPIC_API_KEY"
        assert results["openai"][0] is False

    def test_check_with_openai_key_set(self, monkeypatch):
        """Should detect OPENAI_API_KEY when set."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")

        results = check_env_vars()

        assert results["anthropic"][0] is False
        assert results["openai"][0] is True

    def test_check_with_no_keys_set(self, monkeypatch):
        """Should detect when no keys are set."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        results = check_env_vars()

        assert results["anthropic"][0] is False
        assert results["openai"][0] is False


class TestCheckProviderConnection:
    """Test provider connection testing."""

    def test_no_api_key(self):
        """Should fail with no API key."""
        success, message = check_provider_connection("anthropic", "")
        assert success is False
        assert "No API key" in message

    def test_unknown_provider(self):
        """Should fail for unknown provider."""
        success, message = check_provider_connection("unknown", "some-key")
        assert success is False
        assert "Unknown provider" in message


class TestValidateCommand:
    """Test qn config validate command."""

    def test_validate_help(self, runner):
        """Should show help text."""
        result = runner.invoke(qn, ["config", "validate", "--help"])
        assert result.exit_code == 0
        assert "Validate configuration" in result.output
        assert "--test-connection" in result.output
        assert "--org-path" in result.output

    def test_validate_no_keys(self, runner, monkeypatch):
        """Should warn when no keys are set."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        result = runner.invoke(qn, ["config", "validate"])

        assert result.exit_code == 1
        assert "NOT SET" in result.output
        assert "No API keys found" in result.output

    def test_validate_with_anthropic_key(self, runner, monkeypatch):
        """Should pass with Anthropic key set."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-testkeytestkeytestkeytestkey")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        result = runner.invoke(qn, ["config", "validate"])

        assert result.exit_code == 0
        assert "SET" in result.output
        assert "Validation passed" in result.output

    def test_validate_with_org_path(self, runner, monkeypatch, temp_org_dir):
        """Should validate providers.yaml when org-path provided."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-testkeytestkeytestkeytestkey")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        result = runner.invoke(qn, ["config", "validate", "--org-path", str(temp_org_dir)])

        assert result.exit_code == 0
        assert "Configuration valid" in result.output

    def test_validate_with_invalid_org_path(self, runner, monkeypatch):
        """Should fail with invalid org path."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-testkeytestkeytestkeytestkey")

        result = runner.invoke(qn, ["config", "validate", "--org-path", "/nonexistent/path"])

        # Click validates path existence
        assert result.exit_code != 0

    def test_validate_verbose_output(self, runner, monkeypatch, temp_org_dir):
        """Should show verbose output with -v flag."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-testkeytestkeytestkeytestkey")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        result = runner.invoke(qn, ["config", "validate", "--org-path", str(temp_org_dir), "-v"])

        assert result.exit_code == 0
        assert "Providers:" in result.output
        assert "anthropic:" in result.output
        assert "enabled" in result.output

    def test_validate_missing_providers_yaml(self, runner, monkeypatch):
        """Should fail when providers.yaml is missing."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-testkeytestkeytestkeytestkey")

        with tempfile.TemporaryDirectory() as tmpdir:
            org_path = Path(tmpdir)
            config_path = org_path / "config"
            config_path.mkdir()
            # No providers.yaml created

            result = runner.invoke(qn, ["config", "validate", "--org-path", str(org_path)])

            assert result.exit_code == 1
            assert "providers.yaml not found" in result.output

    def test_validate_plaintext_key_warning(self, runner, monkeypatch):
        """Should warn about plaintext API keys in config."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-testkeytestkeytestkeytestkey")

        with tempfile.TemporaryDirectory() as tmpdir:
            org_path = Path(tmpdir)
            config_path = org_path / "config"
            config_path.mkdir()

            # Create providers.yaml with plaintext key
            providers_yaml = config_path / "providers.yaml"
            providers_yaml.write_text("""
default: anthropic
providers:
  anthropic:
    enabled: true
    api_key: sk-ant-api03-plaintextkeythatshouldbeanenvvar
    timeout: 60
""")

            result = runner.invoke(qn, ["config", "validate", "--org-path", str(org_path)])

            assert "Plaintext API keys detected" in result.output


class TestValidateWithTestConnection:
    """Test the --test-connection flag."""

    def test_test_connection_no_keys(self, runner, monkeypatch):
        """Should skip connection tests when no keys set."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        result = runner.invoke(qn, ["config", "validate", "--test-connection"])

        assert "SKIPPED" in result.output

    def test_test_connection_with_key(self, runner, monkeypatch):
        """Should attempt connection test when key is set."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-invalidkey12345678901234567890")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        result = runner.invoke(qn, ["config", "validate", "--test-connection"])

        # Should show testing output (will fail with invalid key)
        assert "API Connectivity Tests" in result.output
        assert "anthropic:" in result.output
