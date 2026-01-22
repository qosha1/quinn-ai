"""
Tests for BdClient.
"""

import pytest
from unittest.mock import patch, MagicMock
import subprocess

from shared.bd import BdClient, BdClientError, BdResult
from shared.bd.client import InMemoryBdClient


class TestBdClient:
    """Test BdClient subprocess handling."""

    def test_run_success(self):
        """run() returns BdResult on success."""
        with patch("shared.bd.client.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="issue created",
                stderr="",
            )
            client = BdClient()
            result = client.run("create", "--title=Test")

            assert isinstance(result, BdResult)
            assert result.stdout == "issue created"
            assert result.success
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert args == ["bd", "create", "--title=Test"]

    def test_run_with_db_path(self):
        """run() includes --db flag when db_path is set."""
        with patch("shared.bd.client.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="output",
                stderr="",
            )
            client = BdClient(db_path="/path/to/.beads")
            client.run("list")

            args = mock_run.call_args[0][0]
            assert "--db" in args
            assert "/path/to/.beads" in args

    def test_run_with_custom_command(self):
        """run() uses custom bd_command path."""
        with patch("shared.bd.client.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="output",
                stderr="",
            )
            client = BdClient(bd_command="/usr/local/bin/bd")
            client.run("list")

            args = mock_run.call_args[0][0]
            assert args[0] == "/usr/local/bin/bd"

    def test_run_failure_raises_error(self):
        """run() raises BdClientError on non-zero exit."""
        with patch("shared.bd.client.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="Error: issue not found",
            )
            client = BdClient()

            with pytest.raises(BdClientError) as exc_info:
                client.run("show", "beads-xxx")

            assert exc_info.value.returncode == 1
            assert "issue not found" in exc_info.value.stderr

    def test_run_silent_returns_none_on_failure(self):
        """run_silent() returns None instead of raising."""
        with patch("shared.bd.client.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="Error",
            )
            client = BdClient()
            result = client.run_silent("show", "beads-xxx")

            assert result is None

    def test_run_silent_returns_result_on_success(self):
        """run_silent() returns BdResult on success."""
        with patch("shared.bd.client.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="success",
                stderr="",
            )
            client = BdClient()
            result = client.run_silent("list")

            assert isinstance(result, BdResult)
            assert result.stdout == "success"

    def test_run_json_parses_output(self):
        """run_json() parses JSON output."""
        with patch("shared.bd.client.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout='[{"id": "beads-1"}]',
                stderr="",
            )
            client = BdClient()
            result = client.run_json("list", "--json")

            assert result == [{"id": "beads-1"}]


class TestInMemoryBdClient:
    """Test InMemoryBdClient for testing."""

    def test_run_records_commands(self):
        """run() records all commands called."""
        client = InMemoryBdClient()
        client.run("list", "--json")
        client.run("show", "beads-abc")

        assert len(client.commands) == 2
        assert client.commands[0] == ("list", "--json")
        assert client.commands[1] == ("show", "beads-abc")

    def test_set_response(self):
        """set_response() configures return value."""
        client = InMemoryBdClient()
        client.set_response("list", '[{"id": "beads-1"}]')

        result = client.run("list", "--json")
        assert isinstance(result, BdResult)
        assert result.stdout == '[{"id": "beads-1"}]'

    def test_set_json_response(self):
        """set_json_response() configures JSON return value."""
        client = InMemoryBdClient()
        client.set_json_response("list", [{"id": "beads-1"}])

        result = client.run_json("list", "--json")
        assert result == [{"id": "beads-1"}]

    def test_set_fail(self):
        """set_fail() makes command raise error."""
        client = InMemoryBdClient()
        client.set_fail("create")

        with pytest.raises(BdClientError):
            client.run("create", "--title=Test")

    def test_run_silent_on_failed_command(self):
        """run_silent() returns None for failed commands."""
        client = InMemoryBdClient()
        client.set_fail("show")

        result = client.run_silent("show", "beads-xxx")
        assert result is None

    def test_clear_resets_state(self):
        """clear() resets all recorded state."""
        client = InMemoryBdClient()
        client.run("list")
        client.set_response("show", "data")
        client.set_fail("create")

        client.clear()

        assert len(client.commands) == 0
        assert len(client.responses) == 0
        assert len(client.fail_commands) == 0


class TestBdResult:
    """Test BdResult dataclass."""

    def test_success_property(self):
        """success is True when returncode is 0."""
        result = BdResult(stdout="ok", stderr="", returncode=0)
        assert result.success

        result = BdResult(stdout="", stderr="error", returncode=1)
        assert not result.success

    def test_json_parses_stdout(self):
        """json() parses stdout as JSON."""
        result = BdResult(stdout='{"key": "value"}', stderr="", returncode=0)
        assert result.json() == {"key": "value"}

    def test_json_returns_none_for_empty(self):
        """json() returns None for empty stdout."""
        result = BdResult(stdout="", stderr="", returncode=0)
        assert result.json() is None

    def test_get_created_id_extracts_beads_id(self):
        """get_created_id() extracts beads-xxx ID."""
        result = BdResult(stdout="✓ Created issue: beads-abc123", stderr="", returncode=0)
        assert result.get_created_id() == "beads-abc123"

    def test_get_created_id_extracts_quinnai_id(self):
        """get_created_id() extracts quinnai-xxx ID."""
        result = BdResult(stdout="Created: quinnai-xyz789", stderr="", returncode=0)
        assert result.get_created_id() == "quinnai-xyz789"
