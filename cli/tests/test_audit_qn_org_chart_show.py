"""Audit tests for `qn org chart show` (bead quinn-ai-ikz).

Verifies the org-chart tree rendering reads from org-chart/current.yaml
and displays workers in hierarchical order with name, role, lifecycle status.
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
            "--ceo-name", "Alice",
            "--skip-okrs",
        ])
        assert result.exit_code == 0, f"setup init failed: {result.output}"
        yield org_path


def test_chart_show_renders_header_and_ceo(runner, initialized_org):
    result = runner.invoke(qn, ["--org-path", str(initialized_org), "org", "chart", "show"])
    assert result.exit_code == 0, result.output
    assert "Organization Structure:" in result.output
    assert "Alice" in result.output
    assert "CEO" in result.output


def test_chart_show_includes_lifecycle_status(runner, initialized_org):
    """Each worker should render with their lifecycle status (e.g. 'pending')."""
    result = runner.invoke(qn, ["--org-path", str(initialized_org), "org", "chart", "show"])
    assert result.exit_code == 0
    # Default CEO post-init has lifecycle 'pending'
    assert "pending" in result.output, (
        f"Expected lifecycle status in output. Got:\n{result.output}"
    )


def test_chart_show_fails_cleanly_when_org_chart_missing(runner):
    """If org-chart/current.yaml is missing, should error cleanly with guidance."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = runner.invoke(qn, ["--org-path", tmpdir, "org", "chart", "show"])
        assert result.exit_code != 0, (
            f"Should fail without an init. Output:\n{result.output}"
        )
        assert "Org-chart not found" in result.output
        assert "qn org init" in result.output


def test_chart_show_renders_hierarchy_after_hire(runner, initialized_org):
    """Hiring a worker should add them under their manager in the chart."""
    # Find CEO id from org chart yaml directly
    import yaml
    chart = yaml.safe_load((initialized_org / "org-chart" / "current.yaml").read_text())
    ceo_id = chart["hierarchy"]["root"]

    hire = runner.invoke(qn, [
        "--org-path", str(initialized_org),
        "org", "hire",
        "--name", "Bob",
        "--role", "engineer",
        "--manager", ceo_id,
        "--cost", "50",
    ])
    assert hire.exit_code == 0, f"hire failed: {hire.output}"

    result = runner.invoke(qn, ["--org-path", str(initialized_org), "org", "chart", "show"])
    assert result.exit_code == 0, result.output
    assert "Alice" in result.output
    assert "Bob" in result.output
    assert "engineer" in result.output
    # Bob should appear under Alice — verify Bob's line comes after Alice's
    alice_idx = result.output.index("Alice")
    bob_idx = result.output.index("Bob")
    assert alice_idx < bob_idx, "CEO must render before subordinates"
