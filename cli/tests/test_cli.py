"""
Unit tests for CLI framework.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from cli.commands.main import qn
from cli.commands.context import Context


@pytest.fixture
def runner():
    """Get Click test runner."""
    return CliRunner()


@pytest.fixture
def temp_org():
    """Create temporary org directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestQnCommand:
    """Test main qn command."""

    def test_qn_help(self, runner):
        """qn --help should show usage."""
        result = runner.invoke(qn, ["--help"])
        assert result.exit_code == 0
        assert "QuinnAI organization management CLI" in result.output

    def test_qn_shows_groups(self, runner):
        """qn --help should show command groups."""
        result = runner.invoke(qn, ["--help"])
        assert "org" in result.output
        assert "wrkr" in result.output

    def test_qn_org_path_option(self, runner, temp_org):
        """qn should accept --org-path option."""
        result = runner.invoke(qn, ["--org-path", str(temp_org), "--help"])
        assert result.exit_code == 0


class TestOrgGroup:
    """Test org command group."""

    def test_org_help(self, runner):
        """qn org --help should show subcommands."""
        result = runner.invoke(qn, ["org", "--help"])
        assert result.exit_code == 0
        assert "init" in result.output
        assert "start" in result.output
        assert "stop" in result.output
        assert "status" in result.output

    def test_org_init_help(self, runner):
        """qn org init --help should show options."""
        result = runner.invoke(qn, ["org", "init", "--help"])
        assert result.exit_code == 0
        assert "--ceo-name" in result.output

    def test_org_init_runs(self, runner, temp_org):
        """qn org init should initialize organization."""
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "init"
        ])
        assert result.exit_code == 0
        assert "Initialized organization" in result.output
        assert "Created CEO" in result.output
        # Verify folder structure created (per README spec)
        assert (temp_org / "config").exists()
        assert (temp_org / "org-chart").exists()
        assert (temp_org / "live").exists()
        assert (temp_org / "live" / "workers").exists()
        assert (temp_org / "storage" / "shared").exists()
        assert (temp_org / "storage" / "workers").exists()
        # Verify config files copied
        assert (temp_org / "config" / "providers.yaml").exists()
        assert (temp_org / "config" / "worker-templates.yaml").exists()
        # Verify org-chart created
        assert (temp_org / "org-chart" / "current.yaml").exists()

    def test_org_init_already_initialized(self, runner, temp_org):
        """qn org init should fail if already initialized."""
        # First init
        runner.invoke(qn, ["--org-path", str(temp_org), "org", "init"])
        # Second init should fail
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "init"
        ])
        assert result.exit_code != 0
        assert "already initialized" in result.output

    def test_org_start_runs(self, runner, temp_org):
        """qn org start should start initialized organization."""
        # First init
        runner.invoke(qn, ["--org-path", str(temp_org), "org", "init"])
        # Then start (without spawning CEO since no budget in test)
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "start", "--no-spawn-ceo", "--skip-config-validation"
        ])
        assert result.exit_code == 0
        assert "Organization started" in result.output
 
    def test_org_start_worker_requires_running(self, runner, temp_org):
        """qn org start --worker should require running org."""
        runner.invoke(qn, ["--org-path", str(temp_org), "org", "init"])

        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "start", "--worker", "ceo", "--skip-config-validation"
        ])

        assert result.exit_code != 0
        assert "not running" in result.output.lower()

    def test_org_start_worker_runs(self, runner, temp_org):
        """qn org start --worker should start workday via session spawn."""
        runner.invoke(qn, ["--org-path", str(temp_org), "org", "init"])
        runner.invoke(qn, ["--org-path", str(temp_org), "org", "start", "--no-spawn-ceo", "--skip-config-validation"])

        with patch("cli.commands.org.session_utils.spawn_worker_session") as mock_spawn:
            result = runner.invoke(qn, [
                "--org-path", str(temp_org),
                "org", "start", "--worker", "ceo", "--skip-config-validation"
            ])

        assert result.exit_code == 0
        assert "Starting workday for" in result.output
        mock_spawn.assert_called_once()

    def test_org_start_requires_init(self, runner, temp_org):
        """qn org start should require org to be initialized."""
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "start"
        ])
        assert result.exit_code != 0
        assert "not initialized" in result.output.lower() or "Run 'qn org init'" in result.output

    def test_org_start_validates_config(self, runner, temp_org, monkeypatch):
        """qn org start should validate provider configuration.

        Default config (claude_code only, system-auth) validates cleanly,
        so to verify validation actually runs we have to construct a
        scenario that fails: enable anthropic in providers.yaml and
        ensure ANTHROPIC_API_KEY is unset.
        """
        import yaml
        runner.invoke(qn, ["--org-path", str(temp_org), "org", "init"])

        # Flip anthropic to enabled in the org's providers.yaml — without
        # an api_key set, validation must fail.
        providers_path = temp_org / "config" / "providers.yaml"
        cfg = yaml.safe_load(providers_path.read_text())
        cfg["providers"]["anthropic"]["enabled"] = True
        cfg["providers"]["anthropic"]["api_key"] = "${ANTHROPIC_API_KEY}"
        providers_path.write_text(yaml.safe_dump(cfg))
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "start", "--no-spawn-ceo"
        ])
        assert result.exit_code != 0, f"Expected validation failure, got:\n{result.output}"
        out = result.output.lower()
        assert "api_key" in out or "configuration" in out or "anthropic" in out, (
            f"Expected validation error mentioning api_key/configuration/anthropic. Got:\n{result.output}"
        )

    def test_org_start_skip_validation_flag(self, runner, temp_org):
        """qn org start --skip-config-validation should skip validation."""
        runner.invoke(qn, ["--org-path", str(temp_org), "org", "init"])
        # With skip flag should succeed
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "start", "--no-spawn-ceo", "--skip-config-validation"
        ])
        assert result.exit_code == 0

    def test_org_stop_runs(self, runner, temp_org):
        """qn org stop should stop running organization."""
        # Init and start first (without spawning CEO since no budget in test)
        runner.invoke(qn, ["--org-path", str(temp_org), "org", "init"])
        runner.invoke(qn, ["--org-path", str(temp_org), "org", "start", "--no-spawn-ceo", "--skip-config-validation"])
        # Then stop
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "stop"
        ])
        assert result.exit_code == 0
        assert "Organization stopped" in result.output

    def test_org_stop_worker_sends_wrapup(self, runner, temp_org):
        """qn org stop --worker should request wrap-up and close session."""
        from cli.core.db import open_database, get_org_db_path
        from cli.core.queries import get_channel_by_name, get_channel_messages

        runner.invoke(qn, ["--org-path", str(temp_org), "org", "init"])
        runner.invoke(qn, ["--org-path", str(temp_org), "org", "start", "--no-spawn-ceo", "--skip-config-validation"])

        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "stop", "--worker", "ceo",
            "--graceful-timeout", "1",  # avoid the default 60s real-sleep
        ])

        assert result.exit_code == 0
        assert "Workday stopped for" in result.output

        db = open_database(get_org_db_path(temp_org))
        try:
            general = get_channel_by_name(db, "general")
            assert general is not None
            messages = get_channel_messages(db, general.id, limit=1)
            assert messages
            assert "Workday ending" in messages[0].content
        finally:
            db.close()

    def test_org_stop_requires_init(self, runner, temp_org):
        """qn org stop should require org to be initialized."""
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "stop"
        ])
        assert result.exit_code != 0
        assert "not initialized" in result.output.lower() or "Run 'qn org init'" in result.output

    def test_org_status_runs(self, runner, temp_org):
        """qn org status should show organization status."""
        # First init
        runner.invoke(qn, ["--org-path", str(temp_org), "org", "init"])
        # Then check status
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "status"
        ])
        assert result.exit_code == 0
        assert "Status:" in result.output
        assert "Workers:" in result.output

    def test_org_status_requires_init(self, runner, temp_org):
        """qn org status should require org to be initialized."""
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "status"
        ])
        assert result.exit_code != 0
        assert "not initialized" in result.output.lower() or "Run 'qn org init'" in result.output


class TestWrkrGroup:
    """Test wrkr command group."""

    def test_wrkr_help(self, runner):
        """qn wrkr --help should show its subcommands.

        Note: 'inbox' and 'send' are msgr commands, not qn wrkr. Worker
        messaging goes through the standalone msgr CLI.
        """
        result = runner.invoke(qn, ["wrkr", "--help"])
        assert result.exit_code == 0
        for cmd in ("get-work", "status", "search", "delegate", "report",
                    "cleanup", "restart"):
            assert cmd in result.output, f"qn wrkr --help missing {cmd!r}: {result.output}"

    def test_wrkr_get_work_requires_worker_id(self, runner, temp_org):
        """qn wrkr get-work should require QUINN_WORKER_ID."""
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "wrkr", "get-work"
        ])
        assert result.exit_code != 0
        assert "QUINN_WORKER_ID" in result.output

    def test_wrkr_get_work_requires_init(self, runner, temp_org):
        """qn wrkr get-work should require org to be initialized."""
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "wrkr", "get-work"
        ], env={"QUINN_WORKER_ID": "test-worker"})
        assert result.exit_code != 0
        assert "not initialized" in result.output.lower() or "Run 'qn org init'" in result.output

    def test_wrkr_get_work_with_valid_worker(self, runner, temp_org):
        """qn wrkr get-work should run with valid worker."""
        # Initialize and start org (CEO becomes active)
        runner.invoke(qn, ["--org-path", str(temp_org), "org", "init"])
        runner.invoke(qn, ["--org-path", str(temp_org), "org", "start"])
        # Get CEO worker ID from database
        from cli.core.db import open_database, get_org_db_path
        from cli.core.org import Org
        db = open_database(get_org_db_path(temp_org))
        org = Org.load(db)
        ceo_id = org.ceo_worker_id
        db.close()
        # Now test get-work with CEO
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "wrkr", "get-work"
        ], env={"QUINN_WORKER_ID": ceo_id})
        assert result.exit_code == 0
        # CEO cannot work because no session is running
        assert "cannot accept work" in result.output.lower() or "no work" in result.output.lower()

    def test_wrkr_status_requires_worker_id(self, runner, temp_org):
        """qn wrkr status should require QUINN_WORKER_ID."""
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "wrkr", "status"
        ])
        assert result.exit_code != 0
        assert "QUINN_WORKER_ID" in result.output

    def test_wrkr_status_requires_init(self, runner, temp_org):
        """qn wrkr status should require org to be initialized."""
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "wrkr", "status"
        ], env={"QUINN_WORKER_ID": "test-worker"})
        assert result.exit_code != 0
        assert "not initialized" in result.output.lower() or "Run 'qn org init'" in result.output

    def test_wrkr_status_with_valid_worker(self, runner, temp_org):
        """qn wrkr status should show worker details."""
        # Initialize org
        runner.invoke(qn, ["--org-path", str(temp_org), "org", "init"])
        # Get CEO worker ID
        from cli.core.db import open_database, get_org_db_path
        from cli.core.org import Org
        db = open_database(get_org_db_path(temp_org))
        org = Org.load(db)
        ceo_id = org.ceo_worker_id
        db.close()
        # Test status
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "wrkr", "status"
        ], env={"QUINN_WORKER_ID": ceo_id})
        assert result.exit_code == 0
        assert "Worker:" in result.output
        assert "Lifecycle:" in result.output


class TestContext:
    """Test CLI context object."""

    def test_context_init(self, temp_org):
        """Context should initialize with org path."""
        ctx = Context(temp_org)
        assert ctx.org_path == temp_org
        assert ctx._db is None

    def test_context_db_requires_org_path(self):
        """Context.db should require org path."""
        ctx = Context()
        with pytest.raises(Exception):
            _ = ctx.db

    def test_context_close_idempotent(self, temp_org):
        """Context.close should be safe to call multiple times."""
        ctx = Context(temp_org)
        ctx.close()
        ctx.close()  # Should not raise


class TestObserveCommand:
    """Test qn org observe command."""

    def test_observe_help(self, runner):
        """qn org observe --help should show usage."""
        result = runner.invoke(qn, ["org", "observe", "--help"])
        assert result.exit_code == 0
        assert "tmux session" in result.output.lower()
        assert "--stream" in result.output

    def test_observe_requires_init(self, runner, temp_org):
        """qn org observe should require org to be initialized."""
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "observe", "some-worker"
        ])
        assert result.exit_code != 0
        assert "not initialized" in result.output.lower() or "Run 'qn org init'" in result.output

    def test_observe_requires_valid_worker(self, runner, temp_org):
        """qn org observe should require valid worker."""
        # Initialize org
        runner.invoke(qn, ["--org-path", str(temp_org), "org", "init"])
        # Try to observe non-existent worker
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "observe", "nonexistent-worker"
        ])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_observe_requires_active_session(self, runner, temp_org):
        """qn org observe should require worker to have active session."""
        # Initialize org
        runner.invoke(qn, ["--org-path", str(temp_org), "org", "init"])
        # Get CEO worker ID
        from cli.core.db import open_database, get_org_db_path
        from cli.core.org import Org
        db = open_database(get_org_db_path(temp_org))
        org = Org.load(db)
        ceo_id = org.ceo_worker_id
        db.close()
        # Try to observe CEO (no session running)
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "observe", ceo_id
        ])
        assert result.exit_code != 0
        assert "does not have an active session" in result.output.lower() or "starting" in result.output.lower() or "running" in result.output.lower() or "idle" in result.output.lower()

    def test_observe_accepts_worker_name(self, runner, temp_org):
        """qn org observe should accept worker name."""
        # Initialize org
        runner.invoke(qn, ["--org-path", str(temp_org), "org", "init", "--ceo-name", "TestCEO"])
        # Try to observe by name (will fail because no session, but name lookup should work)
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "observe", "TestCEO"
        ])
        # Should fail because no active session, not because worker not found
        assert result.exit_code != 0
        assert "not found" not in result.output.lower() or "session" in result.output.lower()


class TestEnvVar:
    """Test environment variable handling."""

    def test_org_path_from_env(self, runner, temp_org):
        """Should read QUINN_ORG_PATH from environment."""
        result = runner.invoke(qn, ["org", "--help"], env={
            "QUINN_ORG_PATH": str(temp_org)
        })
        assert result.exit_code == 0
