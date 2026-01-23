"""Tests for Provider Configuration widget.

Tests the AI provider configuration UI component.
"""

import pytest
from textual.widgets import Switch, Input, Static

from board_ui.widgets.provider_config import ProviderConfigWidget, ProviderInfo


class TestProviderConfigWidget:
    """Tests for ProviderConfigWidget."""

    @pytest.mark.asyncio
    async def test_widget_composes(self):
        """Widget should compose provider list."""
        from textual.app import App, ComposeResult

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield ProviderConfigWidget(id="provider-config")

        app = TestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            # Check widget exists
            widget = app.query_one("#provider-config", ProviderConfigWidget)
            assert widget is not None

            # Check header exists
            header = app.query_one("#provider-header", Static)
            assert header is not None

            # Check provider list exists
            provider_list = app.query_one("#provider-list")
            assert provider_list is not None

    @pytest.mark.asyncio
    async def test_shows_available_providers(self):
        """Should list Anthropic, OpenAI, etc."""
        from textual.app import App, ComposeResult

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield ProviderConfigWidget(id="provider-config")

        app = TestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            # Check default providers are shown
            anthropic_card = app.query_one("#card-anthropic")
            assert anthropic_card is not None

            openai_card = app.query_one("#card-openai")
            assert openai_card is not None

            claude_code_card = app.query_one("#card-claude_code")
            assert claude_code_card is not None

    @pytest.mark.asyncio
    async def test_enable_disable_toggle(self):
        """Each provider should have enable/disable toggle."""
        from textual.app import App, ComposeResult

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield ProviderConfigWidget(id="provider-config")

        app = TestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            # Check switches exist for each provider
            anthropic_switch = app.query_one("#switch-anthropic", Switch)
            assert anthropic_switch is not None

            openai_switch = app.query_one("#switch-openai", Switch)
            assert openai_switch is not None

            # Anthropic should be disabled by default
            assert anthropic_switch.value is False

            # Claude Code should be enabled by default
            claude_switch = app.query_one("#switch-claude_code", Switch)
            assert claude_switch.value is True

    @pytest.mark.asyncio
    async def test_api_key_input_masked(self):
        """API key input should be masked."""
        from textual.app import App, ComposeResult

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield ProviderConfigWidget(id="provider-config")

        app = TestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            # Check API key inputs are password fields
            anthropic_input = app.query_one("#apikey-anthropic", Input)
            assert anthropic_input is not None
            assert anthropic_input.password is True

            openai_input = app.query_one("#apikey-openai", Input)
            assert openai_input.password is True

    @pytest.mark.asyncio
    async def test_validates_api_key(self):
        """Should validate API key format."""
        widget = ProviderConfigWidget()

        # Test Anthropic key validation
        assert widget._validate_api_key("anthropic", "sk-ant-api-valid-key-here-12345") is True
        assert widget._validate_api_key("anthropic", "invalid-key") is False
        assert widget._validate_api_key("anthropic", "") is False

        # Test OpenAI key validation
        assert widget._validate_api_key("openai", "sk-proj-valid-key-here-12345") is True
        assert widget._validate_api_key("openai", "invalid-key") is False

        # Claude Code doesn't need API key
        assert widget._validate_api_key("claude_code", "") is True

    @pytest.mark.asyncio
    async def test_friendly_labels(self):
        """Should use 'AI Service' not 'LLM Provider'."""
        # Check the PROVIDERS list uses friendly names
        from board_ui.widgets.provider_config import ProviderConfigWidget

        providers = ProviderConfigWidget.PROVIDERS

        # Provider names should be friendly
        for p in providers:
            # Should NOT contain jargon like "LLM"
            assert "LLM" not in p.name
            assert "LLM" not in p.description
            # Should have friendly descriptions
            assert len(p.description) > 10
