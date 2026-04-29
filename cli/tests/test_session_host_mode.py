"""Failing tests for session spawn behavior in host mode (host-mode-init / quinn-ai-2vui).

When the org is in host mode (org_state.project_root is set):
  - SessionConfig.working_directory must be the project_root, not the
    worker's storage dir. Workers need cwd at the project root so their
    bd/edit/test commands operate on the project.
  - $WORKER_STORAGE env var must point at the absolute path of the
    worker's private dir under .quinnai/storage/workers/<hierarchy>/.
  - $QUINN_WORKER_ID must remain set (existing plumbing, not regressed).

In greenfield mode the existing behavior is preserved (cwd = worker's
storage dir).
"""
import sqlite3
import tempfile
from pathlib import Path

import pytest


def _setup_host_mode_org(tmp: Path) -> Path:
    """Initialize a host-mode org under tmp/project/.quinnai/ and return project."""
    from cli.core.org_init import initialize_org

    project = tmp / "project"
    project.mkdir()
    (project / ".git").mkdir()
    (project / ".beads").mkdir()
    (project / ".beads" / "beads.db").touch()

    initialize_org(
        org_path=project,
        org_name="Host Org",
        ceo_name="Alice",
        ceo_role="CEO",
        host_mode=True,
    )
    return project


class TestHostModeSessionPlumbing:
    """Session spawn config in host mode."""

    def test_session_spawn_uses_project_root_cwd_in_host_mode(self):
        """SessionConfig.working_directory must be project_root, not worker storage."""
        from cli.core.onboarding import get_worker_session_working_directory

        with tempfile.TemporaryDirectory() as tmp:
            project = _setup_host_mode_org(Path(tmp))

            # Resolve the CEO worker's spawn cwd in this org.
            cwd = get_worker_session_working_directory(
                org_path=project / ".quinnai",
                worker_id="ceo",
            )

            assert Path(cwd) == project, (
                f"host-mode worker cwd must be project root, got {cwd}"
            )

    def test_session_spawn_sets_worker_storage_env_to_quinnai_subdir(self):
        """$WORKER_STORAGE points at .quinnai/storage/workers/<hierarchy>/ (absolute)."""
        from cli.core.onboarding import get_worker_env_vars_for_worker

        with tempfile.TemporaryDirectory() as tmp:
            project = _setup_host_mode_org(Path(tmp))

            env = get_worker_env_vars_for_worker(
                org_path=project / ".quinnai",
                worker_id="ceo",
            )

            ws = env["WORKER_STORAGE"]
            ws_path = Path(ws)
            # Absolute path
            assert ws_path.is_absolute()
            # Lives under .quinnai/storage/workers/, NOT the project root
            assert ".quinnai" in ws_path.parts
            assert "storage" in ws_path.parts
            assert "workers" in ws_path.parts
            # And distinct from cwd
            assert ws_path != project

    def test_session_spawn_keeps_quinn_worker_id_env(self):
        """Existing $QUINN_WORKER_ID plumbing must continue to work in host mode."""
        from cli.core.onboarding import get_worker_env_vars_for_worker

        with tempfile.TemporaryDirectory() as tmp:
            project = _setup_host_mode_org(Path(tmp))

            env = get_worker_env_vars_for_worker(
                org_path=project / ".quinnai",
                worker_id="wrkr-deadbeef",
            )

            assert env.get("QUINN_WORKER_ID") == "wrkr-deadbeef"


class TestGreenfieldSessionPlumbingPreserved:
    """Sanity: existing greenfield behavior is unchanged."""

    def test_greenfield_session_spawn_uses_worker_storage_cwd(self):
        """In greenfield mode, cwd remains the worker's storage dir (existing behavior)."""
        from cli.core.org_init import initialize_org
        from cli.core.onboarding import get_worker_session_working_directory

        with tempfile.TemporaryDirectory() as tmp:
            org_path = Path(tmp) / "greenfield"
            org_path.mkdir()
            initialize_org(
                org_path=org_path,
                org_name="Greenfield",
                ceo_name="Bob",
                ceo_role="CEO",
            )  # no host_mode kwarg

            cwd = get_worker_session_working_directory(
                org_path=org_path,
                worker_id="ceo",
            )

            # Greenfield: cwd is the worker's private storage dir,
            # somewhere under org_path/storage/workers/.
            cwd_path = Path(cwd)
            assert cwd_path != org_path  # not project root style
            assert "storage" in cwd_path.parts
            assert "workers" in cwd_path.parts
