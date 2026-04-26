"""Regression test for quinn-ai-lxp.

The bootstrap OKR (created during 'qn org init --skip-okrs') must now
exist as a bead AND in the SQLite okrs table, sharing the same id.
Previously it only existed in SQLite, so 'qn org okr list' (which
reads beads) returned 'No OKRs found' on a fresh org.
"""

import sqlite3
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


def test_bootstrap_okr_appears_in_beads_view(runner, initialized_org):
    """qn org okr list (reads beads) must surface the bootstrap OKR."""
    result = runner.invoke(qn, [
        "--org-path", str(initialized_org), "org", "okr", "list",
    ])
    assert result.exit_code == 0, result.output
    # The bootstrap OKR title is 'Establish organizational foundation'
    # (cli/core/constants/system.py: DEFAULT_BOOTSTRAP_OKR_TITLE)
    assert "Establish" in result.output, (
        f"Expected bootstrap OKR in beads view. Got:\n{result.output}"
    )


def test_bootstrap_okr_id_matches_between_stores(runner, initialized_org):
    """The bd id and the SQLite okrs.id must be the same value, so
    cross-store references (e.g. `bd dep add ... serves:<id>`) work."""
    # Read SQLite id
    conn = sqlite3.connect(str(initialized_org / "live" / "quinn.db"))
    try:
        sqlite_id, sqlite_title = conn.execute(
            "SELECT id, title FROM okrs LIMIT 1"
        ).fetchone()
    finally:
        conn.close()

    # Read beads view, look for the same id
    result = runner.invoke(qn, [
        "--org-path", str(initialized_org), "org", "okr", "list",
    ])
    assert result.exit_code == 0, result.output
    assert sqlite_id in result.output, (
        f"SQLite OKR id {sqlite_id!r} (title: {sqlite_title!r}) does not "
        f"appear in beads-view output. Stores are diverged.\n"
        f"qn org okr list output:\n{result.output}"
    )


def test_bootstrap_okr_id_format_is_bead_style(runner, initialized_org):
    """When bd is available, the bootstrap OKR id should be in the
    bd-issue format ({prefix}-{shortid}), NOT the legacy 'okr-...' format."""
    conn = sqlite3.connect(str(initialized_org / "live" / "quinn.db"))
    try:
        (okr_id,) = conn.execute("SELECT id FROM okrs LIMIT 1").fetchone()
    finally:
        conn.close()

    # bd issue ids look like 'foo-abc123' where foo is the org prefix
    # (typically the parent dir name). The legacy format 'okr-abc...' is
    # the fallback used only when bd creation fails.
    assert not okr_id.startswith("okr-"), (
        f"Bootstrap OKR id {okr_id!r} is in legacy 'okr-...' format. "
        f"Expected bd-issue format ({{prefix}}-{{shortid}}). bd creation "
        f"may have failed silently — check init output."
    )
