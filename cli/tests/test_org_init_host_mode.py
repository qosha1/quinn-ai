"""Failing tests for `qn org init --host` (host-mode-init / quinn-ai-2vui).

Asserts the host-mode init contract:
- Org metadata lands under <project_root>/.quinnai/, NOT at project root.
- Project's existing .beads/ is reused; qn does NOT run `bd init` itself.
- Project root files (README.md, CLAUDE.md, AGENTS.md) are never written/clobbered.
- org_state row records project_root.
- .beads/hooks/pre-update is installed and executable.
- Auto-detect: if .beads/ or .git/ exists at --org-path and --host wasn't
  passed, host mode auto-enables (with a notice). --no-host opts back.

Tests fail with TypeError (host_mode kwarg not yet accepted) or
AssertionError (paths not created) until the impl lands.
"""
import sqlite3
import subprocess
import tempfile
from pathlib import Path

import pytest


def _seed_project(tmp: Path) -> Path:
    """Set up a minimal pre-existing project: .git/, .beads/, CLAUDE.md, README.md.

    Returns the project root path. Used by every host-mode init test.
    """
    project = tmp / "project"
    project.mkdir()
    (project / ".git").mkdir()  # marker only; not a real git repo
    (project / ".beads").mkdir()
    (project / ".beads" / "beads.db").touch()  # pre-existing tracker
    (project / "CLAUDE.md").write_text("# Project's own CLAUDE.md\n")
    (project / "README.md").write_text("# My Project\n")
    (project / "src").mkdir()
    (project / "src" / "main.py").write_text("# user code\n")
    return project


class TestHostModeLayout:
    """The directory layout under host mode."""

    def test_init_host_creates_dot_quinnai_subdir_only(self):
        from cli.core.org_init import initialize_org

        with tempfile.TemporaryDirectory() as tmp:
            project = _seed_project(Path(tmp))

            ok = initialize_org(
                org_path=project,
                org_name="Test Org",
                ceo_name="Alice",
                ceo_role="CEO",
                host_mode=True,
            )

            assert ok is True
            quinnai = project / ".quinnai"
            assert quinnai.is_dir()
            assert (quinnai / "config").is_dir()
            assert (quinnai / "live").is_dir()
            assert (quinnai / "live" / "quinn.db").exists()
            assert (quinnai / "storage").is_dir()
            assert (quinnai / "org-chart").is_dir()
            # Crucially: nothing at project root level beyond what we seeded.
            assert not (project / "config").exists()
            assert not (project / "live").exists()
            assert not (project / "storage").exists()

    def test_init_host_does_not_run_bd_init(self):
        """Project's existing .beads/ stays untouched. qn must not invoke bd init."""
        from cli.core.org_init import initialize_org

        with tempfile.TemporaryDirectory() as tmp:
            project = _seed_project(Path(tmp))
            beads_db = project / ".beads" / "beads.db"
            original_mtime = beads_db.stat().st_mtime
            (project / ".beads" / "marker.txt").write_text("project-owned")

            initialize_org(
                org_path=project,
                org_name="Test Org",
                ceo_name="Alice",
                ceo_role="CEO",
                host_mode=True,
            )

            # The pre-existing marker survives (proves no rm/replace happened).
            assert (project / ".beads" / "marker.txt").read_text() == "project-owned"
            # The .beads/ dir was NOT recreated/wiped.
            assert beads_db.exists()

    def test_init_host_does_not_render_root_readme_md(self):
        """Project's README.md is the user's. Host-mode init must never overwrite it."""
        from cli.core.org_init import initialize_org

        with tempfile.TemporaryDirectory() as tmp:
            project = _seed_project(Path(tmp))
            original = (project / "README.md").read_text()

            initialize_org(
                org_path=project,
                org_name="Test Org",
                ceo_name="Alice",
                ceo_role="CEO",
                host_mode=True,
            )

            assert (project / "README.md").read_text() == original

    def test_init_host_does_not_render_root_claude_md(self):
        from cli.core.org_init import initialize_org

        with tempfile.TemporaryDirectory() as tmp:
            project = _seed_project(Path(tmp))
            original = (project / "CLAUDE.md").read_text()

            initialize_org(
                org_path=project,
                org_name="Test Org",
                ceo_name="Alice",
                ceo_role="CEO",
                host_mode=True,
            )

            assert (project / "CLAUDE.md").read_text() == original
            # AGENTS.md must also not be created at project root.
            assert not (project / "AGENTS.md").exists()


class TestHostModeSchemaAndState:
    """org_state records project_root in host mode."""

    def test_init_host_records_project_root_in_org_state(self):
        from cli.core.org_init import initialize_org

        with tempfile.TemporaryDirectory() as tmp:
            project = _seed_project(Path(tmp))

            initialize_org(
                org_path=project,
                org_name="Test Org",
                ceo_name="Alice",
                ceo_role="CEO",
                host_mode=True,
            )

            db_path = project / ".quinnai" / "live" / "quinn.db"
            conn = sqlite3.connect(str(db_path))
            row = conn.execute(
                "SELECT project_root FROM org_state WHERE id='default'"
            ).fetchone()
            conn.close()

            assert row is not None
            assert row[0] == str(project)

    def test_init_greenfield_leaves_project_root_null(self):
        """Existing greenfield init flow keeps project_root null (back-compat)."""
        from cli.core.org_init import initialize_org

        with tempfile.TemporaryDirectory() as tmp:
            org_path = Path(tmp) / "greenfield-org"
            org_path.mkdir()

            initialize_org(
                org_path=org_path,
                org_name="Greenfield",
                ceo_name="Bob",
                ceo_role="CEO",
            )  # no host_mode kwarg → greenfield

            db_path = org_path / "live" / "quinn.db"
            conn = sqlite3.connect(str(db_path))
            row = conn.execute(
                "SELECT project_root FROM org_state WHERE id='default'"
            ).fetchone()
            conn.close()

            assert row is not None
            assert row[0] is None


class TestHostModeBdShim:
    """The bd PATH shim for the trust boundary (revised mechanism per
    architecture phase: bd has no per-action hook, so we use a $PATH
    shim at .quinnai/bin/bd instead of .beads/hooks/pre-update)."""

    def test_init_host_installs_bd_path_shim(self):
        from cli.core.org_init import initialize_org

        with tempfile.TemporaryDirectory() as tmp:
            project = _seed_project(Path(tmp))

            initialize_org(
                org_path=project,
                org_name="Test Org",
                ceo_name="Alice",
                ceo_role="CEO",
                host_mode=True,
            )

            shim = project / ".quinnai" / "bin" / "bd"
            assert shim.exists(), "bd PATH shim must be installed"
            assert shim.stat().st_mode & 0o111, "shim must be executable"
            content = shim.read_text()
            assert "QUINN_WORKER_ID" in content
            assert "assignee" in content.lower()


class TestHostModeAutoDetect:
    """qn org init auto-detects host mode when .beads/ or .git/ exists."""

    def test_auto_detect_when_beads_exists(self):
        """No --host flag, .beads/ exists → host mode auto-enables."""
        from cli.commands.main import qn
        from click.testing import CliRunner

        with tempfile.TemporaryDirectory() as tmp:
            project = _seed_project(Path(tmp))

            runner = CliRunner()
            result = runner.invoke(
                qn,
                [
                    "--org-path", str(project),
                    "org", "init",
                    "--ceo-name", "Alice",
                    "--skip-okrs",
                ],
                catch_exceptions=False,
            )

            assert result.exit_code == 0, result.output
            assert (project / ".quinnai").is_dir(), (
                "auto-detect should have laid out under .quinnai/"
            )
            assert "host mode" in result.output.lower(), (
                "auto-detect should print a notice"
            )

    def test_no_host_flag_forces_greenfield_even_with_beads(self):
        """--no-host opts back to greenfield even when markers are present."""
        from cli.commands.main import qn
        from click.testing import CliRunner

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "greenfield"
            target.mkdir()
            # Markers present at target — but --no-host overrides.
            (target / ".beads").mkdir()
            (target / ".beads" / "beads.db").touch()

            runner = CliRunner()
            result = runner.invoke(
                qn,
                [
                    "--org-path", str(target),
                    "org", "init",
                    "--ceo-name", "Alice",
                    "--skip-okrs",
                    "--no-host",
                ],
                catch_exceptions=False,
            )

            # Either succeeds with greenfield layout, or refuses cleanly
            # because .beads/ exists. Both are valid; the contract is just
            # that .quinnai/ is NOT created (host mode was suppressed).
            assert not (target / ".quinnai").exists()
