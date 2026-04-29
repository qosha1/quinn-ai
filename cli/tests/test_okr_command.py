"""
Unit tests for qn org okr CLI commands.

Tests the OKR command group including:
- okr list with various filters
- okr set/add for creating OKRs
- okr cascade for hierarchy view
- okr show for detailed view
- okr progress and update-kr for key results
- okr link for work item linking
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from cli.commands.main import qn
from cli.core.constants import BEAD_TYPE_EPIC


@pytest.fixture
def runner():
    """Get Click test runner."""
    return CliRunner()


@pytest.fixture
def temp_org():
    """Create temporary org directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def initialized_org(runner, temp_org):
    """Create an initialized org and return its path."""
    result = runner.invoke(qn, ["--org-path", str(temp_org), "org", "init", "--ceo-name", "TestCEO"])
    if result.exit_code != 0:
        pytest.fail(f"org init failed: {result.output}")
    return temp_org


class TestOkrCommandHelp:
    """Test OKR command help and arguments."""

    def test_okr_help(self, runner):
        """qn org okr --help should show subcommands."""
        result = runner.invoke(qn, ["org", "okr", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "set" in result.output
        assert "add" in result.output
        assert "cascade" in result.output
        assert "show" in result.output

    def test_okr_list_help(self, runner):
        """qn org okr list --help should show options."""
        result = runner.invoke(qn, ["org", "okr", "list", "--help"])
        assert result.exit_code == 0
        assert "--status" in result.output
        assert "--assignee" in result.output
        assert "--all" in result.output

    def test_okr_set_help(self, runner):
        """qn org okr set --help should show options."""
        result = runner.invoke(qn, ["org", "okr", "set", "--help"])
        assert result.exit_code == 0
        assert "--title" in result.output
        assert "--description" in result.output
        assert "--owner" in result.output
        assert "--priority" in result.output
        assert "--label" in result.output
        assert "--due" in result.output
        assert "--parent" in result.output


class TestOkrListCommand:
    """Test qn org okr list command."""

    def test_list_requires_init(self, runner, temp_org):
        """Should require org to be initialized."""
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "okr", "list"
        ])
        assert result.exit_code != 0
        assert "not initialized" in result.output.lower() or "Run 'qn org init'" in result.output

    @patch('cli.commands.org.okr._helpers.run_bd')
    def test_list_shows_no_okrs(self, mock_run_bd, runner, initialized_org):
        """Should show message when no OKRs found."""
        mock_run_bd.return_value = MagicMock(
            returncode=0,
            stdout="[]",
            stderr=""
        )

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "list"
        ])

        assert result.exit_code == 0
        assert "No OKRs found" in result.output

    @patch('cli.commands.org.okr._helpers.run_bd')
    def test_list_shows_okrs(self, mock_run_bd, runner, initialized_org):
        """Should display OKRs when found."""
        mock_run_bd.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps([
                {
                    "id": "okr-abc123",
                    "title": "Increase Revenue",
                    "status": "open",
                    "priority": 1,
                    "assignee": "ceo",
                    "description": "Grow revenue by 50%",
                    "labels": ["okr", "q1"],
                    "created_at": "2026-01-01T00:00:00"
                }
            ]),
            stderr=""
        )

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "list"
        ])

        assert result.exit_code == 0
        assert "Increase Revenue" in result.output
        assert "okr-abc123" in result.output
        assert "open" in result.output

    @patch('cli.commands.org.okr._helpers.run_bd')
    def test_list_with_status_filter(self, mock_run_bd, runner, initialized_org):
        """Should pass status filter to bd."""
        mock_run_bd.return_value = MagicMock(
            returncode=0,
            stdout="[]",
            stderr=""
        )

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "list", "--status=in_progress"
        ])

        assert result.exit_code == 0
        # Verify bd was called with status filter
        call_args = mock_run_bd.call_args[0][0]
        assert "--status=in_progress" in call_args

    @patch('cli.commands.org.okr._helpers.run_bd')
    def test_list_with_assignee_filter(self, mock_run_bd, runner, initialized_org):
        """Should pass assignee filter to bd."""
        mock_run_bd.return_value = MagicMock(
            returncode=0,
            stdout="[]",
            stderr=""
        )

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "list", "--assignee=ceo"
        ])

        assert result.exit_code == 0
        call_args = mock_run_bd.call_args[0][0]
        assert "--assignee=ceo" in call_args

    @patch('cli.commands.org.okr._helpers.run_bd')
    def test_list_with_all_flag(self, mock_run_bd, runner, initialized_org):
        """Should pass --all flag to include closed OKRs."""
        mock_run_bd.return_value = MagicMock(
            returncode=0,
            stdout="[]",
            stderr=""
        )

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "list", "--all"
        ])

        assert result.exit_code == 0
        call_args = mock_run_bd.call_args[0][0]
        assert "--all" in call_args


class TestOkrSetCommand:
    """Test qn org okr set command."""

    def test_set_requires_init(self, runner, temp_org):
        """Should require org to be initialized."""
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "okr", "set", "--title=Test OKR"
        ])
        assert result.exit_code != 0
        assert "not initialized" in result.output.lower() or "Run 'qn org init'" in result.output

    def test_set_requires_title(self, runner, initialized_org):
        """Should require --title option."""
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "set"
        ])
        assert result.exit_code != 0
        assert "title" in result.output.lower() or "--title" in result.output

    @patch('cli.commands.org.okr._helpers.run_bd')
    def test_set_creates_okr(self, mock_run_bd, runner, initialized_org):
        """Should create OKR via bd."""
        mock_run_bd.return_value = MagicMock(
            returncode=0,
            stdout="Created issue: okr-abc123",
            stderr=""
        )

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "set", "--title=Test OKR"
        ])

        assert result.exit_code == 0
        assert "Created" in result.output

        # Verify bd was called with correct args
        call_args = mock_run_bd.call_args[0][0]
        assert "create" in call_args
        assert "Test OKR" in call_args
        assert f"--type={BEAD_TYPE_EPIC}" in call_args
        assert "--label=okr" in call_args

    @patch('cli.commands.org.okr._helpers.run_bd')
    def test_set_with_all_options(self, mock_run_bd, runner, initialized_org):
        """Should pass all options to bd."""
        mock_run_bd.return_value = MagicMock(
            returncode=0,
            stdout="Created issue: okr-abc123",
            stderr=""
        )

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "set",
            "--title=Revenue Growth",
            "--description=Grow by 50%",
            "--owner=director",
            "--priority=0",
            "--label=q1",
            "--label=critical",
            "--due=+3m",
            "--parent=okr-parent"
        ])

        assert result.exit_code == 0

        call_args = mock_run_bd.call_args[0][0]
        assert "--description" in call_args or "Grow by 50%" in str(call_args)
        assert "--assignee" in call_args or "director" in str(call_args)
        assert "--priority=0" in call_args
        assert "--due" in call_args
        assert "--parent" in call_args


class TestOkrAddCommand:
    """Test qn org okr add command (alias for set)."""

    @patch('cli.commands.org.okr._helpers.run_bd')
    def test_add_creates_okr(self, mock_run_bd, runner, initialized_org):
        """Should create OKR via bd (same as set)."""
        mock_run_bd.return_value = MagicMock(
            returncode=0,
            stdout="Created issue: okr-xyz",
            stderr=""
        )

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "add", "--title=New OKR"
        ])

        assert result.exit_code == 0
        assert "Created" in result.output


class TestOkrCascadeCommand:
    """Test qn org okr cascade command."""

    def test_cascade_requires_init(self, runner, temp_org):
        """Should require org to be initialized."""
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "okr", "cascade"
        ])
        assert result.exit_code != 0
        assert "not initialized" in result.output.lower() or "Run 'qn org init'" in result.output

    @patch('cli.commands.org.okr._helpers.run_bd')
    def test_cascade_shows_no_okrs(self, mock_run_bd, runner, initialized_org):
        """Should show message when no OKRs found."""
        mock_run_bd.return_value = MagicMock(
            returncode=0,
            stdout="[]",
            stderr=""
        )

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "cascade"
        ])

        assert result.exit_code == 0
        assert "No OKRs found" in result.output

    @patch('cli.commands.org.okr._helpers.run_bd')
    def test_cascade_shows_hierarchy(self, mock_run_bd, runner, initialized_org):
        """Should display OKR hierarchy."""
        mock_run_bd.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps([
                {"id": "okr-parent", "title": "Company Goal", "status": "open", "parent_id": None},
                {"id": "okr-child", "title": "Team Goal", "status": "open", "parent_id": "okr-parent"},
            ]),
            stderr=""
        )

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "cascade"
        ])

        assert result.exit_code == 0
        assert "OKR Cascade" in result.output
        assert "Company Goal" in result.output
        assert "Team Goal" in result.output

    @patch('cli.commands.org.okr._helpers.run_bd')
    def test_cascade_with_root(self, mock_run_bd, runner, initialized_org):
        """Should show cascade from specific root."""
        mock_run_bd.return_value = MagicMock(
            returncode=0,
            stdout="okr-abc tree output",
            stderr=""
        )

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "cascade", "--root=okr-abc"
        ])

        assert result.exit_code == 0
        # Verify bd dep tree was called
        call_args = mock_run_bd.call_args[0][0]
        assert "dep" in call_args
        assert "tree" in call_args


class TestOkrShowCommand:
    """Test qn org okr show command."""

    def test_show_requires_init(self, runner, temp_org):
        """Should require org to be initialized."""
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "okr", "show", "okr-abc"
        ])
        assert result.exit_code != 0
        assert "not initialized" in result.output.lower() or "Run 'qn org init'" in result.output

    @patch('cli.commands.org.okr._helpers.run_bd')
    def test_show_displays_okr(self, mock_run_bd, runner, initialized_org):
        """Should display OKR details."""
        # First call: bd show
        # Second call: bd list --serves
        mock_run_bd.side_effect = [
            MagicMock(returncode=0, stdout="OKR Details Here", stderr=""),
            MagicMock(returncode=0, stdout="[]", stderr=""),
        ]

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "show", "okr-abc"
        ])

        assert result.exit_code == 0
        assert "OKR Details" in result.output or "Work items" in result.output

    @patch('cli.commands.org.okr._helpers.run_bd')
    def test_show_okr_not_found(self, mock_run_bd, runner, initialized_org):
        """Should error when OKR not found."""
        mock_run_bd.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Issue not found"
        )

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "show", "nonexistent"
        ])

        assert result.exit_code != 0
        assert "not found" in result.output.lower()


class TestOkrProgressCommand:
    """Test qn org okr progress command."""

    def test_progress_requires_init(self, runner, temp_org):
        """Should require org to be initialized."""
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "okr", "progress", "okr-abc"
        ])
        assert result.exit_code != 0
        assert "not initialized" in result.output.lower() or "Run 'qn org init'" in result.output

    def test_progress_okr_not_found(self, runner, initialized_org):
        """Should error when OKR not found."""
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "progress", "nonexistent-okr"
        ])

        assert result.exit_code != 0
        assert "not found" in result.output.lower()


class TestOkrUpdateKrCommand:
    """Test qn org okr update-kr command."""

    def test_update_kr_requires_init(self, runner, temp_org):
        """Should require org to be initialized."""
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "okr", "update-kr", "okr-abc", "--metric=test"
        ])
        assert result.exit_code != 0
        assert "not initialized" in result.output.lower() or "Run 'qn org init'" in result.output

    def test_update_kr_requires_metric(self, runner, initialized_org):
        """Should require --metric option."""
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "update-kr", "okr-abc"
        ])
        assert result.exit_code != 0
        assert "metric" in result.output.lower() or "--metric" in result.output


class TestOkrLinkCommand:
    """Test qn org okr link command."""

    def test_link_requires_init(self, runner, temp_org):
        """Should require org to be initialized."""
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "okr", "link", "task-abc", "okr-xyz"
        ])
        assert result.exit_code != 0
        assert "not initialized" in result.output.lower() or "Run 'qn org init'" in result.output

    @patch('cli.commands.org.okr._helpers.run_bd')
    def test_link_creates_dependency(self, mock_run_bd, runner, initialized_org):
        """Should create serves dependency via bd."""
        mock_run_bd.return_value = MagicMock(
            returncode=0,
            stdout="Dependency added",
            stderr=""
        )

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "link", "task-abc", "okr-xyz"
        ])

        assert result.exit_code == 0
        assert "Linked" in result.output or "serves" in result.output

        # Verify bd dep add was called with serves type
        call_args = mock_run_bd.call_args[0][0]
        assert "dep" in call_args
        assert "add" in call_args
        assert "serves" in call_args

    @patch('cli.commands.org.okr._helpers.run_bd')
    def test_link_handles_error(self, mock_run_bd, runner, initialized_org):
        """Should error when link fails."""
        mock_run_bd.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Issue not found"
        )

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "link", "bad-id", "okr-xyz"
        ])

        assert result.exit_code != 0
        assert "Failed" in result.output or "not found" in result.output.lower()


class TestOkrErrorHandling:
    """Test error handling in OKR commands."""

    @patch('cli.commands.org.okr._helpers.run_bd')
    def test_handles_bd_error(self, mock_run_bd, runner, initialized_org):
        """Should handle bd errors gracefully."""
        mock_run_bd.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Beads error: something went wrong"
        )

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "set", "--title=Test"
        ])

        assert result.exit_code != 0
        assert "Failed" in result.output or "error" in result.output.lower()

    @patch('cli.commands.org.okr._helpers.run_bd')
    def test_handles_invalid_json(self, mock_run_bd, runner, initialized_org):
        """Should handle invalid JSON from bd."""
        mock_run_bd.return_value = MagicMock(
            returncode=0,
            stdout="not valid json{",
            stderr=""
        )

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "list"
        ])

        # Should not crash, should show no OKRs message
        assert result.exit_code == 0
        assert "No OKRs found" in result.output


class TestOkrDatabaseIntegration:
    """Test OKR database integration features."""

    @patch('cli.commands.org.okr.list_cmd._helpers.run_bd')
    def test_list_shows_empty_message_when_no_okrs(self, mock_run_bd, runner, initialized_org):
        """qn org okr list shows the empty-state message when no OKRs exist.

        Beads is the canonical source for OKR ids; with no OKRs in beads,
        nothing is rendered regardless of what's in the SQLite mirror.
        """
        mock_run_bd.return_value = MagicMock(returncode=0, stdout="[]", stderr="")

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "list"
        ])

        assert result.exit_code == 0
        assert "No OKRs found" in result.output

    @patch('cli.commands.org.okr.list_cmd._helpers.run_bd')
    def test_list_merges_beads_metadata_with_db_key_results(
        self, mock_run_bd, runner, initialized_org
    ):
        """qn org okr list merges beads (status/labels/priority) with db (KRs/progress)."""
        import json
        from cli.core.db import open_database, get_org_db_path
        from cli.core.queries import create_okr, add_okr_key_result

        db = open_database(get_org_db_path(initialized_org))
        try:
            from cli.core.org import Org
            org = Org.load(db)
            ceo_id = org.ceo_worker_id

            okr = create_okr(
                db=db,
                title="Test OKR from DB",
                owner_id=ceo_id,
                description="Test description",
                status="active",
                okr_id="test-merge-1",
            )
            add_okr_key_result(db, okr.id, "metric_a", 100.0, "count", 25.0)
        finally:
            db.close()

        # Beads returns the same OKR id so the merge succeeds.
        mock_run_bd.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps([{
                "id": "test-merge-1",
                "title": "Test OKR from DB",
                "status": "open",
                "priority": 1,
                "labels": ["okr"],
                "assignee": ceo_id,
                "created_at": "2026-04-28T00:00:00Z",
            }]),
            stderr="",
        )

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "list"
        ])

        assert result.exit_code == 0
        assert "Test OKR from DB" in result.output
        # Status comes from db (active), not beads (open) — db is authoritative for OKR state
        assert "active" in result.output
        # Priority comes from beads
        assert "P1" in result.output
        # KRs come from db
        assert "metric_a" in result.output
        assert "25" in result.output
        assert "100" in result.output

    @patch('cli.commands.org.okr._helpers.run_bd')
    def test_set_stores_in_database(self, mock_run_bd, runner, initialized_org):
        """OKR set should also store OKR in database."""
        from cli.core.db import open_database, get_org_db_path
        from cli.core.queries import get_okr

        # Mock successful beads creation
        mock_run_bd.return_value = MagicMock(
            returncode=0,
            stdout="✓ Created issue: test-abc\n  Title: DB Test OKR",
            stderr=""
        )

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "set",
            "--title", "DB Test OKR",
            "--owner", "TestCEO",
            "--description", "Test description"
        ])

        assert result.exit_code == 0

        # Verify OKR was stored in database
        db = open_database(get_org_db_path(initialized_org))
        try:
            okr = get_okr(db, "test-abc")
            assert okr is not None
            assert okr.title == "DB Test OKR"
            assert okr.description == "Test description"
        finally:
            db.close()

    @patch('cli.commands.org.okr.list_cmd._helpers.run_bd')
    def test_list_respects_status_filter(self, mock_run_bd, runner, initialized_org):
        """qn org okr list --status=<x> passes the right filter to beads.

        Filtering happens via beads (`bd list --status=...`); the test
        verifies the status flag round-trips correctly and the filtered
        beads response controls what's rendered.
        """
        import json

        active_response = json.dumps([{
            "id": "test-active-1", "title": "Active OKR",
            "status": "open", "priority": 2, "labels": ["okr"],
        }])
        completed_response = json.dumps([{
            "id": "test-completed-1", "title": "Completed OKR",
            "status": "closed", "priority": 2, "labels": ["okr"],
        }])

        # First call: active
        mock_run_bd.return_value = MagicMock(returncode=0, stdout=active_response, stderr="")
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "list", "--status=active"
        ])
        assert result.exit_code == 0
        assert "Active OKR" in result.output
        assert "Completed OKR" not in result.output
        # Verify status filter mapped to beads 'open'
        bd_args = mock_run_bd.call_args[0][0]
        assert "--status=open" in bd_args

        # Second call: completed
        mock_run_bd.return_value = MagicMock(returncode=0, stdout=completed_response, stderr="")
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "list", "--status=completed"
        ])
        assert result.exit_code == 0
        assert "Completed OKR" in result.output
        assert "Active OKR" not in result.output
        # Verify completed maps to beads 'closed'
        bd_args = mock_run_bd.call_args[0][0]
        assert "--status=closed" in bd_args


class TestOkrCloseCommand:
    """Test qn org okr close (regression for quinn-ai-kljb).

    Workers reach for `bd close <okr-id>` because OKR ids share the beads
    format, but bd close alone leaves the SQLite okrs.status row stuck on
    'active'. `qn org okr close` updates BOTH stores.
    """

    def test_close_help_listed_in_group(self, runner):
        """qn org okr --help should advertise the close subcommand."""
        result = runner.invoke(qn, ["org", "okr", "--help"])
        assert result.exit_code == 0
        assert "close" in result.output

    def test_close_requires_init(self, runner, temp_org):
        result = runner.invoke(qn, [
            "--org-path", str(temp_org),
            "org", "okr", "close", "myorg-abc",
        ])
        assert result.exit_code != 0
        assert "not initialized" in result.output.lower() or "Run 'qn org init'" in result.output

    @patch('cli.commands.org.okr.manage._helpers.run_bd')
    def test_close_invokes_bd_close_and_updates_sqlite(
        self, mock_run_bd, runner, initialized_org
    ):
        """Closing an OKR fires `bd close <id>` AND flips SQLite status."""
        from cli.core.db import get_org_db_path, open_database
        from cli.core.queries import create_okr, get_okr

        # Seed a real OKR row in SQLite so update_okr_status has something to flip.
        db_path = get_org_db_path(initialized_org)
        db = open_database(db_path)
        try:
            from cli.core.org import Org
            ceo_id = Org.load(db).ceo_worker_id
            create_okr(
                db=db,
                title="Test OKR",
                owner_id=ceo_id,
                description="seeded for close test",
                status="active",
                okr_id="testorg-close1",
            )
        finally:
            db.close()

        mock_run_bd.return_value = MagicMock(returncode=0, stdout="Closed: testorg-close1", stderr="")

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "close", "testorg-close1",
        ])
        assert result.exit_code == 0, result.output
        # bd close <id> was called
        bd_args = mock_run_bd.call_args[0][0]
        assert bd_args[0] == "close"
        assert bd_args[1] == "testorg-close1"
        # SQLite mirror reflects closure
        db = open_database(db_path)
        try:
            okr = get_okr(db, "testorg-close1")
            assert okr is not None
            assert okr.status == "completed"
        finally:
            db.close()
        assert "Closed OKR testorg-close1" in result.output

    @patch('cli.commands.org.okr.manage._helpers.run_bd')
    def test_close_supports_cancelled_status(
        self, mock_run_bd, runner, initialized_org
    ):
        """--status=cancelled abandons rather than completes the OKR."""
        from cli.core.db import get_org_db_path, open_database
        from cli.core.queries import create_okr, get_okr

        db_path = get_org_db_path(initialized_org)
        db = open_database(db_path)
        try:
            from cli.core.org import Org
            ceo_id = Org.load(db).ceo_worker_id
            create_okr(
                db=db, title="Doomed OKR", owner_id=ceo_id,
                description="will be cancelled", status="active",
                okr_id="testorg-cancel1",
            )
        finally:
            db.close()

        mock_run_bd.return_value = MagicMock(returncode=0, stdout="Closed", stderr="")
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "close", "testorg-cancel1",
            "--status=cancelled", "--reason=superseded",
        ])
        assert result.exit_code == 0, result.output

        # --reason flowed through to bd close
        bd_args = mock_run_bd.call_args[0][0]
        assert "--reason" in bd_args
        assert "superseded" in bd_args

        db = open_database(db_path)
        try:
            okr = get_okr(db, "testorg-cancel1")
            assert okr.status == "cancelled"
        finally:
            db.close()

    @patch('cli.commands.org.okr.manage._helpers.run_bd')
    def test_close_propagates_bd_failure(self, mock_run_bd, runner, initialized_org):
        """If bd close fails (id not found, permission), surface the error."""
        mock_run_bd.return_value = MagicMock(
            returncode=1, stdout="", stderr="issue 'nope-xyz' not found",
        )
        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "close", "nope-xyz",
        ])
        assert result.exit_code != 0
        assert "Failed to close OKR" in result.output

    @patch('cli.commands.org.okr.manage._helpers.run_bd')
    def test_close_tolerates_missing_sqlite_mirror(
        self, mock_run_bd, runner, initialized_org
    ):
        """Closing an OKR that exists as a bead but has no SQLite mirror row
        should still succeed — bead is the source of truth."""
        mock_run_bd.return_value = MagicMock(returncode=0, stdout="Closed", stderr="")

        result = runner.invoke(qn, [
            "--org-path", str(initialized_org),
            "org", "okr", "close", "ghost-okr-id",
        ])
        # bd close succeeded and we don't fail just because the SQLite mirror
        # is missing (legacy / direct-bd OKRs).
        assert result.exit_code == 0, result.output
        assert "Closed OKR ghost-okr-id" in result.output
