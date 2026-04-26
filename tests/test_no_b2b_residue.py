"""Structural guardrail: repo contains no residue from the upstream B2B SaaS template.

CLAUDE.md declares QuinnAI as a Python CLI tool, not a Django/NextJS B2B SaaS.
This test fails until that invariant holds on disk.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


DELETED_DIRS = [
    "backend",
    "app",
    "landing",
    "e2e",
    "compose",
    ".envs",
    "openspec/changes",
]

DELETED_ROOT_FILES = [
    "docker-compose.local.yml",
    "docker-compose.production.yml",
    "DEPLOYMENT.md",
    "DOCKER.md",
    "release-notes/TEMPLATE.md",
]

DELETED_TEST_FILES = [
    "tests/test_auth_teams.py",
    "tests/test_backend.py",
    "tests/test_billing.py",
    "tests/test_frontend_app.py",
    "tests/test_landing_page.py",
    "tests/test_infrastructure.py",
]

DELETED_SCRIPTS = [
    "scripts/verify-setup.sh",
]


@pytest.mark.parametrize("relpath", DELETED_DIRS)
def test_b2b_directory_absent(relpath: str) -> None:
    path = ROOT / relpath
    assert not path.exists(), f"{relpath}/ should be removed but still exists"


@pytest.mark.parametrize("relpath", DELETED_ROOT_FILES + DELETED_TEST_FILES + DELETED_SCRIPTS)
def test_b2b_file_absent(relpath: str) -> None:
    path = ROOT / relpath
    assert not path.exists(), f"{relpath} should be removed but still exists"


def test_makefile_has_no_template_targets() -> None:
    makefile = (ROOT / "Makefile").read_text()
    forbidden = ["template-fetch", "template-diff", "template-merge", "template-cherry"]
    found = [t for t in forbidden if t in makefile]
    assert not found, f"Makefile still contains B2B template-sync targets: {found}"


def test_version_matches_pyproject() -> None:
    version_file = (ROOT / "VERSION").read_text().strip()

    pyproject = (ROOT / "pyproject.toml").read_text()
    pyproject_version = None
    for line in pyproject.splitlines():
        line = line.strip()
        if line.startswith("version") and "=" in line:
            pyproject_version = line.split("=", 1)[1].strip().strip('"').strip("'")
            break

    assert pyproject_version is not None, "pyproject.toml has no [project].version"
    assert version_file == pyproject_version, (
        f"VERSION ({version_file}) != pyproject.toml version ({pyproject_version})"
    )
