"""
E2E smoke tests for `qn org stop` command.

Tests verify org stopping works end-to-end.
"""


def test_org_stop_uninitialized(temp_org_dir, cli_runner):
    """Should fail gracefully when org not initialized."""
    result = cli_runner(
        ["--org-path", str(temp_org_dir), "org", "stop", "--yes"],
    )

    # Should fail
    assert result.returncode != 0
    assert "not initialized" in result.stderr.lower()


def test_org_stop_not_running(initialized_org, cli_runner):
    """Should fail gracefully when org not running."""
    result = cli_runner(
        ["--org-path", str(initialized_org), "org", "stop", "--yes"],
    )

    # Should fail with meaningful error
    assert result.returncode != 0
    assert "cannot stop" in result.stderr.lower() or "not running" in result.stderr.lower()


def test_org_stop_success(running_org, cli_runner):
    """Should successfully stop running org."""
    result = cli_runner(
        [
            "--org-path", str(running_org),
            "org", "stop",
            "--yes",  # Skip confirmation
            "--force",  # Force stop without graceful shutdown
        ],
        check=True,
    )

    assert result.returncode == 0
    assert "stopped" in result.stdout.lower()

    # Verify status changed to stopped
    status_result = cli_runner(
        ["--org-path", str(running_org), "org", "status"],
        check=True,
    )

    assert "stopped" in status_result.stdout.lower()


def test_org_stop_idempotent(running_org, cli_runner):
    """Should be idempotent - stopping already stopped org should succeed."""
    # Stop org
    cli_runner(
        [
            "--org-path", str(running_org),
            "org", "stop",
            "--yes",
            "--force",
        ],
        check=True,
    )

    # Stop again
    result = cli_runner(
        [
            "--org-path", str(running_org),
            "org", "stop",
            "--yes",
            "--force",
        ],
        check=True,
    )

    assert result.returncode == 0
    assert "already stopped" in result.stdout.lower()


def test_org_stop_graceful_timeout(running_org, cli_runner):
    """Should respect graceful timeout parameter."""
    result = cli_runner(
        [
            "--org-path", str(running_org),
            "org", "stop",
            "--yes",
            "--graceful-timeout", "5",
        ],
        check=True,
        timeout=15,  # Should finish well before this
    )

    assert result.returncode == 0


def test_org_stop_force(running_org, cli_runner):
    """Should force stop without graceful shutdown."""
    result = cli_runner(
        [
            "--org-path", str(running_org),
            "org", "stop",
            "--yes",
            "--force",
        ],
        check=True,
    )

    assert result.returncode == 0
    # Force should skip wrap-up
    assert "stopped" in result.stdout.lower()


def test_org_stop_auto_detection(running_org, cli_runner):
    """Should auto-detect org from working directory.

    Auto-detection looks for live/quinn.db, which exists in running org.
    """
    # Auto-detection should work because live/quinn.db exists
    assert (running_org / "live" / "quinn.db").exists()

    result = cli_runner(
        [
            "org", "stop",
            "--yes",
            "--force",
        ],
        cwd=running_org,
        check=True,
    )

    assert result.returncode == 0


def test_org_stop_cleanup(running_org, cli_runner):
    """Should run cleanup by default."""
    result = cli_runner(
        [
            "--org-path", str(running_org),
            "org", "stop",
            "--yes",
            "--force",
            "--cleanup",  # Explicit, but should be default
        ],
        check=True,
    )

    assert result.returncode == 0


def test_org_stop_no_cleanup(running_org, cli_runner):
    """Should skip cleanup when requested."""
    result = cli_runner(
        [
            "--org-path", str(running_org),
            "org", "stop",
            "--yes",
            "--force",
            "--no-cleanup",
        ],
        check=True,
    )

    assert result.returncode == 0
