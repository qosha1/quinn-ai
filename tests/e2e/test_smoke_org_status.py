"""
E2E smoke tests for `qn org status` command.

Tests verify that org status reporting works correctly.
"""


def test_org_status_uninitialized(temp_org_dir, cli_runner):
    """Should fail gracefully when org not initialized."""
    result = cli_runner(
        ["--org-path", str(temp_org_dir), "org", "status"],
    )

    # Should fail
    assert result.returncode != 0
    # Should provide helpful error
    assert "not initialized" in result.stderr.lower() or "init" in result.stderr.lower()


def test_org_status_initialized(initialized_org, cli_runner):
    """Should show status for initialized org."""
    result = cli_runner(
        ["--org-path", str(initialized_org), "org", "status"],
        check=True,
    )

    assert result.returncode == 0

    # Should show org path
    assert str(initialized_org) in result.stdout

    # Should show status
    assert "Status:" in result.stdout
    assert "initialized" in result.stdout.lower()

    # Should show CEO info
    assert "CEO" in result.stdout
    assert "Name:" in result.stdout


def test_org_status_running(running_org, cli_runner):
    """Should show running status and active workers."""
    result = cli_runner(
        ["--org-path", str(running_org), "org", "status"],
        check=True,
    )

    assert result.returncode == 0

    # Should show running status
    assert "running" in result.stdout.lower()

    # Should show worker stats
    assert "Workers:" in result.stdout
    assert "Total:" in result.stdout


def test_org_status_auto_detection(initialized_org, cli_runner):
    """Should auto-detect org from working directory.

    Auto-detection looks for live/quinn.db, which exists after init.
    """
    # Auto-detection should work because live/quinn.db exists
    assert (initialized_org / "live" / "quinn.db").exists()

    # Run status from org directory without --org-path
    result = cli_runner(
        ["org", "status"],
        cwd=initialized_org,
        check=True,
    )

    assert result.returncode == 0
    assert "Status:" in result.stdout


def test_org_status_verbose(initialized_org, cli_runner):
    """Should provide more detail with --verbose flag."""
    result = cli_runner(
        ["--org-path", str(initialized_org), "--verbose", "org", "status"],
        check=True,
    )

    assert result.returncode == 0
    assert "Status:" in result.stdout
