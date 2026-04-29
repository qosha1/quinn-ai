"""Regression tests for board UI panel data-sync bugs.

Covers:
- quinn-ai-176s: OKR panel shows 'No OKRs found' when SQLite mirror is empty
  but bd has OKR-labeled epics (dolt-mode orgs).
- quinn-ai-qc1a: Messages panel doesn't render entries when the first
  alphabetical channel is empty but other channels have messages, and
  selecting a message doesn't update the right-hand detail pane.
"""

import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from textual.widgets import DataTable, Label, Static

from board_ui.app import BoardApp
from board_ui.config import BoardConfig
from board_ui.interfaces.org_connection import Message
from board_ui.views.messages import MessagesView

# Reuse the e2e helpers
from .test_e2e_messages_view import create_base_org_db, add_messages_to_channel


# ---------------------------------------------------------------------------
# OKR panel: bd-fallback when SQLite mirror is empty (quinn-ai-176s)
# ---------------------------------------------------------------------------


def _make_org_with_bd_only_okr(tmp_path: Path) -> Path:
    """Create org where workers/channels exist but `okrs` table is empty.

    Simulates a dolt-mode org: bd has the canonical OKR but the SQLite
    mirror was never populated (qn org okr set is broken on dolt orgs).
    """
    org_path = tmp_path / "test-org-bd-only"
    org_path.mkdir()
    create_base_org_db(org_path)
    # Don't insert anything into okrs — it's empty by default.
    return org_path


@pytest.mark.asyncio
async def test_okr_panel_shows_bd_okrs_when_mirror_is_empty(tmp_path, monkeypatch):
    """OKR panel should fall back to bd when SQLite mirror has no OKRs.

    Repro of quinn-ai-176s: dolt-mode orgs end up with an empty
    `okrs` table even when bd has OKR-labeled epics. The panel must
    still display them.
    """
    org_path = _make_org_with_bd_only_okr(tmp_path)

    # Mock bd's response for an OKR query: one open epic with label 'okr'.
    bd_okr_payload = [
        {
            "id": "test-org-6is",
            "title": "Q1: Bd-only OKR",
            "description": "Lives in bd, not in SQLite mirror",
            "status": "open",
            "assignee": "worker-ceo",
            "priority": 0,
            "labels": ["okr"],
            "created_at": "2026-04-01T00:00:00",
        }
    ]

    fake_result = MagicMock()
    fake_result.returncode = 0
    fake_result.stdout = __import__("json").dumps(bd_okr_payload)
    fake_result.stderr = ""

    # Patch run_bd in the OKR reader's lookup module.
    with patch(
        "board_ui.services.readers.okrs.run_bd",
        return_value=fake_result,
        create=True,
    ):
        config = BoardConfig(org_paths=[org_path])
        app = BoardApp(config)

        async with app.run_test() as pilot:
            await pilot.pause()
            await app._connect_to_org(org_path)
            await pilot.pause()

            conn = app.org_connection
            assert conn is not None
            okrs = conn.get_okrs()

    assert len(okrs) == 1, (
        "Expected bd-only OKR to be surfaced when SQLite mirror is empty; "
        f"got {len(okrs)} OKRs."
    )
    assert okrs[0].id == "test-org-6is"
    assert okrs[0].title == "Q1: Bd-only OKR"


# ---------------------------------------------------------------------------
# Messages panel: multi-channel scenario (quinn-ai-qc1a)
# ---------------------------------------------------------------------------


@pytest.fixture
def org_with_empty_first_channel():
    """Replicate the live-org scenario: many channels, the
    alphabetically-first one (board-channel) is empty, but a later
    channel ('general') has messages.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir) / "test-org-multi"
        org_path.mkdir()
        db_path = create_base_org_db(org_path)

        # board-channel exists but is empty
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT INTO channels (id, name, type) VALUES "
            "('ch-board', 'board-channel', 'topic')"
        )
        conn.commit()
        conn.close()

        # general channel with three messages
        add_messages_to_channel(
            db_path,
            "general",
            [
                {"content": "Welcome Riley!", "priority": 3, "from_worker_id": "worker-dev1"},
                {"content": "Welcome Nico!", "priority": 3, "from_worker_id": "worker-dev2"},
                {"content": "Stand up at 10", "priority": 2, "from_worker_id": "worker-ceo"},
            ],
        )

        yield org_path, db_path


@pytest.mark.asyncio
async def test_messages_panel_initial_render_picks_channel_with_messages(
    org_with_empty_first_channel,
):
    """On first paint, MessagesView should default to a channel that has
    messages, not the alphabetically-first empty channel.

    Repro of quinn-ai-qc1a: the live debugg-fundraise org has
    'board-channel' (empty) and 'general' (13 messages). Sorting channels
    by name puts board-channel first; the inbox shows zero rows even
    though the org has plenty of messages. Operators perceived this as
    'panel doesn't populate'.
    """
    org_path, db_path = org_with_empty_first_channel
    config = BoardConfig(org_paths=[org_path])
    app = BoardApp(config)

    async with app.run_test() as pilot:
        await pilot.pause()
        await app._connect_to_org(org_path)
        await pilot.pause()

        app.action_switch_tab("messages")
        await pilot.pause()

        table = app.query_one("#messages-table", DataTable)
        assert table.row_count == 3, (
            f"Initial paint should land on a channel with messages, "
            f"got {table.row_count} rows."
        )


@pytest.mark.asyncio
async def test_messages_panel_selection_populates_detail_pane(
    org_with_empty_first_channel,
):
    """Selecting a row should put message content into the detail pane.

    Repro of quinn-ai-qc1a: 'Selecting a message in the list does NOT
    show details in the right-hand pane'.
    """
    from textual.widgets._data_table import RowKey

    org_path, db_path = org_with_empty_first_channel
    config = BoardConfig(org_paths=[org_path])
    app = BoardApp(config)

    async with app.run_test() as pilot:
        await pilot.pause()
        await app._connect_to_org(org_path)
        await pilot.pause()

        app.action_switch_tab("messages")
        await pilot.pause()

        view = app.query_one("#messages-view", MessagesView)

        # Switch to 'general' (the channel that actually has messages).
        general = next(c for c in view._channels if c["name"] == "general")
        view._current_channel_id = general["id"]
        await view._load_channel_messages()
        await pilot.pause()

        assert view._messages, "Expected messages loaded for general channel"
        target_msg = view._messages[0]

        # Simulate row selection event.
        event = MagicMock()
        event.row_key = RowKey(target_msg.id)
        await view.on_data_table_row_selected(event)
        await pilot.pause()

        body = app.query_one("#message-body", Static)
        rendered = str(body.render())
        assert target_msg.content in rendered, (
            f"Expected detail pane to show message content "
            f"{target_msg.content!r}; got {rendered!r}"
        )

        header = app.query_one("#detail-header", Label)
        header_text = str(header.render())
        assert target_msg.from_worker_name in header_text or (
            target_msg.from_worker_id in header_text
        ), (
            f"Detail header should identify sender; got {header_text!r}"
        )
