"""
Tests for 'msgr search' subcommand.

These tests are INTENTIONALLY FAILING — the 'search' subcommand does not yet
exist in cli/msgr/main.py (not registered).
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from cli.core.db import init_database
from cli.core.queries.channel import create_channel, create_message
from cli.msgr.main import msgr


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def initialized_org():
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir)
        r = CliRunner()
        from cli.commands.main import qn
        result = r.invoke(qn, [
            "--org-path", str(org_path), "org", "init",
            "--ceo-name", "SearchTestCEO", "--skip-okrs",
        ])
        assert result.exit_code == 0, result.output
        yield org_path


def _ceo_id(org_path: Path) -> str:
    conn = sqlite3.connect(str(org_path / "live" / "quinn.db"))
    try:
        return conn.execute("SELECT id FROM workers WHERE role='CEO'").fetchone()[0]
    finally:
        conn.close()


def _seed_messages(org_path: Path, worker_id: str) -> None:
    """Insert a handful of messages so search tests have data to work with."""
    db_path = org_path / "live" / "quinn.db"
    db = init_database(db_path)
    try:
        chan = create_channel(db, "general", "topic")
        other = create_channel(db, "random", "topic")
        create_message(db, chan.id, worker_id, "We are looking to fundraise in Q2")
        create_message(db, chan.id, worker_id, "Fundraise round closed successfully")
        create_message(db, chan.id, worker_id, "Completely unrelated update")
        create_message(db, other.id, worker_id, "fundraise discussion in random channel")
    finally:
        db.close()


class TestMsgrSearch:
    """Tests for the 'msgr search' subcommand."""

    def test_search_command_exists(self, runner, initialized_org):
        """'msgr search fundraise' must not exit with code 2 ('no such command')."""
        ceo_id = _ceo_id(initialized_org)

        result = runner.invoke(msgr, [
            "--org-path", str(initialized_org),
            "--worker-id", ceo_id,
            "search", "fundraise",
        ])

        assert result.exit_code != 2, (
            "exit_code==2 means 'no such command'; 'search' is not registered.\n"
            + result.output
        )

    def test_search_returns_results_when_matching(self, runner, initialized_org):
        """With matching messages in the DB, results should appear in output."""
        ceo_id = _ceo_id(initialized_org)
        _seed_messages(initialized_org, ceo_id)

        result = runner.invoke(msgr, [
            "--org-path", str(initialized_org),
            "--worker-id", ceo_id,
            "search", "fundraise",
        ])

        assert result.exit_code == 0, result.output
        assert "fundraise" in result.output.lower(), (
            f"Expected 'fundraise' in output, got:\n{result.output}"
        )

    def test_search_no_results_prints_message(self, runner, initialized_org):
        """Searching for a term with no matches must exit 0 and say 'No results'."""
        ceo_id = _ceo_id(initialized_org)

        result = runner.invoke(msgr, [
            "--org-path", str(initialized_org),
            "--worker-id", ceo_id,
            "search", "zzznomatchzzz",
        ])

        assert result.exit_code == 0, result.output
        assert "no results" in result.output.lower(), (
            f"Expected 'No results' message in output, got:\n{result.output}"
        )

    def test_search_channel_filter(self, runner, initialized_org):
        """'msgr search text --channel general' must only return messages from #general."""
        ceo_id = _ceo_id(initialized_org)
        _seed_messages(initialized_org, ceo_id)

        result = runner.invoke(msgr, [
            "--org-path", str(initialized_org),
            "--worker-id", ceo_id,
            "search", "fundraise", "--channel", "general",
        ])

        assert result.exit_code == 0, result.output
        # The 'random' channel message should not appear
        # (Implementation detail: we just check the flag is accepted and output is sane)
        output = result.output.lower()
        # Must return at least the general-channel messages
        assert "fundraise" in output, (
            f"Expected fundraise results from #general:\n{result.output}"
        )
        # The random-channel hit must NOT bleed in (if channel filtering works)
        assert "random channel" not in output, (
            f"random-channel message leaked into filtered results:\n{result.output}"
        )
