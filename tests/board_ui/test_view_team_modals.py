"""Tests for the team-view action modals (quinn-ai-6hn).

Pins:
- HireWorkerModal returns a dict on submit, None on cancel
- WorkerActionsModal returns the chosen action string, None on cancel
- ConfirmFireModal returns True on confirm, False on cancel
- WorkerActionsModal only renders the actions it was given
"""

import pytest

from board_ui.app import BoardApp
from board_ui.config import BoardConfig
from board_ui.views._modals import (
    ConfirmFireModal,
    HireWorkerModal,
    WorkerActionsModal,
)
from textual.widgets import Button, Input


class TestHireWorkerModal:
    @pytest.mark.asyncio
    async def test_submit_returns_dict_with_form_values(self):
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            modal = HireWorkerModal()

            async def collect():
                return await app.push_screen_wait(modal)

            task = pilot.app.run_worker(collect, exclusive=False)
            await pilot.pause()
            modal.query_one("#hire-name", Input).value = "Alice"
            modal.query_one("#hire-role", Input).value = "Engineer"
            modal.query_one("#hire-manager", Input).value = "ceo"
            await pilot.pause()
            await pilot.click("#hire-submit")
            await pilot.pause()
            result = await task.wait()

            assert result == {"name": "Alice", "role": "Engineer", "manager": "ceo"}

    @pytest.mark.asyncio
    async def test_cancel_returns_none(self):
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            modal = HireWorkerModal()

            async def collect():
                return await app.push_screen_wait(modal)

            task = pilot.app.run_worker(collect, exclusive=False)
            await pilot.pause()
            await pilot.click("#hire-cancel")
            await pilot.pause()
            result = await task.wait()
            assert result is None

    @pytest.mark.asyncio
    async def test_submit_with_empty_name_or_role_does_not_dismiss(self):
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            modal = HireWorkerModal()

            async def collect():
                return await app.push_screen_wait(modal)

            task = pilot.app.run_worker(collect, exclusive=False)
            await pilot.pause()
            # Leave name/role empty, hit submit
            await pilot.click("#hire-submit")
            await pilot.pause()
            assert not task.is_finished, (
                "Modal should NOT dismiss with empty required fields"
            )
            # Cancel to release
            await pilot.click("#hire-cancel")
            await pilot.pause()
            await task.wait()


class TestWorkerActionsModal:
    @pytest.mark.asyncio
    async def test_only_provided_actions_have_buttons(self):
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            modal = WorkerActionsModal("alice", actions=["fire", "promote"])
            app.push_screen(modal)
            await pilot.pause()

            ids = {b.id for b in modal.query(Button)}
            assert "act-fire" in ids
            assert "act-promote" in ids
            assert "act-demote" not in ids
            assert "act-cancel" in ids

            await pilot.click("#act-cancel")
            await pilot.pause()

    @pytest.mark.asyncio
    async def test_picking_action_returns_its_name(self):
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            modal = WorkerActionsModal("alice", actions=["fire", "promote"])

            async def collect():
                return await app.push_screen_wait(modal)

            task = pilot.app.run_worker(collect, exclusive=False)
            await pilot.pause()
            await pilot.click("#act-promote")
            await pilot.pause()
            result = await task.wait()
            assert result == "promote"

    @pytest.mark.asyncio
    async def test_cancel_returns_none(self):
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            modal = WorkerActionsModal("alice", actions=["fire"])

            async def collect():
                return await app.push_screen_wait(modal)

            task = pilot.app.run_worker(collect, exclusive=False)
            await pilot.pause()
            await pilot.click("#act-cancel")
            await pilot.pause()
            result = await task.wait()
            assert result is None


class TestConfirmFireModal:
    @pytest.mark.asyncio
    async def test_confirm_returns_true(self):
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            modal = ConfirmFireModal("alice")

            async def collect():
                return await app.push_screen_wait(modal)

            task = pilot.app.run_worker(collect, exclusive=False)
            await pilot.pause()
            await pilot.click("#confirm-yes")
            await pilot.pause()
            result = await task.wait()
            assert result is True

    @pytest.mark.asyncio
    async def test_cancel_returns_false(self):
        app = BoardApp(BoardConfig.default())
        async with app.run_test() as pilot:
            modal = ConfirmFireModal("alice")

            async def collect():
                return await app.push_screen_wait(modal)

            task = pilot.app.run_worker(collect, exclusive=False)
            await pilot.pause()
            await pilot.click("#confirm-cancel")
            await pilot.pause()
            result = await task.wait()
            assert result is False
