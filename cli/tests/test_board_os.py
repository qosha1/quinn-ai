"""
Tests for Board OS feature — worker detail panel + session attach.

All tests must FAIL until implementation exists.
"""

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# WorkerDetail dataclass
# ---------------------------------------------------------------------------

def test_worker_detail_dataclass_exists() -> None:
    from board_ui.interfaces.org_connection import WorkerDetail

    detail = WorkerDetail(
        worker_id="wrkr-123",
        tools=[],
        storage_tree={},
        active_beads=[],
        recent_messages=[],
        briefing_excerpt="",
    )
    assert detail.worker_id == "wrkr-123"


def test_worker_detail_has_all_required_fields() -> None:
    from board_ui.interfaces.org_connection import WorkerDetail

    detail = WorkerDetail(
        worker_id="wrkr-123",
        tools=[{"name": "rc", "description": "Remote compose"}],
        storage_tree={"BRIEFING.md": None, "work": {}},
        active_beads=[{"id": "bead-1", "title": "Do thing", "status": "in_progress"}],
        recent_messages=[{"sender": "Cleo", "body": "Hi", "ts": "10:00"}],
        briefing_excerpt="You are the CEO.",
    )
    assert len(detail.tools) == 1
    assert detail.tools[0]["name"] == "rc"
    assert "BRIEFING.md" in detail.storage_tree
    assert len(detail.active_beads) == 1
    assert len(detail.recent_messages) == 1
    assert "CEO" in detail.briefing_excerpt


# ---------------------------------------------------------------------------
# OrgConnection interface — get_worker_detail
# ---------------------------------------------------------------------------

def test_org_connection_interface_has_get_worker_detail() -> None:
    from board_ui.interfaces.org_connection import OrgConnection
    import inspect

    assert hasattr(OrgConnection, "get_worker_detail"), (
        "OrgConnection must declare get_worker_detail(worker_id) -> WorkerDetail | None"
    )
    sig = inspect.signature(OrgConnection.get_worker_detail)
    assert "worker_id" in sig.parameters


# ---------------------------------------------------------------------------
# WorkerDetailReader — reads tools from org config
# ---------------------------------------------------------------------------

def test_worker_detail_reader_loads_org_tools(tmp_path: Path) -> None:
    from board_ui.services.readers.worker_detail import WorkerDetailReader

    # Write tools.yaml
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "tools.yaml").write_text(
        "tools:\n  - name: rc\n    description: Remote compose\n"
    )

    reader = WorkerDetailReader(db=MagicMock(), org_path=tmp_path)
    detail = reader.get_worker_detail("wrkr-123")
    assert any(t["name"] == "rc" for t in detail.tools)


def test_worker_detail_reader_empty_tools_when_no_yaml(tmp_path: Path) -> None:
    from board_ui.services.readers.worker_detail import WorkerDetailReader

    (tmp_path / "config").mkdir()
    reader = WorkerDetailReader(db=MagicMock(), org_path=tmp_path)
    detail = reader.get_worker_detail("wrkr-123")
    assert detail.tools == []


def test_worker_detail_reader_loads_briefing_excerpt(tmp_path: Path) -> None:
    from board_ui.services.readers.worker_detail import WorkerDetailReader

    (tmp_path / "config").mkdir()
    # Set up a minimal storage structure
    worker_storage = tmp_path / "storage" / "workers" / "ceo" / "wrkr-123"
    worker_storage.mkdir(parents=True)
    (worker_storage / "BRIEFING.md").write_text(
        "# CEO Briefing\nYou are the CEO.\nMore content here.\n" * 5
    )

    mock_db = MagicMock()
    mock_db.fetchone.return_value = {"id": "wrkr-123", "role": "CEO", "manager_id": None}

    reader = WorkerDetailReader(db=mock_db, org_path=tmp_path)
    detail = reader.get_worker_detail("wrkr-123")
    assert "CEO" in detail.briefing_excerpt
    # Excerpt should be limited (not the whole file)
    assert len(detail.briefing_excerpt) < 2000


def test_worker_detail_reader_builds_storage_tree(tmp_path: Path) -> None:
    from board_ui.services.readers.worker_detail import WorkerDetailReader

    (tmp_path / "config").mkdir()
    worker_storage = tmp_path / "storage" / "workers" / "ceo" / "wrkr-123"
    worker_storage.mkdir(parents=True)
    (worker_storage / "BRIEFING.md").write_text("briefing")
    (worker_storage / "work").mkdir()
    (worker_storage / "work" / "notes.md").write_text("notes")

    mock_db = MagicMock()
    mock_db.fetchone.return_value = {"id": "wrkr-123", "role": "CEO", "manager_id": None}

    reader = WorkerDetailReader(db=mock_db, org_path=tmp_path)
    detail = reader.get_worker_detail("wrkr-123")
    assert isinstance(detail.storage_tree, dict)
    assert "BRIEFING.md" in detail.storage_tree


# ---------------------------------------------------------------------------
# Session attach — suspend + tmux attach pattern
# ---------------------------------------------------------------------------

def test_session_attach_helper_exists() -> None:
    from board_ui.services.session_attach import attach_to_worker_session

    assert callable(attach_to_worker_session)


def test_session_attach_calls_tmux_attach(tmp_path: Path) -> None:
    from board_ui.services.session_attach import attach_to_worker_session

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        attach_to_worker_session("qn-worker-abc123")

    mock_run.assert_called_once()
    call_args = mock_run.call_args[0][0]
    assert "tmux" in call_args
    assert "attach-session" in call_args
    assert "qn-worker-abc123" in call_args


def test_session_attach_returns_false_when_no_session() -> None:
    from board_ui.services.session_attach import attach_to_worker_session

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1)
        result = attach_to_worker_session("nonexistent-session")

    assert result is False


def test_session_attach_returns_true_on_success() -> None:
    from board_ui.services.session_attach import attach_to_worker_session

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = attach_to_worker_session("qn-worker-abc123")

    assert result is True


# ---------------------------------------------------------------------------
# TeamView layout — worker selection drives detail panel
# ---------------------------------------------------------------------------

def test_team_view_has_attach_key_binding() -> None:
    """TeamView must have 'a' key bound to attach action."""
    from board_ui.views.team import TeamView

    bindings = {b.key: b for b in TeamView.BINDINGS}
    assert "a" in bindings, "TeamView must bind 'a' key to session attach"


def test_team_view_has_worker_detail_panel() -> None:
    """TeamView must compose a WorkerDetailPanel widget."""
    import inspect
    from board_ui.views.team import TeamView
    from board_ui.widgets.worker_detail import WorkerDetailPanel

    source = inspect.getsource(TeamView.compose)
    assert "WorkerDetailPanel" in source, (
        "TeamView.compose() must yield a WorkerDetailPanel widget"
    )


# ---------------------------------------------------------------------------
# WorkerDetailPanel widget
# ---------------------------------------------------------------------------

def test_worker_detail_panel_widget_exists() -> None:
    from board_ui.widgets.worker_detail import WorkerDetailPanel
    assert WorkerDetailPanel is not None


def test_worker_detail_panel_has_update_method() -> None:
    from board_ui.widgets.worker_detail import WorkerDetailPanel
    assert hasattr(WorkerDetailPanel, "update_worker")


def test_worker_detail_panel_renders_tool_names() -> None:
    from board_ui.widgets.worker_detail import WorkerDetailPanel
    from board_ui.interfaces.org_connection import WorkerDetail

    detail = WorkerDetail(
        worker_id="wrkr-1",
        tools=[{"name": "rc", "description": "Remote compose"}],
        storage_tree={},
        active_beads=[],
        recent_messages=[],
        briefing_excerpt="You are the CEO.",
    )
    panel = WorkerDetailPanel()
    rendered = panel.render_detail_text(detail)
    assert "rc" in rendered
    assert "Remote compose" in rendered


def test_worker_detail_panel_renders_storage_tree() -> None:
    from board_ui.widgets.worker_detail import WorkerDetailPanel
    from board_ui.interfaces.org_connection import WorkerDetail

    detail = WorkerDetail(
        worker_id="wrkr-1",
        tools=[],
        storage_tree={"BRIEFING.md": None, "work": {"notes.md": None}},
        active_beads=[],
        recent_messages=[],
        briefing_excerpt="",
    )
    panel = WorkerDetailPanel()
    rendered = panel.render_detail_text(detail)
    assert "BRIEFING.md" in rendered
    assert "work" in rendered
