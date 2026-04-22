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
from ..logging_config import get_board_logger

logger = get_board_logger(__name__)


class TeamView(VerticalScroll):
    """Team view with worker list and jump-in buttons."""

    DEFAULT_CSS = """
    TeamView {
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
        # Track open session windows for cleanup
        self._open_windows: dict[str, any] = {}  # worker_id -> WindowHandle
        self._workers: list[WorkerInfo] = []
        self._current_filter = "all"
        self._refresh_interval_seconds = 2  # Auto-refresh every 2 seconds
        self._spawning_session: set[str] = set()  # worker IDs currently spawning

    def compose(self) -> ComposeResult:
        with Container(id="team-header"):
            yield Label("Team Members", classes="panel-title")
            with Horizontal():
                yield Button("All", id="filter-all", classes="filter-btn", variant="primary")
                yield Button("Active", id="filter-active", classes="filter-btn")
                yield Button("Idle", id="filter-idle", classes="filter-btn")
                yield Button("+ Hire Worker", id="hire-worker-btn", variant="success", classes="filter-btn")

        with Container(id="workers-table"):
            table = DataTable(id="workers-data")
            table.add_columns("Status", "Name", "Role", "Team", "Manager", "Actions")
            yield table

    async def on_mount(self) -> None:
        """Load workers when view mounts."""
        await self.refresh_workers()
        # Start auto-refresh timer
        self.set_interval(self._refresh_interval_seconds, self._auto_refresh)

    async def _auto_refresh(self) -> None:
        """Auto-refresh callback for timer."""
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

        # Build manager name lookup
        manager_names = {w.id: w.name for w in workers}

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

            # Manager name
            manager = manager_names.get(worker.manager_id, "None") if worker.manager_id else "None"

            # Actions - different options based on worker type
            if worker.is_ceo:
                actions = "[Chat]"
            elif worker.manager_id is None:  # Manager (non-CEO)
                actions = "[Chat] [Fire] [Demote]"
            else:  # Regular worker
                actions = "[Chat] [Fire] [Promote]"

            table.add_row(
                status_icon,
                worker.name,
                role,
                worker.team_name,
                manager,
                actions,
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
        """Handle button presses."""
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
        elif event.button.id == "hire-worker-btn":
            await self._hire_worker()

    async def on_data_table_cell_selected(self, event: DataTable.CellSelected) -> None:
        """Handle cell selection - detect which action was clicked."""
        if event.coordinate.column == 5:  # Actions column
            # Get worker ID from row key - need to access .value attribute
            worker_id = event.cell_key.row_key.value

            # Find worker by ID
            worker = next((w for w in self._workers if w.id == worker_id), None)
            if not worker:
                self.app.notify(f"Worker {worker_id} not found", severity="error")
                return

            # Get cell value to determine which action
            cell_value = event.value

            # Parse action from cell text
            if "[Chat]" in cell_value:
                # For now, always open chat on click
                # TODO: Could parse click position to determine exact action
                await self._open_worker_chat(worker)
            elif "[Fire]" in cell_value:
                # Show menu or directly fire (for now, let's show a confirmation)
                await self._show_worker_actions_menu(worker)
            elif "[Promote]" in cell_value or "[Demote]" in cell_value:
                await self._show_worker_actions_menu(worker)

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
        """Open a chat window with a worker.

        If the worker has no active session, spawns one first.
        If the session is stale, cleans it up and spawns a new one.
        """
        if worker.id in self._spawning_session:
            return  # Already spawning

        tmux_session = worker.tmux_session_name

        # No session? Start one.
        if not tmux_session:
            self._spawning_session.add(worker.id)
            try:
                tmux_session = await self._ensure_worker_session(worker)
            finally:
                self._spawning_session.discard(worker.id)
            if not tmux_session:
                return

        from ..terminals import get_terminal_provider

        terminal = get_terminal_provider()
        if terminal is None:
            self.app.notify("No terminal available", severity="error")
            return

        try:
            window_handle = terminal.attach_to_session(
                title=f"Chat with {worker.name}",
                session_name=tmux_session,
            )
            self._open_windows[worker.id] = window_handle

        except ValueError:
            # Session is stale — clean it up and spawn a fresh one
            logger.warning(f"Stale session for {worker.name}, respawning...")
            await self._cleanup_stale_session(worker)

            self._spawning_session.add(worker.id)
            try:
                tmux_session = await self._ensure_worker_session(worker)
            finally:
                self._spawning_session.discard(worker.id)
            if not tmux_session:
                return

            try:
                window_handle = terminal.attach_to_session(
                    title=f"Chat with {worker.name}",
                    session_name=tmux_session,
                )
                self._open_windows[worker.id] = window_handle
            except Exception as e:
                logger.error(f"Failed to open chat after respawn for {worker.name}: {e}")
                self.app.notify(f"Failed to open chat: {e}", severity="error")

        except Exception as e:
            logger.error(f"Failed to open chat for {worker.name}: {e}")
            self.app.notify(f"Failed to open chat: {e}", severity="error")

    async def _ensure_worker_session(self, worker: WorkerInfo) -> str | None:
        """Ensure a worker has a running session, spawning if needed.

        Args:
            worker: WorkerInfo to ensure session for

        Returns:
            tmux_session_name if session is running, None on failure
        """
        if not hasattr(self.app, 'org_connection') or self.app.org_connection is None:
            self.app.notify("No org connected", severity="error")
            return None

        conn = self.app.org_connection
        self.app.notify(f"Starting session for {worker.name}...", severity="information")

        try:
            bg = self.app.run_worker(
                lambda: conn.restart_worker_session(worker.id),
                thread=True,
            )
            success, tmux_name = await bg.wait()
        except Exception as e:
            self.app.notify(f"Failed to start session: {e}", severity="error")
            return None

        if not success or not tmux_name:
            self.app.notify(
                f"Failed to start session for {worker.name}",
                severity="error",
            )
            return None

        self.app.notify(f"Session started for {worker.name}", severity="success")
        await self.refresh_workers()
        return tmux_name

    async def _hire_worker(self) -> None:
        """Hire a new worker.

        Shows input prompts for worker name, role, and manager selection.
        """
        from textual.screen import ModalScreen
        from textual.widgets import Input

        # For now, show a notification that this needs CLI
        # TODO: Implement proper modal dialog with form
        self.app.notify(
            "Worker hiring coming soon. For now, use: qn org hire --name=<name> --role=<role> --manager=<manager>",
            severity="information",
            timeout=8
        )

    async def _show_worker_actions_menu(self, worker: WorkerInfo) -> None:
        """Show actions menu for a worker.

        Displays Fire/Promote/Demote options based on worker type.
        """
        # For now, show a simple notification
        # TODO: Implement proper menu/dialog

        actions = []
        if not worker.is_ceo:
            actions.append("Fire")
        if worker.manager_id is None and not worker.is_ceo:  # Manager
            actions.append("Demote")
        elif worker.manager_id is not None:  # Regular worker
            actions.append("Promote")

        self.app.notify(
            f"Worker actions for {worker.name}: {', '.join(actions)}. Use CLI for now: qn org fire {worker.id}",
            severity="information",
            timeout=6
        )

    async def _fire_worker(self, worker: WorkerInfo) -> None:
        """Fire a worker.

        Shows confirmation dialog and executes qn org fire command.
        """
        if worker.is_ceo:
            self.app.notify("Cannot fire the CEO", severity="error")
            return

        # TODO: Show confirmation dialog
        # For now, use subprocess directly
        import subprocess

        self.app.notify(f"Firing {worker.name}...", severity="information")

        try:
            result = subprocess.run(
                ["qn", "org", "fire", worker.id, "--force", "--org-path", str(self.app.org_connection.org_path)],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                self.app.notify(f"Fired {worker.name} successfully", severity="success")
                await self.refresh_workers()
            else:
                error = result.stderr or result.stdout or "Unknown error"
                self.app.notify(f"Failed to fire {worker.name}: {error}", severity="error")
        except Exception as e:
            self.app.notify(f"Error firing worker: {e}", severity="error")

    async def _promote_worker(self, worker: WorkerInfo) -> None:
        """Promote a worker to manager.

        Shows confirmation and executes qn org promote command.
        """
        if worker.is_ceo or worker.manager_id is None:
            self.app.notify("Worker is already a manager or CEO", severity="warning")
            return

        self.app.notify(
            f"Worker promotion coming soon. Use: qn org promote {worker.id}",
            severity="information",
            timeout=6
        )

    async def _demote_worker(self, worker: WorkerInfo) -> None:
        """Demote a manager to regular worker.

        Shows confirmation and executes qn org demote command.
        """
        if worker.is_ceo:
            self.app.notify("Cannot demote the CEO", severity="error")
            return

        if worker.manager_id is not None:
            self.app.notify("Worker is not a manager", severity="warning")
            return

        self.app.notify(
            f"Worker demotion coming soon. Use: qn org demote {worker.id}",
            severity="information",
            timeout=6
        )

    def export_as_text(self) -> str:
        """Export team view content as plain text.

        Returns:
            Formatted text representation of team
        """
        lines = []
        lines.append("=" * 80)
        lines.append("QUINNAI BOARD - TEAM")
        lines.append("=" * 80)
        lines.append("")

        # Filter info
        lines.append(f"Filter: {self._current_filter.capitalize()}")
        lines.append("")

        # Workers
        if not self._workers:
            lines.append("No workers in org")
        else:
            # Apply filter to get displayed workers
            displayed_workers = [w for w in self._workers if self._passes_filter(w)]

            if not displayed_workers:
                lines.append(f"No workers match '{self._current_filter}' filter")
            else:
                lines.append(f"Workers ({len(displayed_workers)} displayed, {len(self._workers)} total):")
                lines.append("")

                # Build manager name lookup
                manager_names = {w.id: w.name for w in self._workers}

                for worker in displayed_workers:
                    lines.append("-" * 80)
                    lines.append(f"Name: {worker.name}")
                    lines.append(f"ID: {worker.id}")
                    role_prefix = "★ " if worker.is_ceo else ""
                    lines.append(f"Role: {role_prefix}{worker.role}")
                    lines.append(f"Team: {worker.team_name}")

                    # Manager
                    manager = manager_names.get(worker.manager_id, "None") if worker.manager_id else "None"
                    lines.append(f"Manager: {manager}")

                    # Session state
                    status_text = self._get_status_text(worker.session_state, worker.session_mode)
                    lines.append(f"Status: {status_text}")

                    if worker.session_state:
                        lines.append(f"Session State: {worker.session_state.value}")

                    if worker.session_mode:
                        lines.append(f"Session Mode: {worker.session_mode}")

                    if worker.tmux_session_name:
                        lines.append(f"Tmux Session: {worker.tmux_session_name}")

                    # Current task
                    if worker.current_task:
                        lines.append(f"Current Task: {worker.current_task}")

                    lines.append("")

        lines.append("=" * 80)
        return "\n".join(lines)
