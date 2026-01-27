"""
Team view - worker sessions with jump-in capability.

Shows:
- All workers with status (active/idle/blocked)
- Each worker: name, role, current task summary
- [Chat Now] button to open session in new window
- CEO prominently featured at top
- Filter by team/status
"""

import logging
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.widgets import Button, DataTable, Label, Static
from textual.widget import Widget

from ..interfaces.org_connection import WorkerInfo, SessionState

logger = logging.getLogger(__name__)


class TeamView(Widget):
    """Team view with worker list and jump-in buttons."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Track open session windows for cleanup
        self._open_windows: dict[str, any] = {}  # worker_id -> WindowHandle

    DEFAULT_CSS = """
    TeamView {
        layout: vertical;
        height: 100%;
    }

    #team-header {
        height: 5;
        padding: 1;
        border-bottom: solid $secondary;
    }

    #workers-table {
        height: 1fr;
        overflow-y: auto;
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
        """Refresh worker list from org connection."""
        # Check if org connected
        if not hasattr(self.app, 'org_connection') or self.app.org_connection is None:
            self._populate_no_org_state()
            return

        try:
            conn = self.app.org_connection
            workers = conn.get_workers()

            if not workers:
                self._populate_empty_workers_state()
                return

            self._populate_workers(workers)
        except Exception as e:
            logger.error(f"Error refreshing workers: {e}")
            self._populate_error_state(str(e))

    def _populate_no_org_state(self) -> None:
        """Populate table with no org connected message."""
        table = self.query_one("#workers-data", DataTable)
        table.clear()
        table.add_row("🟢", "No Org Connected", "-", "-", "Connect to an org to see workers", "-")

    def _populate_empty_workers_state(self) -> None:
        """Populate table with empty workers message."""
        table = self.query_one("#workers-data", DataTable)
        table.clear()
        # Show nothing - empty table for empty org

    def _populate_workers(self, workers: list[WorkerInfo]) -> None:
        """Populate table with actual worker data."""
        table = self.query_one("#workers-data", DataTable)
        table.clear()
        self._workers = workers

        for worker in self._workers:
            # Apply filter
            if not self._passes_filter(worker):
                continue

            # Status icon based on session state
            status_icon = self._get_status_icon(worker.session_state)

            # Format role with CEO indicator
            role = f"★ {worker.role}" if worker.is_ceo else worker.role

            # Current task or status with session mode
            task = worker.current_task or self._get_status_text(worker.session_state, worker.session_mode)

            table.add_row(
                status_icon,
                worker.name,
                role,
                worker.team_name,
                task,
                "[Chat]",
                key=worker.id,  # Store worker ID as row key
            )

    def _populate_error_state(self, error: str) -> None:
        """Populate table with error message."""
        table = self.query_one("#workers-data", DataTable)
        table.clear()
        table.add_row("🔴", "Error", "-", "-", f"Error loading workers: {error}", "-")

    def _get_status_icon(self, state: Optional[SessionState]) -> str:
        """Get status icon for session state.

        Gracefully handles unknown states without crashing.
        """
        if state is None:
            return "⚫"  # No session
        if state == SessionState.RUNNING:
            return "🟢"  # Active
        if state == SessionState.IDLE:
            return "🟡"  # Idle
        if state == SessionState.STARTING:
            return "🔵"  # Starting
        if state == SessionState.STOPPED:
            return "⚫"  # Stopped
        if state == SessionState.CRASHED:
            return "🔴"  # Crashed
        # Unknown state - return question mark instead of crashing
        return "❓"

    def _get_status_text(self, state: Optional[SessionState], mode: Optional[str] = None) -> str:
        """Get status text for session state with optional mode.

        Gracefully handles unknown states without crashing.

        Args:
            state: Current session state
            mode: Session mode ("autonomous" or "interactive")
        """
        mode_suffix = ""
        if mode and state in (SessionState.RUNNING, SessionState.IDLE):
            mode_suffix = f" [{mode[:4]}]"  # Show "auto" or "inte"

        if state is None:
            return "No session"
        if state == SessionState.RUNNING:
            return f"Working...{mode_suffix}"
        if state == SessionState.IDLE:
            return f"Idle{mode_suffix}"
        if state == SessionState.STARTING:
            return "Starting..."
        if state == SessionState.STOPPED:
            return "Stopped"
        if state == SessionState.CRASHED:
            return "Crashed"
        # Unknown state - return descriptive text instead of crashing
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
            # Get worker ID from row key - need to access .value attribute
            worker_id = event.cell_key.row_key.value

            # Find worker by ID
            worker = next((w for w in self._workers if w.id == worker_id), None)
            if worker:
                await self._open_worker_chat(worker)
            else:
                self.app.notify(f"Worker {worker_id} not found", severity="error")

    async def _cleanup_stale_session(self, worker: WorkerInfo) -> bool:
        """Auto-cleanup a stale session when validation fails.

        Clears stale tmux session name and unbinds worker-session binding.

        Args:
            worker: Worker with stale session

        Returns:
            True if cleanup succeeded, False otherwise
        """
        if not hasattr(self.app, 'org_connection') or self.app.org_connection is None:
            return False

        try:
            conn = self.app.org_connection
            # Delegate to org connection's cleanup method
            return conn.cleanup_stale_session(worker.id, worker.tmux_session_name)
        except Exception as e:
            logger.error(f"Failed to cleanup stale session for {worker.name}: {e}")
            return False

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
            # Attempt to attach to session (validates session exists)
            window_handle = terminal.attach_to_session(
                title=f"Chat with {worker.name}",
                session_name=worker.tmux_session_name,
            )

            # Track the window for potential cleanup
            self._open_windows[worker.id] = window_handle

            self.app.notify(f"Opened chat window with {worker.name}")
        except ValueError as e:
            # Session doesn't exist or is invalid - auto-cleanup stale session
            logger.warning(f"Session validation failed for {worker.name}: {e}")

            # Trigger automatic cleanup of stale session
            cleanup_success = await self._cleanup_stale_session(worker)

            if cleanup_success:
                self.app.notify(
                    f"Session for {worker.name} was stale and has been cleaned up. "
                    f"Use 'qn wrkr restart {worker.id}' to spawn a new session.",
                    severity="warning",
                    timeout=10,
                )
            else:
                self.app.notify(
                    f"Session for {worker.name} is dead or invalid. "
                    f"Use 'qn wrkr cleanup {worker.id}' then 'qn wrkr restart {worker.id}' to recover.",
                    severity="error",
                    timeout=10,
                )

            # Refresh workers to show updated state
            await self.refresh_workers()
        except Exception as e:
            # Other errors (AppleScript, permissions, etc.)
            logger.error(f"Failed to open chat for {worker.name}: {e}")
            self.app.notify(f"Failed to open chat: {e}", severity="error")
