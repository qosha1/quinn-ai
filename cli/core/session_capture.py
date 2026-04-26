"""Provider-agnostic session activity capture.

Captures worker session activity by reading tmux pane output, regardless
of which AI provider (Claude, Gemini, Codex, etc.) is running in the session.

This is the ONLY way to stay provider-agnostic - we capture the terminal
output, not the provider's internal state.
"""

import logging
import re
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from cli.core.activity_tracker import ActivityTracker

_logger = logging.getLogger(__name__)


class SessionCaptureService:
    """Background service that captures tmux session activity."""

    def __init__(
        self,
        org_path: Path,
        capture_interval: int = 10,  # Capture every 10 seconds
    ):
        """Initialize session capture service.

        Args:
            org_path: Path to organization directory
            capture_interval: How often to capture pane output (seconds)
        """
        self.org_path = org_path
        self.capture_interval = capture_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._last_captured = {}  # worker_id -> last captured line count

    def start(self) -> None:
        """Start the session capture service in a background thread."""
        if self._running:
            _logger.warning("Session capture service already running")
            return

        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._capture_loop,
            daemon=True,
            name="SessionCapture"
        )
        self._thread.start()
        _logger.info(f"Session capture service started (interval: {self.capture_interval}s)")

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the session capture service.

        Args:
            timeout: Maximum time to wait for service to stop (seconds)
        """
        if not self._running:
            return

        _logger.info("Stopping session capture service...")
        self._running = False
        self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                _logger.warning("Session capture service did not stop gracefully")

        _logger.info("Session capture service stopped")

    def is_running(self) -> bool:
        """Check if service is running.

        Returns:
            True if service is running
        """
        return self._running

    def _capture_loop(self) -> None:
        """Main capture loop (runs in background thread)."""
        _logger.debug("Session capture loop started")

        while self._running:
            try:
                self._capture_all_sessions()
            except Exception as e:
                _logger.error(f"Error in session capture: {e}", exc_info=True)

            # Wait for next capture interval or stop signal
            self._stop_event.wait(timeout=self.capture_interval)

        _logger.debug("Session capture loop exited")

    def _capture_all_sessions(self) -> None:
        """Capture output from all active worker tmux sessions."""
        from cli.core.db import open_database, get_org_db_path

        db_path = get_org_db_path(self.org_path)
        if not db_path.exists():
            return

        db = open_database(db_path)
        try:
            # Get all active workers with sessions
            rows = db.fetchall(
                """SELECT w.id, w.name
                   FROM workers w
                   JOIN sessions s ON s.worker_id = w.id
                   WHERE w.status IN ('onboarding', 'active')
                   AND s.state IN ('running', 'idle')"""
            )

            for worker_row in rows:
                worker_id = worker_row["id"]
                worker_name = worker_row["name"]

                try:
                    self._capture_worker_session(worker_id, worker_name)
                except Exception as e:
                    _logger.debug(f"Failed to capture session for {worker_name}: {e}")

        finally:
            db.close()

    def _capture_worker_session(self, worker_id: str, worker_name: str) -> None:
        """Capture output from a worker's tmux session.

        Args:
            worker_id: Worker ID
            worker_name: Worker name
        """
        tmux_session = f"qn-{worker_id}"

        # Capture pane output (last 100 lines)
        try:
            result = subprocess.run(
                ["tmux", "capture-pane", "-t", tmux_session, "-p", "-S", "-100"],
                capture_output=True,
                text=True,
                timeout=2
            )

            if result.returncode != 0:
                # Session doesn't exist or isn't accessible
                return

            output = result.stdout

            # Parse the output and extract meaningful activity
            self._parse_and_log_activity(worker_id, worker_name, output)

        except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as e:
            _logger.debug(f"Failed to capture tmux pane for {worker_name}: {e}")

    def _parse_and_log_activity(
        self,
        worker_id: str,
        worker_name: str,
        output: str
    ) -> None:
        """Parse tmux output and log activity.

        Args:
            worker_id: Worker ID
            worker_name: Worker name
            output: Tmux pane output
        """
        tracker = ActivityTracker(self.org_path, worker_id)
        lines = output.split("\n")

        # Track what we've already processed
        last_line_count = self._last_captured.get(worker_id, 0)
        current_line_count = len(lines)

        # Only process new lines
        if current_line_count <= last_line_count:
            return

        new_lines = lines[last_line_count:]
        self._last_captured[worker_id] = current_line_count

        # Parse activity from new lines
        for line in new_lines:
            line = line.strip()
            if not line:
                continue

            # Detect bash commands (lines starting with common prompts)
            if self._is_bash_command(line):
                command = self._extract_command(line)
                if command:
                    tracker.log_command(command, success=True)

            # Detect file operations
            file_edit = self._extract_file_edit(line)
            if file_edit:
                tracker.log_file_edit(file_edit["path"], file_edit["action"])

            # Detect task/bead operations
            task_op = self._extract_task_operation(line)
            if task_op:
                tracker.log_task_progress(
                    task_op["task_id"],
                    task_op["status"],
                    task_op.get("notes")
                )

            # Detect decisions/thoughts (AI responses with thinking indicators)
            if self._is_ai_thinking(line):
                tracker.log_message(line[:200], context="AI reasoning")

    def _is_bash_command(self, line: str) -> bool:
        """Check if line looks like a bash command.

        Args:
            line: Line of output

        Returns:
            True if line appears to be a bash command
        """
        # Common bash prompt patterns
        prompts = [
            r"^\$\s+",  # $ prompt
            r"^bash-\d+\.\d+\$\s+",  # bash-3.2$ prompt
            r"^❯\s+",  # modern prompt
        ]

        return any(re.match(pattern, line) for pattern in prompts)

    def _extract_command(self, line: str) -> Optional[str]:
        """Extract command from bash prompt line.

        Args:
            line: Line of output

        Returns:
            Command string or None
        """
        # Remove common prompts
        line = re.sub(r"^(\$|bash-\d+\.\d+\$|❯)\s+", "", line)
        return line if line else None

    def _extract_file_edit(self, line: str) -> Optional[dict]:
        """Extract file edit information from output.

        Args:
            line: Line of output

        Returns:
            Dict with path and action, or None
        """
        # Look for common editor patterns
        patterns = [
            (r"Edit\s+(.+\.(?:py|js|ts|md|json|yaml|txt))", "edit"),
            (r"Write\s+(.+\.(?:py|js|ts|md|json|yaml|txt))", "create"),
            (r"Read\s+(.+\.(?:py|js|ts|md|json|yaml|txt))", "read"),
        ]

        for pattern, action in patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                return {"path": match.group(1), "action": action}

        return None

    def _extract_task_operation(self, line: str) -> Optional[dict]:
        """Extract task/bead operation from output.

        Args:
            line: Line of output

        Returns:
            Dict with task_id and status, or None
        """
        # Look for bd command patterns
        patterns = [
            (r"bd\s+update\s+([a-z0-9-]+)\s+--status=(\w+)", "status_change"),
            (r"bd\s+close\s+([a-z0-9-]+)", "completed"),
            (r"✓\s+Created\s+issue:\s+([a-z0-9-]+)", "created"),
        ]

        for pattern, operation in patterns:
            match = re.search(pattern, line)
            if match:
                if operation == "status_change":
                    return {
                        "task_id": match.group(1),
                        "status": match.group(2),
                        "notes": None
                    }
                elif operation == "completed":
                    return {
                        "task_id": match.group(1),
                        "status": "completed",
                        "notes": None
                    }
                elif operation == "created":
                    return {
                        "task_id": match.group(1),
                        "status": "created",
                        "notes": None
                    }

        return None

    def _is_ai_thinking(self, line: str) -> bool:
        """Check if line contains AI thinking/reasoning.

        Args:
            line: Line of output

        Returns:
            True if line appears to be AI reasoning
        """
        # Look for thinking indicators
        indicators = [
            "⏺",  # Claude Code indicator
            "✶",  # Thinking indicator
            "Sketching",
            "Fermenting",
            "I'll",
            "I'm",
            "Let me",
        ]

        return any(indicator in line for indicator in indicators)
