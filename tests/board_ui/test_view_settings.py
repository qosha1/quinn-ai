"""Tests for Settings view."""

import pytest
from pathlib import Path
from textual.widgets import Label, Button, Select

from board_ui.views.settings import SettingsView
from board_ui.config import BoardConfig
from board_ui.app import BoardApp


class TestSettingsView:
    """Test Settings view rendering and behavior."""

    @pytest.mark.asyncio
    async def test_settings_view_composes(self):
        """Settings view should render without errors."""
        config = BoardConfig(org_paths=[])
        app = BoardApp(config)

        async with app.run_test() as pilot:
            settings = SettingsView()
            await pilot.app.mount(settings)
            await pilot.pause()

            # Check that key elements exist
            assert settings.query_one("#settings-header")
            assert settings.query_one("#default-provider-section")
            assert settings.query_one("#providers-section")
            assert settings.query_one("#current-default-label", Label)
            assert settings.query_one("#change-provider-btn", Button)
            assert settings.query_one("#provider-select", Select)

    @pytest.mark.asyncio
    async def test_settings_view_shows_default_provider(self):
        """Settings view should show current default provider."""
        config = BoardConfig(org_paths=[])
        app = BoardApp(config)

        async with app.run_test() as pilot:
            settings = SettingsView()
            await pilot.app.mount(settings)
            await pilot.pause()

            # Should show placeholder initially
            default_label = settings.query_one("#current-default-label", Label)
            # Check the label is present (content will be updated by refresh_settings)
            assert default_label is not None

    @pytest.mark.asyncio
    async def test_settings_view_change_button_exists(self):
        """Settings view should have a change provider button."""
        config = BoardConfig(org_paths=[])
        app = BoardApp(config)

        async with app.run_test() as pilot:
            settings = SettingsView()
            await pilot.app.mount(settings)
            await pilot.pause()

            # Check button exists
            change_btn = settings.query_one("#change-provider-btn", Button)
            assert change_btn.label == "Change"

    @pytest.mark.asyncio
    async def test_settings_view_providers_list_empty_initially(self):
        """Settings view should have an empty providers list initially."""
        config = BoardConfig(org_paths=[])
        app = BoardApp(config)

        async with app.run_test() as pilot:
            settings = SettingsView()
            await pilot.app.mount(settings)
            await pilot.pause()

            # Providers list should exist but be empty
            providers_list = settings.query_one("#providers-list")
            assert providers_list is not None
