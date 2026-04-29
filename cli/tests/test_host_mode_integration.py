"""Failing end-to-end integration tests for `qn org init --host`
(host-mode-init / quinn-ai-y0pv).

These exercise the full CLI flow against a real temp project with .git/
and a real bd-initialized .beads/. They catch wiring gaps that unit tests
miss: CLI plumbing, file-system-level effects, and the bd hook actually
firing under a real `bd close` invocation.

Will fail until Phase 4 implementation lands. Skipped if `bd` binary not
on PATH (live integration only).
"""
import hashlib
import os
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path

import pytest


def _has_bd() -> bool:
    return shutil.which("bd") is not None


def _hash_dir(path: Path) -> str:
    """Recursive hash of a directory's file contents — used to assert
    .beads/ is byte-for-byte unchanged after host-mode init."""
    h = hashlib.sha256()
    for p in sorted(path.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(path)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


@pytest.fixture
def project_with_beads():
    """A real project tree: git-style markers, bd-initialized .beads/, user files."""
    if not _has_bd():
        pytest.skip("bd binary not on PATH")

    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp) / "project"
        project.mkdir()

        # git marker (we don't need a real git repo for these tests)
        (project / ".git").mkdir()

        # User project files
        (project / "CLAUDE.md").write_text("# Project's own conventions\n")
        (project / "README.md").write_text("# My Project\n")
        (project / "src").mkdir()
        (project / "src" / "main.py").write_text("def hello(): return 'world'\n")

        # Real bd init in the project. --skip-hooks so the seed dir is clean.
        env = {**os.environ, "BEADS_SKIP_IDENTITY_CHECK": "1"}
        result = subprocess.run(
            ["bd", "init", "--skip-hooks", "--quiet"],
            cwd=project,
            env=env,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            pytest.skip(f"bd init failed: {result.stderr}")

        yield project


class TestFullInitHostModeE2E:
    """End-to-end host-mode init against a real seeded project."""

    def test_full_init_host_mode_creates_quinnai_layout_only(self, project_with_beads):
        """qn org init --host inside an existing project: .quinnai/ gets the
        org metadata; nothing else at project root is created or modified."""
        from cli.commands.main import qn
        from click.testing import CliRunner

        beads_hash_before = _hash_dir(project_with_beads / ".beads")
        claude_before = (project_with_beads / "CLAUDE.md").read_text()
        readme_before = (project_with_beads / "README.md").read_text()
        main_before = (project_with_beads / "src" / "main.py").read_text()

        runner = CliRunner()
        result = runner.invoke(
            qn,
            [
                "--org-path", str(project_with_beads),
                "org", "init",
                "--ceo-name", "Alice",
                "--skip-okrs",
                "--host",
            ],
            catch_exceptions=False,
        )

        assert result.exit_code == 0, result.output

        quinnai = project_with_beads / ".quinnai"
        assert quinnai.is_dir()
        assert (quinnai / "live" / "quinn.db").exists()
        assert (quinnai / "config").is_dir()
        assert (quinnai / "storage").is_dir()
        assert (quinnai / "org-chart").is_dir()

        # User files: untouched.
        assert (project_with_beads / "CLAUDE.md").read_text() == claude_before
        assert (project_with_beads / "README.md").read_text() == readme_before
        assert (project_with_beads / "src" / "main.py").read_text() == main_before

        # The trust-boundary mechanism is the .quinnai/bin/bd PATH shim
        # (revised from the original .beads/hooks/pre-update plan because
        # bd has no per-action hook system).
        shim = project_with_beads / ".quinnai" / "bin" / "bd"
        assert shim.exists() and shim.is_file(), (
            "host-mode init must install the bd PATH shim at .quinnai/bin/bd"
        )
        assert shim.stat().st_mode & 0o111, "shim must be executable"

    def test_org_state_records_project_root(self, project_with_beads):
        """After init, org_state.project_root == the project path."""
        from cli.commands.main import qn
        from click.testing import CliRunner

        runner = CliRunner()
        runner.invoke(
            qn,
            [
                "--org-path", str(project_with_beads),
                "org", "init",
                "--ceo-name", "Alice",
                "--skip-okrs",
                "--host",
            ],
            catch_exceptions=False,
        )

        db = sqlite3.connect(str(project_with_beads / ".quinnai" / "live" / "quinn.db"))
        row = db.execute(
            "SELECT project_root FROM org_state WHERE id='default'"
        ).fetchone()
        db.close()

        assert row is not None
        assert Path(row[0]) == project_with_beads


class TestBdHookE2E:
    """The pre-update hook fires under real `bd close` invocations."""

    def test_pre_update_hook_blocks_worker_closing_human_bead(self, project_with_beads):
        """Pre-seed a bead assigned to a human; spawning a worker context
        (QUINN_WORKER_ID env) and running `bd close` must refuse."""
        from cli.commands.main import qn
        from click.testing import CliRunner

        # Seed a human-assigned bead BEFORE init (real project state).
        env = {**os.environ, "BEADS_SKIP_IDENTITY_CHECK": "1"}
        create_result = subprocess.run(
            [
                "bd", "create",
                "--title", "Human's existing P1",
                "--type", "task",
                "--priority", "1",
                "--assignee", "alice@example.com",
                "--description", "pre-existing user work",
            ],
            cwd=project_with_beads,
            env=env,
            capture_output=True,
            text=True,
        )
        assert create_result.returncode == 0, create_result.stderr
        # Parse 'Created issue: <id>' from output
        bead_id = None
        for line in create_result.stdout.splitlines():
            if "Created issue:" in line:
                bead_id = line.split("Created issue:", 1)[1].strip().split()[0]
                break
        assert bead_id, f"could not parse bead id from {create_result.stdout!r}"

        # Init host mode (installs the hook).
        runner = CliRunner()
        runner.invoke(
            qn,
            [
                "--org-path", str(project_with_beads),
                "org", "init",
                "--ceo-name", "Alice",
                "--skip-okrs",
                "--host",
            ],
            catch_exceptions=False,
        )

        # Now invoke `bd close` as a worker — must go through the shim.
        # In production, worker session spawn prepends .quinnai/bin/ to
        # PATH; we mirror that here so the shim intercepts.
        shim_dir = project_with_beads / ".quinnai" / "bin"
        worker_env = {
            **os.environ,
            "BEADS_SKIP_IDENTITY_CHECK": "1",
            "QUINN_WORKER_ID": "wrkr-evil-bot",
            "PATH": f"{shim_dir}:{os.environ.get('PATH', '')}",
        }
        close_result = subprocess.run(
            ["bd", "close", bead_id, "--reason", "stealing this"],
            cwd=project_with_beads,
            env=worker_env,
            capture_output=True,
            text=True,
        )

        assert close_result.returncode != 0, (
            f"hook should have blocked the close, but it succeeded:\n"
            f"stdout={close_result.stdout}\nstderr={close_result.stderr}"
        )
        assert "wrkr-evil-bot" in close_result.stderr or "cannot" in close_result.stderr.lower()

    def test_pre_update_hook_allows_human_close(self, project_with_beads):
        """Same setup but no QUINN_WORKER_ID — humans bypass the hook."""
        from cli.commands.main import qn
        from click.testing import CliRunner

        env = {**os.environ, "BEADS_SKIP_IDENTITY_CHECK": "1"}
        create_result = subprocess.run(
            [
                "bd", "create",
                "--title", "Human's bead",
                "--type", "task",
                "--priority", "2",
                "--assignee", "alice@example.com",
            ],
            cwd=project_with_beads,
            env=env,
            capture_output=True,
            text=True,
        )
        bead_id = None
        for line in create_result.stdout.splitlines():
            if "Created issue:" in line:
                bead_id = line.split("Created issue:", 1)[1].strip().split()[0]
                break

        runner = CliRunner()
        runner.invoke(
            qn,
            [
                "--org-path", str(project_with_beads),
                "org", "init",
                "--ceo-name", "Alice",
                "--skip-okrs",
                "--host",
            ],
            catch_exceptions=False,
        )

        # Human (no QUINN_WORKER_ID) closes their own bead.
        human_env = {k: v for k, v in os.environ.items() if k != "QUINN_WORKER_ID"}
        human_env["BEADS_SKIP_IDENTITY_CHECK"] = "1"
        close_result = subprocess.run(
            ["bd", "close", bead_id, "--reason", "done"],
            cwd=project_with_beads,
            env=human_env,
            capture_output=True,
            text=True,
        )

        assert close_result.returncode == 0, (
            f"human close should succeed, got rc={close_result.returncode}\n"
            f"stderr={close_result.stderr}"
        )
