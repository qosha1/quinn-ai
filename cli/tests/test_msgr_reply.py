"""
Tests for msgr send --reply-to threading feature.

These tests are INTENTIONALLY FAILING — the --reply-to option does not yet
exist in cli/msgr/commands/send.py.
"""

import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from cli.core.db import init_database, get_org_db_path
from cli.core.org_init import OrgInitConfig, init_org
from cli.core.queries.channel import create_channel, create_message, get_message
from cli.msgr.main import msgr

import sqlite3


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def initialized_org():
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir)
        runner = CliRunner()
        from cli.commands.main import qn
        result = runner.invoke(qn, [
            "--org-path", str(org_path), "org", "init",
            "--ceo-name", "ReplyTestCEO", "--skip-okrs",
        ])
        assert result.exit_code == 0, result.output
        yield org_path


def _ceo_id(org_path: Path) -> str:
    conn = sqlite3.connect(str(org_path / "live" / "quinn.db"))
    try:
        return conn.execute("SELECT id FROM workers WHERE role='CEO'").fetchone()[0]
    finally:
        conn.close()


def _general_channel_id(org_path: Path) -> str:
    conn = sqlite3.connect(str(org_path / "live" / "quinn.db"))
    try:
        row = conn.execute("SELECT id FROM channels WHERE name='general'").fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _create_parent_message(org_path: Path, worker_id: str) -> str:
    """Insert a parent message directly via DB, return its ID."""
    db_path = org_path / "live" / "quinn.db"
    db = init_database(db_path)
    try:
        chan_id = _general_channel_id(org_path)
        msg = create_message(db, chan_id, worker_id, "Parent message for threading")
        return msg.id
    finally:
        db.close()


class TestSendReplyTo:
    """Tests for --reply-to option on msgr send."""

    def test_send_with_reply_to_creates_threaded_message(
        self, runner, initialized_org
    ):
        """Invoking 'msgr send #general "reply" --reply-to msg-123' should
        succeed and produce a message with parent_id == 'msg-123'."""
        ceo_id = _ceo_id(initialized_org)
        parent_id = _create_parent_message(initialized_org, ceo_id)

        result = runner.invoke(msgr, [
            "--org-path", str(initialized_org),
            "--worker-id", ceo_id,
            "send", "#general", "This is a reply",
            "--reply-to", parent_id,
        ])

        assert result.exit_code == 0, result.output

        # The newly created reply message must have parent_id set.
        # Parse message ID from output ("  ID: msg-xxx")
        msg_id = None
        for line in result.output.splitlines():
            if line.strip().startswith("ID:"):
                msg_id = line.strip().split("ID:")[-1].strip()
                break

        assert msg_id is not None, f"No message ID in output:\n{result.output}"

        db_path = initialized_org / "live" / "quinn.db"
        db = init_database(db_path)
        try:
            msg = get_message(db, msg_id)
            assert msg is not None
            assert msg.parent_id == parent_id
        finally:
            db.close()

    def test_send_reply_to_nonexistent_message_fails(
        self, runner, initialized_org
    ):
        """Replying to a non-existent message ID must exit non-zero with an error."""
        ceo_id = _ceo_id(initialized_org)

        result = runner.invoke(msgr, [
            "--org-path", str(initialized_org),
            "--worker-id", ceo_id,
            "send", "#general", "Orphan reply",
            "--reply-to", "msg-does-not-exist",
        ])

        assert result.exit_code != 0, (
            "Expected non-zero exit when replying to a nonexistent message, "
            f"got exit_code={result.exit_code}\n{result.output}"
        )

    def test_send_reply_inherits_channel_from_parent(
        self, runner, initialized_org
    ):
        """A reply message must be posted to the same channel as its parent."""
        ceo_id = _ceo_id(initialized_org)
        parent_id = _create_parent_message(initialized_org, ceo_id)
        parent_chan = _general_channel_id(initialized_org)

        result = runner.invoke(msgr, [
            "--org-path", str(initialized_org),
            "--worker-id", ceo_id,
            "send", "#general", "Channel-inheriting reply",
            "--reply-to", parent_id,
        ])

        assert result.exit_code == 0, result.output

        msg_id = None
        for line in result.output.splitlines():
            if line.strip().startswith("ID:"):
                msg_id = line.strip().split("ID:")[-1].strip()
                break

        assert msg_id is not None, f"No message ID in output:\n{result.output}"

        db_path = initialized_org / "live" / "quinn.db"
        db = init_database(db_path)
        try:
            msg = get_message(db, msg_id)
            assert msg is not None
            assert msg.channel_id == parent_chan, (
                f"Reply channel_id {msg.channel_id!r} != parent channel_id {parent_chan!r}"
            )
        finally:
            db.close()
