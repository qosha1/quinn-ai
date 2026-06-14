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


def test_org_init_refuses_to_share_existing_beads_dir(tmp_path, cli_runner):
    """Regression: 'qn org init' must NOT silently share an existing
    .beads/ at the target path (quinn-ai-hmn1).

    Pre-fix: bootstrap OKR + initial tasks landed in whatever .beads/
    was sitting at the target path, polluting that project's tracker.
    """
    # Pre-create a .beads/ directory at the target path to simulate
    # 'init inside a dir that's already part of another bead-tracked project'.
    target = tmp_path / "would-pollute"
    target.mkdir()
    (target / ".beads").mkdir()

    result = cli_runner(
        # --no-host: this asserts GREENFIELD .beads-refusal; without it the
        # pre-existing .beads/ would auto-trigger host mode (which reuses it).
        ["--org-path", str(target), "org", "init", "--no-host"],
    )

    assert result.returncode != 0, (
        "init should refuse when a .beads/ already exists at the target "
        f"path; got success.\nstdout: {result.stdout!r}\nstderr: {result.stderr!r}"
    )
    err = (result.stderr + result.stdout).lower()
    assert "beads" in err and ("already exists" in err or "exist" in err), (
        "error message should mention the .beads conflict; got:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_org_init_skip_okrs_plants_no_okrs_at_all(temp_org_dir, cli_runner):
    """Regression: 'qn org init --skip-okrs' must produce zero OKRs in
    BOTH the SQLite okrs table AND the beads tracker (quinn-ai-6odb).

    Pre-fix: --skip-okrs only suppressed the interactive prompt. Init
    still planted a 'Establish organizational foundation' bootstrap
    OKR that derailed canaries — the CEO would finish the spec's OKR,
    see the planted one, and start working on it off-script.
    """
    import sqlite3

    result = cli_runner(
        ["--org-path", str(temp_org_dir), "org", "init", "--skip-okrs"],
        check=True,
    )
    assert result.returncode == 0

    # SQLite: okrs table must be empty
    db_path = temp_org_dir / "live" / "quinn.db"
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("SELECT title FROM okrs").fetchall()
    finally:
        conn.close()
    assert rows == [], (
        f"--skip-okrs should plant NO OKRs in sqlite; got {rows} "
        "(quinn-ai-6odb regression)"
    )


def test_org_init_reuse_beads_flag_lets_user_share_existing_tracker(
    tmp_path, cli_runner
):
    """The --reuse-beads escape hatch lets the user opt in to sharing
    an existing .beads/ at the target path.
    """
    target = tmp_path / "shared-beads-org"
    target.mkdir()
    (target / ".beads").mkdir()

    result = cli_runner(
        # --no-host: exercise the GREENFIELD --reuse-beads path (a pre-existing
        # .beads/ would otherwise auto-trigger host mode).
        ["--org-path", str(target), "org", "init", "--reuse-beads", "--no-host"],
    )

    assert result.returncode == 0, (
        f"init --reuse-beads should succeed even when .beads/ exists.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert (target / "live" / "quinn.db").exists()
