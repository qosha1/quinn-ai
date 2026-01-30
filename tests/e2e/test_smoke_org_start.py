"""
E2E smoke tests for `qn org start` command.

Tests verify org starting works end-to-end (without actually spawning sessions).
"""


def test_org_start_uninitialized(temp_org_dir, cli_runner):
    """Should fail gracefully when org not initialized."""
    result = cli_runner(
        ["--org-path", str(temp_org_dir), "org", "start", "--no-spawn-ceo"],
    )

    # Should fail
    assert result.returncode != 0
    assert "not initialized" in result.stderr.lower() or "init" in result.stderr.lower()


def test_org_start_success(initialized_org, cli_runner):
    """Should successfully start org from initialized state."""
    # Start org without spawning CEO session
    result = cli_runner(
        [
            "--org-path", str(initialized_org),
            "org", "start",
            "--no-spawn-ceo",
            "--skip-config-validation",
        ],
        check=True,
    )

    assert result.returncode == 0
    assert "Organization started" in result.stdout or "running" in result.stdout.lower()

    # Verify status changed to running
    status_result = cli_runner(
        ["--org-path", str(initialized_org), "org", "status"],
        check=True,
    )

    assert "running" in status_result.stdout.lower()


def test_org_start_idempotent(running_org, cli_runner):
    """Should be idempotent - starting already running org should succeed."""
    result = cli_runner(
        [
            "--org-path", str(running_org),
            "org", "start",
            "--no-spawn-ceo",
            "--skip-config-validation",
        ],
        check=True,
    )

    assert result.returncode == 0
    assert "already running" in result.stdout.lower()


def test_org_start_missing_config(initialized_org, cli_runner):
    """Should fail when provider config missing (unless skipped)."""
    # Remove provider config
    config_file = initialized_org / "config" / "providers.yaml"
    if config_file.exists():
        config_file.unlink()

    # Should fail without --skip-config-validation
    result = cli_runner(
        ["--org-path", str(initialized_org), "org", "start"],
    )

    assert result.returncode != 0
    assert "config" in result.stderr.lower()


def test_org_start_invalid_status_transition(initialized_org, cli_runner):
    """Should handle invalid state transitions gracefully."""
    # Start org successfully first
    cli_runner(
        [
            "--org-path", str(initialized_org),
            "org", "start",
            "--no-spawn-ceo",
            "--skip-config-validation",
        ],
        check=True,
    )

    # Starting already running should be idempotent (not error)
    result = cli_runner(
        [
            "--org-path", str(initialized_org),
            "org", "start",
            "--no-spawn-ceo",
            "--skip-config-validation",
        ],
        check=True,
    )

    assert result.returncode == 0


def test_org_start_auto_detection(initialized_org, cli_runner):
    """Should auto-detect org from working directory.

    Auto-detection looks for live/quinn.db, which exists after init.
    """
    # Auto-detection should work because live/quinn.db exists
    assert (initialized_org / "live" / "quinn.db").exists()

    result = cli_runner(
        [
            "org", "start",
            "--no-spawn-ceo",
            "--skip-config-validation",
        ],
        cwd=initialized_org,
        check=True,
    )

    assert result.returncode == 0


def test_org_start_creates_required_dirs(initialized_org, cli_runner):
    """Should handle case where storage dirs exist."""
    # Ensure storage dirs exist (they should from init, but verify robustness)
    assert (initialized_org / "storage" / "shared").exists()
    assert (initialized_org / "storage" / "workers").exists()

    result = cli_runner(
        [
            "--org-path", str(initialized_org),
            "org", "start",
            "--no-spawn-ceo",
            "--skip-config-validation",
        ],
        check=True,
    )

    assert result.returncode == 0
