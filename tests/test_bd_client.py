"""
Tests for BdClient.
"""

import pytest
from unittest.mock import patch, MagicMock
import subprocess

from shared.bd import BdClient, BdClientError
from shared.bd.client import InMemoryBdClient


class TestBdClient:
    """Test BdClient subprocess handling."""

    def test_run_success(self):
        """run() returns stdout on success."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="issue created",
                stderr="",
            )
            client = BdClient()
            result = client.run("create", "--title=Test")

            assert result == "issue created"
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert args == ["bd", "create", "--title=Test"]

    def test_run_with_db_path(self):
        """run() includes --db flag when db_path is set."""
        with patch("subprocess.run") as mock_run:
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
        with patch("subprocess.run") as mock_run:
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
        with patch("subprocess.run") as mock_run:
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
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="Error",
            )
            client = BdClient()
            result = client.run_silent("show", "beads-xxx")

            assert result is None

    def test_run_silent_returns_output_on_success(self):
        """run_silent() returns output on success."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="success",
                stderr="",
            )
            client = BdClient()
            result = client.run_silent("list")

            assert result == "success"


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
        assert result == '[{"id": "beads-1"}]'

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
