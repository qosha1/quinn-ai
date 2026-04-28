"""
E2E smoke tests for `qn org init` command.

Tests verify that org initialization works end-to-end via actual CLI invocation.
"""

from pathlib import Path


def test_org_init_success(temp_org_dir, cli_runner):
    """Should successfully initialize a new org from scratch."""
    # Run org init
    result = cli_runner(
        ["--org-path", str(temp_org_dir), "org", "init"],
        check=True,
    )

    # Verify exit code
    assert result.returncode == 0

    # Verify output messages
    assert "Initialized organization" in result.stdout
    assert "Created CEO" in result.stdout
    assert str(temp_org_dir) in result.stdout

    # Verify directory structure
    assert (temp_org_dir / "config").exists()
    assert (temp_org_dir / "live").exists()
    assert (temp_org_dir / "storage").exists()
    assert (temp_org_dir / "storage" / "shared").exists()
    assert (temp_org_dir / "storage" / "workers").exists()

    # Verify database
    assert (temp_org_dir / "live" / "quinn.db").exists()

    # Verify config files
    assert (temp_org_dir / "config" / "providers.yaml").exists()


def test_org_init_with_custom_ceo(temp_org_dir, cli_runner):
    """Should initialize org with a custom CEO name."""
    # --ceo-role was removed (CEO is always the role); only --ceo-name remains.
    result = cli_runner(
        [
            "--org-path", str(temp_org_dir),
            "org", "init",
            "--ceo-name", "Alice",
        ],
        check=True,
    )

    assert result.returncode == 0
    assert "Alice" in result.stdout, f"missing 'Alice' in init output:\n{result.stdout}"


def test_org_init_already_exists(initialized_org, cli_runner):
    """Should fail gracefully if org already initialized."""
    # Try to init again
    result = cli_runner(
        ["--org-path", str(initialized_org), "org", "init"],
    )

    # Should fail (but not crash)
    assert result.returncode != 0
    # Should provide helpful error message
    assert "already" in result.stderr.lower() or "exists" in result.stderr.lower()


def test_org_init_creates_nested_path(cli_runner, tmp_path):
    """Should create nested directory structure if needed."""
    # Use a nested path that doesn't exist yet
    nested_path = tmp_path / "deeply" / "nested" / "org"

    result = cli_runner(
        ["--org-path", str(nested_path), "org", "init"],
        check=True,
    )

    # Should succeed and create the path
    assert result.returncode == 0
    assert nested_path.exists()
    assert (nested_path / "live" / "quinn.db").exists()


def test_org_init_creates_ceo_with_hiring_authority(initialized_org, cli_runner):
    """Should create CEO with full hiring authority."""
    # Verify CEO has hiring authority via status command
    result = cli_runner(
        ["--org-path", str(initialized_org), "org", "status"],
        check=True,
    )

    assert result.returncode == 0
    assert "CEO" in result.stdout
    assert "Authority" in result.stdout or "Full" in result.stdout
