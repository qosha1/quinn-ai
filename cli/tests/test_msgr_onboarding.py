"""Tests for msgr integration with worker onboarding."""

import subprocess
import sys
from pathlib import Path
import pytest

from core.db import open_database, get_org_db_path
from core.onboarding import get_worker_env_vars, load_onboarding_context
from core.org_init import OrgInitConfig, init_org
from core.queries import get_worker_by_name


def test_msgr_command_available():
    """Test that msgr can be invoked as a Python module."""
    # Test msgr --help works via python -m
    result = subprocess.run(
        [sys.executable, "-m", "msgr.main", "--help"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "msgr - QuinnAI messaging CLI" in result.stdout
    assert "inbox" in result.stdout
    assert "send" in result.stdout
    assert "channels" in result.stdout


def _init_org(org_path: Path) -> None:
    """Initialize an organization for tests."""
    config = OrgInitConfig(path=org_path, name=org_path.name, ceo_name="CEO", ceo_role="CEO")
    result = init_org(config)
    assert result.success, result.error


def test_msgr_environment_variables_set(tmp_path: Path):
    """Test that worker environment includes variables msgr needs."""
    org_path = tmp_path / "test-org"
    org_path.mkdir()

    _init_org(org_path)

    # Get CEO worker
    db = open_database(get_org_db_path(org_path))
    try:
        ceo = get_worker_by_name(db, "ceo")
        assert ceo is not None

        # Load onboarding context
        ctx = load_onboarding_context(db, ceo.id, org_path)
        env_vars = get_worker_env_vars(ctx, org_path, db)

        # Verify msgr required environment variables are set
        assert "QUINN_WORKER_ID" in env_vars
        assert "QUINN_ORG_PATH" in env_vars
        assert env_vars["QUINN_WORKER_ID"] == ceo.id
        assert env_vars["QUINN_ORG_PATH"] == str(org_path)

        # These are the environment variables msgr uses
        assert "WORKER_ID" in env_vars
        assert "ORG_PATH" in env_vars

    finally:
        db.close()


def test_msgr_works_with_worker_environment(tmp_path: Path):
    """Test that msgr can be called with worker environment variables."""
    org_path = tmp_path / "test-org"
    org_path.mkdir()

    _init_org(org_path)

    # Get CEO worker
    db = open_database(get_org_db_path(org_path))
    try:
        ceo = get_worker_by_name(db, "ceo")
        assert ceo is not None

        # Load onboarding environment
        ctx = load_onboarding_context(db, ceo.id, org_path)
        env_vars = get_worker_env_vars(ctx, org_path, db)

        # Test msgr with worker environment
        # Note: This would fail without QUINN_WORKER_ID if not using --help
        env = {
            **dict(subprocess.os.environ),  # Include current environment
            **env_vars,  # Add worker environment variables
        }

        result = subprocess.run(
            [sys.executable, "-m", "msgr.main", "--help"],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 0
        assert "msgr - QuinnAI messaging CLI" in result.stdout

    finally:
        db.close()
