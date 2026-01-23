"""
Team view - worker sessions with jump-in capability.

Shows:
- All workers with status (active/idle/blocked)
- Each worker: name, role, current task summary
- [Chat Now] button to open session in new window
- CEO prominently featured at top
- Filter by team/status
"""

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.widgets import Button, DataTable, Label, Static
from textual.widget import Widget

from ..interfaces.org_connection import WorkerInfo, SessionState


class TeamView(Widget):
    """Team view with worker list and jump-in buttons."""

    DEFAULT_CSS = """
    TeamView {
        layout: vertical;
        height: 100%;
    }

    #team-header {
        height: auto;
        padding: 1;
        border-bottom: solid $secondary;
    }

    #workers-table {
        height: 1fr;
    }

    DataTable {
        height: 100%;
    }

    .filter-btn {
        margin-right: 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._workers: list[WorkerInfo] = []
        self._current_filter = "all"

    def compose(self) -> ComposeResult:
        with Container(id="team-header"):
            yield Label("Team Members", classes="panel-title")
            with Horizontal():
                yield Button("All", id="filter-all", classes="filter-btn", variant="primary")
                yield Button("Active", id="filter-active", classes="filter-btn")
                yield Button("Idle", id="filter-idle", classes="filter-btn")

        with Container(id="workers-table"):
            table = DataTable(id="workers-data")
            table.add_columns("Status", "Name", "Role", "Team", "Current Task", "Actions")
            yield table

    async def on_mount(self) -> None:
        """Load workers when view mounts."""
        await self.refresh_workers()

    async def refresh_workers(self) -> None:
        """Refresh the worker list from org connection."""
        table = self.query_one("#workers-data", DataTable)
        table.clear()

        # Try to get workers from org connection
        if hasattr(self.app, 'org_connection') and self.app.org_connection:
            self._workers = self.app.org_connection.get_workers()
            self._populate_table_from_connection()
        else:
            # Placeholder data when no org connected
            self._populate_placeholder_data()

    def _populate_table_from_connection(self) -> None:
        """Populate table with real worker data."""
        table = self.query_one("#workers-data", DataTable)

        for worker in self._workers:
            # Apply filter
            if not self._passes_filter(worker):
                continue

            # Status icon based on session state
            status_icon = self._get_status_icon(worker.session_state)

            # Format role with CEO indicator
            role = f"★ {worker.role}" if worker.is_ceo else worker.role

            # Current task or status
            task = worker.current_task or self._get_status_text(worker.session_state)

            table.add_row(
                status_icon,
                worker.name,
                role,
                worker.team_name,
                task,
                "[Chat]",
                key=worker.id,  # Store worker ID as row key
            )

    def _populate_placeholder_data(self) -> None:
        """Populate table with placeholder data."""
        table = self.query_one("#workers-data", DataTable)

        placeholders = [
            ("🟢", "No Org Connected", "-", "-", "Connect to an org to see workers", "-"),
        ]

        for row in placeholders:
            table.add_row(*row)

    def _get_status_icon(self, state: Optional[SessionState]) -> str:
        """Get status icon for session state."""
        if state is None:
            return "⚫"  # No session
        if state == SessionState.RUNNING:
            return "🟢"  # Active
        if state == SessionState.IDLE:
            return "🟡"  # Idle
        if state == SessionState.BLOCKED:
            return "🔴"  # Blocked
        if state == SessionState.STARTING:
            return "🔵"  # Starting
        return "⚫"

    def _get_status_text(self, state: Optional[SessionState]) -> str:
        """Get status text for session state."""
        if state is None:
            return "No session"
        if state == SessionState.RUNNING:
            return "Working..."
        if state == SessionState.IDLE:
            return "Idle"
        if state == SessionState.BLOCKED:
            return "Blocked"
        if state == SessionState.STARTING:
            return "Starting..."
        return "Unknown"

    def _passes_filter(self, worker: WorkerInfo) -> bool:
        """Check if worker passes the current filter."""
        if self._current_filter == "all":
            return True
        if self._current_filter == "active":
            return worker.session_state in (SessionState.RUNNING, SessionState.STARTING)
        if self._current_filter == "idle":
            return worker.session_state == SessionState.IDLE or worker.session_state is None
        return True

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle filter button presses."""
        if event.button.id in ("filter-all", "filter-active", "filter-idle"):
            # Update filter
            self._current_filter = event.button.id.replace("filter-", "")

            # Update button styles
            for btn_id in ("filter-all", "filter-active", "filter-idle"):
                btn = self.query_one(f"#{btn_id}", Button)
                if btn_id == event.button.id:
                    btn.variant = "primary"
                else:
                    btn.variant = "default"

            # Refresh table with new filter
            await self.refresh_workers()

    async def on_data_table_cell_selected(self, event: DataTable.CellSelected) -> None:
        """Handle cell selection - check if it's the Chat button."""
        if event.coordinate.column == 5:  # Actions column
            table = self.query_one("#workers-data", DataTable)
            row_key = table.get_row_key(event.coordinate.row)

            # Find worker by ID
            worker = next((w for w in self._workers if w.id == row_key), None)
            if worker:
                await self._open_worker_chat(worker)

    async def _open_worker_chat(self, worker: WorkerInfo) -> None:
        """Open a chat window with a worker."""
        from ..terminals import get_terminal_provider

        if not worker.tmux_session_name:
            self.app.notify(f"{worker.name} has no active session", severity="warning")
            return

        terminal = get_terminal_provider()
        if terminal is None:
            self.app.notify("No terminal available", severity="error")
            return

        try:
            terminal.attach_to_session(
                title=f"Chat with {worker.name}",
                session_name=worker.tmux_session_name,
            )
            self.app.notify(f"Opened chat window with {worker.name}")
        except Exception as e:
            self.app.notify(f"Failed to open chat: {e}", severity="error")
