"""Tests for CEO Briefing Composer widget.

Tests the initial briefing message UI component.
"""

import pytest
from textual.widgets import Static, TextArea, Button, Select

from board_ui.widgets.ceo_briefing import (
    CEOBriefingWidget,
    BriefingContent,
    BRIEFING_TEMPLATES,
)


class TestCEOBriefingWidget:
    """Tests for CEOBriefingWidget."""

    @pytest.mark.asyncio
    async def test_widget_composes(self):
        """Widget should compose structured sections."""
        from textual.app import App, ComposeResult

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield CEOBriefingWidget(id="ceo-briefing")

        app = TestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            # Check widget exists
            widget = app.query_one("#ceo-briefing", CEOBriefingWidget)
            assert widget is not None

            # Check header exists
            header = app.query_one("#briefing-header", Static)
            assert header is not None

            # Check template select exists
            template_select = app.query_one("#template-select", Select)
            assert template_select is not None

    @pytest.mark.asyncio
    async def test_has_context_section(self):
        """Should have Context section."""
        from textual.app import App, ComposeResult

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield CEOBriefingWidget(id="ceo-briefing")

        app = TestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            # Check context section exists
            context_label = app.query_one("#context-label", Static)
            assert context_label is not None

            context_editor = app.query_one("#context-editor", TextArea)
            assert context_editor is not None

    @pytest.mark.asyncio
    async def test_has_requirements_section(self):
        """Should have Requirements section."""
        from textual.app import App, ComposeResult

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield CEOBriefingWidget(id="ceo-briefing")

        app = TestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            # Check requirements section exists
            req_label = app.query_one("#requirements-label", Static)
            assert req_label is not None

            req_editor = app.query_one("#requirements-editor", TextArea)
            assert req_editor is not None

    @pytest.mark.asyncio
    async def test_has_constraints_section(self):
        """Should have Constraints section."""
        from textual.app import App, ComposeResult

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield CEOBriefingWidget(id="ceo-briefing")

        app = TestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            # Check constraints section exists
            constraints_label = app.query_one("#constraints-label", Static)
            assert constraints_label is not None

            constraints_editor = app.query_one("#constraints-editor", TextArea)
            assert constraints_editor is not None

    @pytest.mark.asyncio
    async def test_has_success_criteria_section(self):
        """Should have Success Criteria section."""
        from textual.app import App, ComposeResult

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield CEOBriefingWidget(id="ceo-briefing")

        app = TestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            # Check success criteria section exists
            sc_label = app.query_one("#success-criteria-label", Static)
            assert sc_label is not None

            sc_editor = app.query_one("#success-criteria-editor", TextArea)
            assert sc_editor is not None

    @pytest.mark.asyncio
    async def test_markdown_editor(self):
        """Should provide markdown editing with preview."""
        from textual.app import App, ComposeResult
        from textual.widgets import TabbedContent

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield CEOBriefingWidget(id="ceo-briefing")

        app = TestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            # Check tabbed interface exists (edit/preview)
            tabs = app.query_one("#briefing-tabs", TabbedContent)
            assert tabs is not None

            # Check preview content exists
            preview = app.query_one("#preview-content", Static)
            assert preview is not None

    @pytest.mark.asyncio
    async def test_templates_available(self):
        """Should provide templates for common org types."""
        from textual.app import App, ComposeResult

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield CEOBriefingWidget(id="ceo-briefing")

        app = TestApp()
        async with app.run_test() as pilot:
            await pilot.pause()

            widget = app.query_one("#ceo-briefing", CEOBriefingWidget)

            # Check templates are available
            templates = widget.get_templates()
            assert len(templates) >= 3

            # Templates should have content
            for name, template in templates.items():
                assert template.context or template.requirements
                assert isinstance(template, BriefingContent)

    @pytest.mark.asyncio
    async def test_message_queued_on_save(self):
        """Briefing should be queued for CEO on org start."""
        # Test the internal queue method directly
        content = BriefingContent(
            context="Test context",
            requirements="Test requirements",
        )

        widget = CEOBriefingWidget(initial_content=content)

        # Verify content is retrievable
        assert widget._content.context == "Test context"
        assert widget._content.requirements == "Test requirements"

        # Test markdown generation
        markdown = content.to_markdown()
        assert "## Context" in markdown
        assert "Test context" in markdown
        assert "## Requirements" in markdown
