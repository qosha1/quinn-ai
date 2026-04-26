"""Audit tests for `qn org status` (bead quinn-ai-c74).

Existing tests in test_cli.py cover the trivial 'runs / requires init' cases.
Audit gaps:
- Output reflects --ceo-name correctly
- Output reports the actual org lifecycle state
- 'Authority' line renders when CEO has scope
- Counters (Total / Active / Sessions / Managers) all surface
"""

import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from cli.commands.main import qn


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def initialized_org():
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir)
        runner = CliRunner()
        result = runner.invoke(qn, [
            "--org-path", str(org_path),
            "org", "init",
            "--ceo-name", "AuditCEO",
            "--skip-okrs",
        ])
        assert result.exit_code == 0, f"setup init failed: {result.output}"
        yield org_path


def test_status_shows_org_path_and_state(runner, initialized_org):
    result = runner.invoke(qn, ["--org-path", str(initialized_org), "org", "status"])
    assert result.exit_code == 0, result.output
    assert f"Organization: {initialized_org}" in result.output
    assert "Status: initialized" in result.output


def test_status_shows_ceo_name_from_init(runner, initialized_org):
    result = runner.invoke(qn, ["--org-path", str(initialized_org), "org", "status"])
    assert result.exit_code == 0, result.output
    assert "AuditCEO" in result.output, (
        f"Expected --ceo-name to appear in status output. Got:\n{result.output}"
    )


def test_status_shows_worker_section(runner, initialized_org):
    result = runner.invoke(qn, ["--org-path", str(initialized_org), "org", "status"])
    assert result.exit_code == 0
    # All four counters must appear
    assert "Workers:" in result.output
    assert "Total: 1" in result.output, f"Expected Total: 1 (just CEO). Got:\n{result.output}"
    assert "Active: 0" in result.output
    assert "Sessions: 0" in result.output


def test_status_shows_ceo_block_with_authority(runner, initialized_org):
    result = runner.invoke(qn, ["--org-path", str(initialized_org), "org", "status"])
    assert result.exit_code == 0
    assert "CEO:" in result.output
    assert "Role: CEO" in result.output
    assert "Lifecycle:" in result.output
    # CEO ships with full authority by default
    assert "Authority: Full (all roles)" in result.output, (
        f"CEO should have full authority by default. Output:\n{result.output}"
    )


def test_status_reflects_running_state_after_start(runner, initialized_org):
    """Status must update when the org transitions to running."""
    start = runner.invoke(qn, [
        "--org-path", str(initialized_org),
        "org", "start", "--no-spawn-ceo", "--skip-config-validation",
    ])
    assert start.exit_code == 0, start.output

    result = runner.invoke(qn, ["--org-path", str(initialized_org), "org", "status"])
    assert result.exit_code == 0, result.output
    assert "Status: running" in result.output, (
        f"After start, status should be running. Got:\n{result.output}"
    )
