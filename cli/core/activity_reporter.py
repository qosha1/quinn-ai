"""Activity reporting service.

Periodically sends worker activity summaries to the board-channel
so the board can see what workers are doing.
"""

import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.db import Database, open_database, get_org_db_path
from core.activity_tracker import ActivityTracker

_logger = logging.getLogger(__name__)


class ActivityReporter:
    """Background service that sends activity summaries to the board."""

    def __init__(
        self,
        org_path: Path,
        report_interval: int = 300,  # 5 minutes
    ):
        """Initialize activity reporter.

        Args:
            org_path: Path to organization directory
            report_interval: How often to send reports (seconds)
        """
        self.org_path = org_path
        self.report_interval = report_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        """Start the activity reporter in a background thread."""
        if self._running:
            _logger.warning("Activity reporter already running")
            return

        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._report_loop,
            daemon=True,
            name="ActivityReporter"
        )
        self._thread.start()
        _logger.info(f"Activity reporter started (interval: {self.report_interval}s)")

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the activity reporter.

        Args:
            timeout: Maximum time to wait for reporter to stop (seconds)
        """
        if not self._running:
            return

        _logger.info("Stopping activity reporter...")
        self._running = False
        self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                _logger.warning("Activity reporter did not stop gracefully")

        _logger.info("Activity reporter stopped")

    def is_running(self) -> bool:
        """Check if reporter is running.

        Returns:
            True if reporter is running
        """
        return self._running

    def _report_loop(self) -> None:
        """Main reporting loop (runs in background thread)."""
        _logger.debug("Activity reporter loop started")

        while self._running:
            try:
                self._send_activity_reports()
            except Exception as e:
                _logger.error(f"Error in activity reporter: {e}", exc_info=True)

            # Wait for next report interval or stop signal
            self._stop_event.wait(timeout=self.report_interval)

        _logger.debug("Activity reporter loop exited")

    def _send_activity_reports(self) -> None:
        """Send activity summaries for all active workers to board-channel."""
        db_path = get_org_db_path(self.org_path)
        if not db_path.exists():
            return

        db = open_database(db_path)
        try:
            # Get all active workers
            rows = db.fetchall(
                """SELECT id, name, role
                   FROM workers
                   WHERE status IN ('onboarding', 'active')"""
            )

            if not rows:
                return

            # Get board-channel
            channel_row = db.fetchone(
                "SELECT id FROM channels WHERE name = 'board-channel'"
            )
            if not channel_row:
                _logger.warning("No board-channel found, skipping activity reports")
                return

            board_channel_id = channel_row["id"]

            # Send report for each worker with activity
            for worker_row in rows:
                worker_id = worker_row["id"]
                worker_name = worker_row["name"]
                worker_role = worker_row["role"]

                tracker = ActivityTracker(self.org_path, worker_id)

                # Get activity from last reporting interval
                report_minutes = int(self.report_interval / 60) + 5  # Add buffer
                recent_activity = tracker.get_recent_activity(minutes=report_minutes)

                # Only send if there's actual activity
                if not recent_activity:
                    continue

                # Create activity summary
                summary = tracker.create_activity_summary(minutes=report_minutes)

                # Create message in board-channel
                from core.queries import create_message, generate_id
                from core.notifications import create_notification_bead

                message_content = f"## {worker_name} ({worker_role}) Activity\n\n{summary}"

                message = create_message(
                    db=db,
                    channel_id=board_channel_id,
                    from_worker_id=worker_id,
                    content=message_content,
                    priority=2,  # Normal priority
                    time_sensitivity="routine",
                    message_id=generate_id("msg"),
                )

                # Create notification bead for the board
                # The board isn't a worker, so we create a notification without worker_id
                # This will show up in the board UI inbox
                db.execute(
                    """INSERT INTO notification_beads
                       (id, message_id, channel_id, created_at, status)
                       VALUES (?, ?, ?, ?, 'pending')""",
                    (generate_id("notif"), message.id, board_channel_id, datetime.now())
                )
                db.connection.commit()

                _logger.info(f"Sent activity report for {worker_name} to board")

        finally:
            db.close()
