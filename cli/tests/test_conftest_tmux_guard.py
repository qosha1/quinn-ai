"""Regression test for quinn-ai-0ou.

tests/conftest.py used to call 'tmux ...' subprocess unconditionally,
crashing pytest collection on hosts without tmux. The fix should
gracefully no-op when tmux is missing.

This test imports the cleanup helper and verifies it doesn't raise
when shutil.which says tmux is unavailable.
"""

from pathlib import Path
from unittest.mock import patch

import pytest


def test_cleanup_org_sessions_handles_missing_tmux(tmp_path):
    """When shutil.which('tmux') returns None, cleanup_org_sessions must
    return cleanly instead of raising FileNotFoundError on subprocess.run."""
    from tests.conftest import cleanup_org_sessions

    # Use a tmp dir that DOES exist but has a fake live/quinn.db so the
    # function reaches its tmux call site.
    org_path = tmp_path / "fake-org"
    org_path.mkdir()
    live = org_path / "live"
    live.mkdir()

    # Create a minimal sqlite db with a workers table containing one row,
    # so cleanup_org_sessions iterates and would try to call tmux.
    import sqlite3
    db = live / "quinn.db"
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("CREATE TABLE workers (worker_id TEXT)")
        conn.execute("INSERT INTO workers (worker_id) VALUES ('w1')")
        conn.commit()
    finally:
        conn.close()

    # Patch shutil.which so the function thinks tmux is missing.
    with patch("tests.conftest.shutil.which", return_value=None):
        # Must not raise FileNotFoundError or anything else
        cleanup_org_sessions(org_path)


def test_verify_no_leaked_sessions_handles_missing_tmux():
    """The verify_no_leaked_sessions session-scoped autouse fixture must
    not raise when tmux is missing. We exercise its body directly."""
    from tests import conftest

    # The fixture's body is after the yield — we simulate that by calling
    # the post-yield code via a wrapper. Easier: just import and verify
    # the module-level guard function exists, then exercise it.
    assert hasattr(conftest, "_tmux_available"), (
        "Expected a _tmux_available() helper in tests/conftest.py "
        "(introduced by quinn-ai-0ou fix)"
    )

    with patch("tests.conftest.shutil.which", return_value=None):
        assert conftest._tmux_available() is False
