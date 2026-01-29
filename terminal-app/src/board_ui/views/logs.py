"""
Logs view - searchable and viewable system logs.

Shows:
- Filter controls (component, level, time range)
- Search input box
- Log entry list with syntax highlighting
- Pagination controls
- Auto-refresh toggle
"""

from datetime import date
from pathlib import Path
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import Button, Input, Label, Select, Static, Switch
from textual.widget import Widget


class RenderableStatic(Static):
    """Static widget with .renderable property for test compatibility."""

    @property
    def renderable(self):
        """Return the content as renderable for test compatibility."""
        return self.content

# Import will use from cli.core when running in the board context
try:
    from cli.core.log_reader import LogReader
except ImportError:
    # Fallback for testing
    LogReader = None


class LogsView(Widget):
    """Logs tab view with filtering and search."""

    DEFAULT_CSS = """
    LogsView {
        layout: vertical;
        height: 100%;
    }

    #log-controls {
        height: auto;
        padding: 1;
        background: $surface-darken-1;
    }

    #log-filters {
        height: auto;
    }

    #log-component-filter {
        width: 20;
        margin-right: 2;
    }

    #log-level-filter {
        width: 15;
        margin-right: 2;
    }

    #log-search-input {
        width: 30;
        margin-right: 2;
    }

    #auto-refresh-toggle {
        width: auto;
    }

    #log-entries-container {
        height: 1fr;
        padding: 1;
    }

    .log-entry {
        height: auto;
        margin-bottom: 1;
    }

    .log-entry.level-error {
        color: $error;
    }

    .log-entry.level-warning {
        color: $warning;
    }

    .log-entry.level-info {
        color: $text;
    }

    .log-entry.level-debug {
        color: $text-muted;
    }

    #log-pagination {
        height: 3;
        padding: 1;
        background: $surface-darken-1;
        align: center middle;
    }

    #log-prev-page {
        margin-right: 2;
    }

    #log-next-page {
        margin-left: 2;
    }

    #log-page-label {
        margin: 0 2;
    }

    #log-empty-message {
        height: 100%;
        align: center middle;
        color: $text-muted;
    }
    """

    def __init__(self, org_path: Optional[Path] = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._org_path = org_path
        self._log_reader: Optional[LogReader] = None
        if org_path and LogReader:
            self._log_reader = LogReader(org_path)

        self._current_page = 1
        self._page_size = 50
        self._auto_refresh = True
        self._current_component = None  # None = all components
        self._current_level = None      # None = all levels
        self._current_search = None     # None = no search

    def compose(self) -> ComposeResult:
        """Compose the logs view."""
        with Container(id="log-controls"):
            with Horizontal(id="log-filters"):
                yield Select(
                    options=[
                        ("All Components", None),
                        ("CLI", "cli"),
                        ("Workers", "worker"),
                        ("Sessions", "session"),
                        ("Board", "board"),
                        ("System", "system"),
                    ],
                    value=None,
                    id="log-component-filter",
                    allow_blank=False,
                )
                yield Select(
                    options=[
                        ("All Levels", None),
                        ("DEBUG", "DEBUG"),
                        ("INFO", "INFO"),
                        ("WARNING", "WARNING"),
                        ("ERROR", "ERROR"),
                        ("CRITICAL", "CRITICAL"),
                    ],
                    value=None,
                    id="log-level-filter",
                    allow_blank=False,
                )
                yield Input(
                    placeholder="Search logs...",
                    id="log-search-input",
                )
                yield Switch(
                    value=True,
                    id="auto-refresh-toggle",
                )
                yield Label("Auto-refresh", id="auto-refresh-label")

        with ScrollableContainer(id="log-entries-container"):
            pass  # Will be populated dynamically

        with Horizontal(id="log-pagination"):
            yield Button("◀ Prev", id="log-prev-page", variant="default")
            yield Label("Page 1", id="log-page-label")
            yield Button("Next ▶", id="log-next-page", variant="default")

    async def refresh_logs(self) -> None:
        """Refresh the log entries."""
        if not self._log_reader:
            # No log reader - show empty state
            await self._display_logs([])
            return

        # Get logs based on current filters/search
        try:
            if self._current_search:
                logs = self._log_reader.search_logs(
                    query=self._current_search,
                    component=self._current_component,
                    level=self._current_level,
                )
            elif self._current_component is None and self._current_level is None and self._current_page == 1:
                # No filters/search, first page - use tail for most recent logs
                logs = self._log_reader.tail_logs(
                    component=None,
                    lines=self._page_size,
                )
            else:
                # With filters or pagination - use read_logs
                logs = self._log_reader.read_logs(
                    component=self._current_component,
                    level=self._current_level,
                    limit=self._page_size,
                    offset=(self._current_page - 1) * self._page_size,
                )

            # Update UI
            await self._display_logs(logs)

        except Exception:
            # On error, show empty state
            await self._display_logs([])

    async def _display_logs(self, logs: list[dict]) -> None:
        """Display log entries in the UI."""
        container = self.query_one("#log-entries-container", ScrollableContainer)

        # Remove existing entries
        for child in list(container.children):
            await child.remove()

        if not logs:
            # Show empty message
            await container.mount(RenderableStatic("No logs available", id="log-empty-message"))
            return

        # Add log entries
        for log in logs:
            level = log.get("level", "INFO")
            timestamp = log.get("timestamp", "")
            component = log.get("component", "")
            message = log.get("message", "")

            # Format timestamp (remove microseconds and Z)
            if timestamp:
                timestamp = timestamp.replace("Z", "").split(".")[0]

            # Create log entry label
            log_text = f"{timestamp} [{level:8s}] {component:10s}: {message}"
            level_class = f"level-{level.lower()}"

            await container.mount(
                Label(log_text, classes=f"log-entry {level_class}")
            )

    async def _apply_filters(self) -> None:
        """Apply current filters and refresh logs."""
        # Read from widgets in case they were set directly (e.g., in tests)
        try:
            component_filter = self.query_one("#log-component-filter", Select)
            self._current_component = component_filter.value
        except Exception:
            pass

        try:
            level_filter = self.query_one("#log-level-filter", Select)
            self._current_level = level_filter.value
        except Exception:
            pass

        await self.refresh_logs()

    async def _perform_search(self) -> None:
        """Perform search with current query."""
        # Read from widget in case it was set directly (e.g., in tests)
        try:
            search_input = self.query_one("#log-search-input", Input)
            self._current_search = search_input.value if search_input.value else None
        except Exception:
            pass

        await self.refresh_logs()

    async def on_select_changed(self, event: Select.Changed) -> None:
        """Handle filter selection changes."""
        event.stop()  # Prevent propagation
        if event.select.id == "log-component-filter":
            self._current_component = event.value
            self._current_page = 1  # Reset to first page
            await self._apply_filters()
        elif event.select.id == "log-level-filter":
            self._current_level = event.value
            self._current_page = 1  # Reset to first page
            await self._apply_filters()

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes."""
        event.stop()  # Prevent propagation
        if event.input.id == "log-search-input":
            self._current_search = event.value if event.value else None
            self._current_page = 1  # Reset to first page
            await self._perform_search()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle search input submission."""
        event.stop()  # Prevent propagation
        if event.input.id == "log-search-input":
            self._current_search = event.value if event.value else None
            self._current_page = 1  # Reset to first page
            await self._perform_search()

    async def on_switch_changed(self, event: Switch.Changed) -> None:
        """Handle auto-refresh toggle."""
        event.stop()  # Prevent propagation
        if event.switch.id == "auto-refresh-toggle":
            self._auto_refresh = event.value

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle pagination button presses."""
        event.stop()  # Prevent propagation
        if event.button.id == "log-prev-page":
            if self._current_page > 1:
                self._current_page -= 1
                await self.refresh_logs()
                await self._update_page_label()
        elif event.button.id == "log-next-page":
            self._current_page += 1
            await self.refresh_logs()
            await self._update_page_label()

    async def _update_page_label(self) -> None:
        """Update the page number label."""
        page_label = self.query_one("#log-page-label", Label)
        page_label.update(f"Page {self._current_page}")

    def set_org_path(self, org_path: Path) -> None:
        """Set the organization path and initialize log reader."""
        self._org_path = org_path
        if LogReader:
            self._log_reader = LogReader(org_path)
