"""
E2E smoke tests for full org lifecycle workflow.

Tests verify the complete workflow: init → start → status → stop.
"""


def test_full_workflow_init_start_status_stop(temp_org_dir, cli_runner):
    """Should complete full org lifecycle without errors.

    Workflow:
    1. Initialize org
    2. Check status (should be initialized)
    3. Start org
    4. Check status (should be running)
    5. Stop org
    6. Check status (should be stopped)
    """
    # Step 1: Initialize
    init_result = cli_runner(
        [
            "--org-path", str(temp_org_dir),
            "org", "init",
            "--ceo-name", "TestCEO",
            "--ceo-role", "CEO",
        ],
        check=True,
    )

    assert init_result.returncode == 0
    assert "Initialized organization" in init_result.stdout

    # Step 2: Check status (initialized)
    status_result = cli_runner(
        ["--org-path", str(temp_org_dir), "org", "status"],
        check=True,
    )

    assert status_result.returncode == 0
    assert "initialized" in status_result.stdout.lower()
    assert "TestCEO" in status_result.stdout

    # Step 3: Start org
    start_result = cli_runner(
        [
            "--org-path", str(temp_org_dir),
            "org", "start",
            "--no-spawn-ceo",
            "--skip-config-validation",
        ],
        check=True,
    )

    assert start_result.returncode == 0
    assert "Organization started" in start_result.stdout or "running" in start_result.stdout.lower()

    # Step 4: Check status (running)
    status_result = cli_runner(
        ["--org-path", str(temp_org_dir), "org", "status"],
        check=True,
    )

    assert status_result.returncode == 0
    assert "running" in status_result.stdout.lower()

    # Step 5: Stop org
    stop_result = cli_runner(
        [
            "--org-path", str(temp_org_dir),
            "org", "stop",
            "--yes",
            "--force",
        ],
        check=True,
    )

    assert stop_result.returncode == 0
    assert "stopped" in stop_result.stdout.lower()

    # Step 6: Check status (stopped)
    status_result = cli_runner(
        ["--org-path", str(temp_org_dir), "org", "status"],
        check=True,
    )

    assert status_result.returncode == 0
    assert "stopped" in status_result.stdout.lower()


def test_full_workflow_with_auto_detection(temp_org_dir, cli_runner):
    """Should complete full workflow using auto-detection.

    Auto-detection looks for live/quinn.db. After init, this file exists
    and subsequent commands can auto-detect the org root.
    """
    # Initialize (must use --org-path since DB doesn't exist yet)
    cli_runner(
        ["--org-path", str(temp_org_dir), "org", "init"],
        check=True,
    )

    # Verify DB exists for auto-detection
    assert (temp_org_dir / "live" / "quinn.db").exists()

    # Now auto-detection should work for remaining commands

    # Start (auto-detect)
    cli_runner(
        ["org", "start", "--no-spawn-ceo", "--skip-config-validation"],
        cwd=temp_org_dir,
        check=True,
    )

    # Check status (auto-detect)
    status_result = cli_runner(
        ["org", "status"],
        cwd=temp_org_dir,
        check=True,
    )

    assert "running" in status_result.stdout.lower()

    # Stop (auto-detect)
    cli_runner(
        ["org", "stop", "--yes", "--force"],
        cwd=temp_org_dir,
        check=True,
    )


def test_full_workflow_start_stop_restart(temp_org_dir, cli_runner):
    """Should support stop and restart cycle.

    Workflow:
    1. Init → Start → Stop
    2. Start again (resume)
    3. Stop again
    """
    # Initialize
    cli_runner(
        ["--org-path", str(temp_org_dir), "org", "init"],
        check=True,
    )

    # First start
    cli_runner(
        [
            "--org-path", str(temp_org_dir),
            "org", "start",
            "--no-spawn-ceo",
            "--skip-config-validation",
        ],
        check=True,
    )

    # First stop
    cli_runner(
        [
            "--org-path", str(temp_org_dir),
            "org", "stop",
            "--yes",
            "--force",
        ],
        check=True,
    )

    # Restart (should work from stopped state)
    restart_result = cli_runner(
        [
            "--org-path", str(temp_org_dir),
            "org", "start",
            "--no-spawn-ceo",
            "--skip-config-validation",
        ],
        check=True,
    )

    assert restart_result.returncode == 0

    # Verify running
    status_result = cli_runner(
        ["--org-path", str(temp_org_dir), "org", "status"],
        check=True,
    )

    assert "running" in status_result.stdout.lower()

    # Final stop
    cli_runner(
        [
            "--org-path", str(temp_org_dir),
            "org", "stop",
            "--yes",
            "--force",
        ],
        check=True,
    )


def test_full_workflow_with_verbose_logging(temp_org_dir, cli_runner):
    """Should support verbose and debug logging throughout workflow."""
    # Initialize with verbose
    cli_runner(
        ["--org-path", str(temp_org_dir), "--verbose", "org", "init"],
        check=True,
    )

    # Start with debug
    cli_runner(
        [
            "--org-path", str(temp_org_dir),
            "--debug",
            "org", "start",
            "--no-spawn-ceo",
            "--skip-config-validation",
        ],
        check=True,
    )

    # Status with verbose
    status_result = cli_runner(
        ["--org-path", str(temp_org_dir), "--verbose", "org", "status"],
        check=True,
    )

    assert status_result.returncode == 0

    # Stop with debug
    cli_runner(
        [
            "--org-path", str(temp_org_dir),
            "--debug",
            "org", "stop",
            "--yes",
            "--force",
        ],
        check=True,
    )


def test_full_workflow_handles_errors_gracefully(temp_org_dir, cli_runner):
    """Should provide helpful errors for invalid operations."""
    # Try to start before init
    start_result = cli_runner(
        ["--org-path", str(temp_org_dir), "org", "start"],
    )

    assert start_result.returncode != 0
    assert "not initialized" in start_result.stderr.lower()

    # Initialize
    cli_runner(
        ["--org-path", str(temp_org_dir), "org", "init"],
        check=True,
    )

    # Try to stop before start
    stop_result = cli_runner(
        ["--org-path", str(temp_org_dir), "org", "stop", "--yes"],
    )

    assert stop_result.returncode != 0

    # Now start and stop should work
    cli_runner(
        [
            "--org-path", str(temp_org_dir),
            "org", "start",
            "--no-spawn-ceo",
            "--skip-config-validation",
        ],
        check=True,
    )

    cli_runner(
        [
            "--org-path", str(temp_org_dir),
            "org", "stop",
            "--yes",
            "--force",
        ],
        check=True,
    )
