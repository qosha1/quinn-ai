"""Tests for HealthStatusWidget display logic."""
import pytest

from board_ui.app import BoardApp
from board_ui.config import BoardConfig
from board_ui.widgets.health_status import HealthStatusWidget
from board_ui.interfaces.org_connection import HealthStatus, HealthIssue

from textual.widgets import Label


def _label_text(label: Label) -> str:
    """Extract text content from a Textual Label widget."""
    return str(label._Static__content)


@pytest.mark.asyncio
async def test_healthy_no_issues_shows_clean_message():
    """When healthy with 0 workers with issues, show clean 'Healthy' message."""
    app = BoardApp(BoardConfig(org_paths=[]))
    async with app.run_test() as pilot:
        health_widget = app.query_one("#health-widget", HealthStatusWidget)
        health = HealthStatus(
            overall_score="healthy",
            workers_with_issues=0,
            total_workers=3,
            issues=[],
        )
        health_widget.update_health(health)
        await pilot.pause()

        score_label = health_widget.query_one("#health-score", Label)
        label_text = _label_text(score_label)

        assert "issues" not in label_text.lower(), (
            f"Healthy org with 0 issues should not mention 'issues', got: {label_text!r}"
        )
        assert "Healthy" in label_text, f"Expected 'Healthy' in label, got: {label_text!r}"


@pytest.mark.asyncio
async def test_healthy_with_notes_shows_notes_not_issues():
    """When healthy but some workers have info-level notes, say 'notes' not 'issues'."""
    app = BoardApp(BoardConfig(org_paths=[]))
    async with app.run_test() as pilot:
        health_widget = app.query_one("#health-widget", HealthStatusWidget)
        health = HealthStatus(
            overall_score="healthy",
            workers_with_issues=1,
            total_workers=3,
            issues=[
                HealthIssue(
                    worker_id="w1",
                    worker_name="Engineer",
                    issue_type="no_activity",
                    severity="info",
                    message="No recent activity",
                )
            ],
        )
        health_widget.update_health(health)
        await pilot.pause()

        score_label = health_widget.query_one("#health-score", Label)
        label_text = _label_text(score_label)

        assert "issues" not in label_text.lower(), (
            f"Healthy org should not say 'issues', got: {label_text!r}"
        )
        assert "notes" in label_text.lower(), (
            f"Healthy org with info items should say 'notes', got: {label_text!r}"
        )
        assert "1" in label_text, f"Should show worker count, got: {label_text!r}"


@pytest.mark.asyncio
async def test_warning_shows_issues_count():
    """When warning, show '(N/N workers with issues)'."""
    app = BoardApp(BoardConfig(org_paths=[]))
    async with app.run_test() as pilot:
        health_widget = app.query_one("#health-widget", HealthStatusWidget)
        health = HealthStatus(
            overall_score="warning",
            workers_with_issues=2,
            total_workers=4,
            issues=[
                HealthIssue(
                    worker_id="w1",
                    worker_name="Engineer",
                    issue_type="no_okrs",
                    severity="warning",
                    message="No OKRs assigned",
                )
            ],
        )
        health_widget.update_health(health)
        await pilot.pause()

        score_label = health_widget.query_one("#health-score", Label)
        label_text = _label_text(score_label)

        assert "issues" in label_text.lower(), (
            f"Warning org should mention 'issues', got: {label_text!r}"
        )
        assert "2" in label_text and "4" in label_text, (
            f"Warning org should show 2/4 counts, got: {label_text!r}"
        )


@pytest.mark.asyncio
async def test_critical_shows_issues_count():
    """When critical, show '(N/N workers with issues)'."""
    app = BoardApp(BoardConfig(org_paths=[]))
    async with app.run_test() as pilot:
        health_widget = app.query_one("#health-widget", HealthStatusWidget)
        health = HealthStatus(
            overall_score="critical",
            workers_with_issues=3,
            total_workers=3,
            issues=[
                HealthIssue(
                    worker_id="w1",
                    worker_name="Engineer",
                    issue_type="crashed_session",
                    severity="error",
                    message="Session crashed",
                )
            ],
        )
        health_widget.update_health(health)
        await pilot.pause()

        score_label = health_widget.query_one("#health-score", Label)
        label_text = _label_text(score_label)

        assert "issues" in label_text.lower(), (
            f"Critical org should mention 'issues', got: {label_text!r}"
        )
        assert "3" in label_text, f"Critical org should show 3/3 counts, got: {label_text!r}"


@pytest.mark.asyncio
async def test_healthy_score_label_gets_healthy_class():
    """When healthy, score label should have health-healthy class applied."""
    app = BoardApp(BoardConfig(org_paths=[]))
    async with app.run_test() as pilot:
        health_widget = app.query_one("#health-widget", HealthStatusWidget)
        health = HealthStatus(
            overall_score="healthy",
            workers_with_issues=0,
            total_workers=2,
            issues=[],
        )
        health_widget.update_health(health)
        await pilot.pause()

        score_label = health_widget.query_one("#health-score", Label)
        assert "health-healthy" in score_label.classes, (
            f"Healthy status should add 'health-healthy' class, got classes: {score_label.classes}"
        )
