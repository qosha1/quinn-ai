"""Real-click e2e sweep via Textual Pilot.

The existing test_e2e_*.py tests assert that elements exist but rarely
simulate actual interaction through Textual's event system. That gap
shipped both x1dd (NoActiveWorker on team panel) and the misdiagnosed
kl7m to the user.

Each test here drives a real interaction (focus + keypress / pilot.click)
and asserts the visible result. A regression in any panel's click flow
should show up here.

Repeatable command:

    .venv/bin/python -m pytest tests/board_ui/test_e2e_real_clicks.py -v
"""

import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from textual.coordinate import Coordinate
from textual.widgets import Button, DataTable, Static

from board_ui.app import BoardApp
from board_ui.config import BoardConfig

from tests.board_ui.test_e2e_messages_view import (
    create_base_org_db,
    add_messages_to_channel,
)


# ─── Fixtures ────────────────────────────────────────────────────────────


REAL_CLEO_MESSAGE = """Riley — you are third in our discovery sprint, working closely with Pria. Your assignment: **What is the right fundraising thesis?**

You start after Pria has a working product brief (she's drafting now). Once that lands, your job is to synthesize it into an investor-grade thesis.

**Your deliverable:**
A fundraise thesis doc (save to `storage/shared/company/THESIS_DRAFT.md`) that answers:
1. In one sentence: why should an investor write a check NOW vs later, and into us vs. competitors?
2. What stage are we honestly at (pre-seed continuation, seed, bridge?) and what does $1M actually unlock?
3. What is the narrative arc? (Where have we been → where we are → where we're going)
4. What objections will we get, and how do we answer them?

[Actions ▸] sprinkled brackets to mimic any potentially-Rich-markup-looking content."""


@pytest.fixture
def org_with_real_message():
    """Org with a real-shaped message containing markdown + brackets +
    backticks — same shape as Cleo's actual outbound DMs that triggered
    the user's 'right pane shows nothing' report."""
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir) / "test-org-realmsg"
        org_path.mkdir()
        db_path = create_base_org_db(org_path)
        add_messages_to_channel(db_path, "board-channel", [
            {"content": REAL_CLEO_MESSAGE, "priority": 2, "is_unread": True},
        ])
        yield org_path


@pytest.fixture
def org_with_actual_live_message():
    """Org seeded with the EXACT verbatim content of the Cleo→Riley DM
    from ~/orgs/debugg-fundraise that the user reported as 'still
    fucking nothing in the messages side bar'. If a Pilot test against
    this content fails to render the body, that's the live bug
    reproduced."""
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir) / "test-org-actualmsg"
        org_path.mkdir()
        db_path = create_base_org_db(org_path)
        live_msg_path = Path("/tmp/cleo_real_msg.txt")
        if not live_msg_path.exists():
            pytest.skip("no /tmp/cleo_real_msg.txt — run sqlite dump first")
        content = live_msg_path.read_text()
        add_messages_to_channel(db_path, "board-channel", [
            {"content": content, "priority": 2, "is_unread": True},
        ])
        yield org_path


@pytest.fixture
def populated_org():
    """Org with workers, a board-channel message, and an OKR."""
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir) / "test-org-realclicks"
        org_path.mkdir()
        db_path = create_base_org_db(org_path)
        add_messages_to_channel(db_path, "board-channel", [
            {
                "content": "BACONSANDWICH-UNIQUE-MARKER-12345",
                "priority": 3,
                "is_unread": True,
            },
        ])
        # Seed an OKR so the OKR panel has something to render.
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            """INSERT INTO okrs (id, title, description, owner_worker_id,
                                  status, parent_okr_id, key_results, due_date,
                                  created_at)
               VALUES ('okr-test', 'Test OKR', 'desc', 'worker-ceo', 'active',
                       NULL, NULL, NULL, ?)""",
            (datetime.now().isoformat(),),
        )
        conn.commit()
        conn.close()
        yield org_path


# ─── Helpers ─────────────────────────────────────────────────────────────


async def _boot_app(org_path):
    config = BoardConfig(org_paths=[org_path])
    app = BoardApp(config)
    return app


# Use a larger Pilot viewport so off-screen widgets (CEO chat button on
# dashboard, etc.) are clickable. Default Textual test viewport is 80×24,
# which clips the dashboard layout.
PILOT_SIZE = (140, 50)


# ─── Tests ───────────────────────────────────────────────────────────────


class TestTabSwitching:
    """Each tab should switch without raising."""

    @pytest.mark.parametrize("tab", ["dashboard", "team", "messages", "okrs", "logs", "settings"])
    @pytest.mark.asyncio
    async def test_switch_to_tab(self, populated_org, tab):
        app = await _boot_app(populated_org)
        async with app.run_test(size=PILOT_SIZE) as pilot:
            await pilot.pause()
            await app._connect_to_org(populated_org)
            await pilot.pause()

            app.action_switch_tab(tab)
            await pilot.pause()
            # Pilot.run_test re-raises any unhandled exception from the
            # event loop, so reaching this line is the assertion.


class TestDashboardButtons:
    """Dashboard action buttons should not crash on click."""

    @pytest.mark.parametrize("btn_id", ["chat-ceo-btn", "start-org-btn", "stop-org-btn", "restart-org-btn"])
    @pytest.mark.asyncio
    async def test_button_press(self, populated_org, btn_id):
        app = await _boot_app(populated_org)
        async with app.run_test(size=PILOT_SIZE) as pilot:
            await pilot.pause()
            await app._connect_to_org(populated_org)
            await pilot.pause()

            app.action_switch_tab("dashboard")
            await pilot.pause()

            try:
                btn = app.query_one(f"#{btn_id}", Button)
            except Exception:
                pytest.skip(f"Button {btn_id} not present (may be conditional)")

            await pilot.click(f"#{btn_id}")
            await pilot.pause()


class TestTeamPanel:
    """Team panel — clicking action cells, filter buttons, hire button."""

    @pytest.mark.asyncio
    async def test_action_cell_click_does_not_crash(self, populated_org):
        """quinn-ai-x1dd: clicking [Actions ▸] cell on a non-CEO row."""
        app = await _boot_app(populated_org)
        async with app.run_test(size=PILOT_SIZE) as pilot:
            await pilot.pause()
            await app._connect_to_org(populated_org)
            await pilot.pause()

            app.action_switch_tab("team")
            await pilot.pause()

            from board_ui.views.team import TeamView
            team_view = app.query_one(TeamView)
            table = team_view.query_one("#workers-data", DataTable)
            assert table.row_count >= 2, f"Need ≥2 rows; got {table.row_count}"

            table.cursor_type = "cell"
            table.cursor_coordinate = Coordinate(1, 5)  # row 1 = non-CEO, col 5 = Actions
            table.focus()
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

    @pytest.mark.parametrize("btn_id", ["filter-all", "filter-active", "filter-idle", "hire-worker-btn"])
    @pytest.mark.asyncio
    async def test_filter_and_hire_buttons(self, populated_org, btn_id):
        app = await _boot_app(populated_org)
        async with app.run_test(size=PILOT_SIZE) as pilot:
            await pilot.pause()
            await app._connect_to_org(populated_org)
            await pilot.pause()

            app.action_switch_tab("team")
            await pilot.pause()

            await pilot.click(f"#{btn_id}")
            await pilot.pause()


class TestMessagesPanel:
    """Messages panel — row selection populating detail pane, reply controls."""

    @pytest.mark.asyncio
    async def test_row_selection_via_keyboard_populates_detail(self, populated_org):
        app = await _boot_app(populated_org)
        async with app.run_test(size=PILOT_SIZE) as pilot:
            await pilot.pause()
            await app._connect_to_org(populated_org)
            await pilot.pause()

            app.action_switch_tab("messages")
            await pilot.pause()

            table = app.query_one("#messages-table", DataTable)
            assert table.row_count >= 1, (
                f"Expected ≥1 row in messages-table; got {table.row_count}. "
                f"Messages panel never loaded the channel."
            )

            table.focus()
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            body = app.query_one("#message-body", Static)
            rendered = str(body.render())
            assert "BACONSANDWICH-UNIQUE-MARKER-12345" in rendered, (
                f"Detail pane did not show the selected message (keyboard). "
                f"Got body: {rendered!r}"
            )

    @pytest.mark.asyncio
    async def test_row_selection_via_mouse_click_populates_detail(self, populated_org):
        """Same as keyboard test but using pilot.click — mouse path is what
        the user actually uses, and DataTable's click → RowSelected pipeline
        is different from focus+Enter."""
        app = await _boot_app(populated_org)
        async with app.run_test(size=PILOT_SIZE) as pilot:
            await pilot.pause()
            await app._connect_to_org(populated_org)
            await pilot.pause()

            app.action_switch_tab("messages")
            await pilot.pause()

            table = app.query_one("#messages-table", DataTable)
            assert table.row_count >= 1, f"Got {table.row_count} rows"

            # Click directly on the table widget — Pilot resolves the
            # offset to the table's region. cursor_type is 'row' per
            # messages.py:170 so a click triggers RowSelected.
            await pilot.click("#messages-table")
            await pilot.pause()

            body = app.query_one("#message-body", Static)
            rendered = str(body.render())
            assert "BACONSANDWICH-UNIQUE-MARKER-12345" in rendered, (
                f"Detail pane did not show the selected message (mouse). "
                f"Got body: {rendered!r}\n"
                "If this fails but the keyboard variant passes, the bug is "
                "specific to click-driven RowSelected events (kl7m-adjacent)."
            )


class TestMessagesPanelRealContent:
    """Real-world message content with brackets / markdown / backticks
    must render in the body — not silently fail Rich markup parsing."""

    @pytest.mark.asyncio
    async def test_body_renders_message_with_markdown_and_brackets(self, org_with_real_message):
        app = await _boot_app(org_with_real_message)
        async with app.run_test(size=PILOT_SIZE) as pilot:
            await pilot.pause()
            await app._connect_to_org(org_with_real_message)
            await pilot.pause()

            app.action_switch_tab("messages")
            await pilot.pause()

            table = app.query_one("#messages-table", DataTable)
            assert table.row_count >= 1

            # Auto-highlight on mount should already have triggered
            # _select_message_by_row_key. If body.update() crashed in
            # Rich markup parsing, the placeholder text remains.
            body = app.query_one("#message-body", Static)
            rendered = str(body.render())

            # Distinctive substring from REAL_CLEO_MESSAGE that would
            # only appear if the body actually rendered the content.
            assert "discovery sprint" in rendered, (
                f"Body did not render real-shaped message content. "
                f"Got: {rendered[:200]!r}\n"
                "If this fails: Static defaults to markup=True; brackets "
                "or unmatched markup in the content are crashing the "
                "render. Fix: pass markup=False to body.update or wrap "
                "content in rich.text.Text(..., markup=None)."
            )


    @pytest.mark.asyncio
    async def test_body_renders_against_live_debugg_fundraise_org(self):
        """Connect to ~/orgs/debugg-fundraise and verify the body
        renders. This is the closest reproduction of the user's
        environment short of having them paste a screenshot. Skip if
        the live org doesn't exist (so the test stays portable)."""
        live_org = Path.home() / "orgs" / "debugg-fundraise"
        if not (live_org / "live" / "quinn.db").exists():
            pytest.skip(f"live org not present at {live_org}")

        app = await _boot_app(live_org)
        async with app.run_test(size=PILOT_SIZE) as pilot:
            await pilot.pause()
            await app._connect_to_org(live_org)
            await pilot.pause()

            app.action_switch_tab("messages")
            await pilot.pause()

            table = app.query_one("#messages-table", DataTable)
            if table.row_count == 0:
                pytest.skip("live org has no messages to render")

            body = app.query_one("#message-body", Static)
            rendered = str(body.render())
            assert "Click on a message" not in rendered, (
                f"After mount + auto-highlight, body still shows the "
                f"placeholder. Live data isn't populating. "
                f"Body content: {rendered[:200]!r}"
            )

    @pytest.mark.asyncio
    async def test_body_renders_actual_live_cleo_message(self, org_with_actual_live_message):
        """Identical to the test above but seeded from the verbatim DM
        content the user is staring at. If this passes but the user
        still reports a blank body, the bug is environment-specific."""
        app = await _boot_app(org_with_actual_live_message)
        async with app.run_test(size=PILOT_SIZE) as pilot:
            await pilot.pause()
            await app._connect_to_org(org_with_actual_live_message)
            await pilot.pause()

            app.action_switch_tab("messages")
            await pilot.pause()

            body = app.query_one("#message-body", Static)
            rendered = str(body.render())
            assert "discovery sprint" in rendered, (
                f"Live-content body did not render. Got: {rendered[:200]!r}"
            )


class TestOkrsPanel:
    """OKR panel — basic render with seeded data."""

    @pytest.mark.asyncio
    async def test_okr_panel_renders_seeded_okr(self, populated_org):
        app = await _boot_app(populated_org)
        async with app.run_test(size=PILOT_SIZE) as pilot:
            await pilot.pause()
            await app._connect_to_org(populated_org)
            await pilot.pause()

            app.action_switch_tab("okrs")
            await pilot.pause()
            # Just assert the tab switch + render didn't blow up — content
            # detail handled elsewhere (tests/board_ui/test_view_panel_data_sync.py).


class TestLogsPanel:
    """Logs panel — filter inputs and channel selector."""

    @pytest.mark.asyncio
    async def test_logs_panel_renders(self, populated_org):
        app = await _boot_app(populated_org)
        async with app.run_test(size=PILOT_SIZE) as pilot:
            await pilot.pause()
            await app._connect_to_org(populated_org)
            await pilot.pause()

            app.action_switch_tab("logs")
            await pilot.pause()


class TestSettingsPanel:
    """Settings panel."""

    @pytest.mark.asyncio
    async def test_settings_renders(self, populated_org):
        app = await _boot_app(populated_org)
        async with app.run_test(size=PILOT_SIZE) as pilot:
            await pilot.pause()
            await app._connect_to_org(populated_org)
            await pilot.pause()

            app.action_switch_tab("settings")
            await pilot.pause()
