"""Activity reporting service.

Periodically sends worker activity summaries to the activity-feed channel
so the board can monitor what workers are doing.

Optionally creates beads for activity summaries to provide queryable history.
"""

import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from cli.core.db import Database, open_database, get_org_db_path
from cli.core.activity_tracker import ActivityTracker
from cli.core.bd_wrapper import run_bd

_logger = logging.getLogger(__name__)


class ActivityReporter:
    """Background service that sends activity summaries to the board."""

    def __init__(
        self,
        org_path: Path,
        report_interval: int = 300,  # 5 minutes
        create_beads: bool = True,  # Create activity summary beads
    ):
        """Initialize activity reporter.

        Args:
            org_path: Path to organization directory
            report_interval: How often to send reports (seconds)
            create_beads: Whether to create beads for activity summaries
        """
        self.org_path = org_path
        self.report_interval = report_interval
        self.create_beads = create_beads
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
        """Send activity summaries for all active workers to activity-feed channel."""
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

            # Get or create activity-feed channel
            from cli.core.constants import DEFAULT_ACTIVITY_FEED_CHANNEL
            from cli.core.queries.channel import get_channel_by_name, create_channel

            channel = get_channel_by_name(db, DEFAULT_ACTIVITY_FEED_CHANNEL)
            if not channel:
                _logger.info(f"Creating {DEFAULT_ACTIVITY_FEED_CHANNEL} channel")
                channel = create_channel(db, DEFAULT_ACTIVITY_FEED_CHANNEL, "topic")

            activity_feed_channel_id = channel.id

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
                from cli.core.queries import create_message, generate_id

                message_content = f"## {worker_name} ({worker_role}) Activity\n\n{summary}"

                message = create_message(
                    db=db,
                    channel_id=activity_feed_channel_id,
                    from_worker_id=worker_id,
                    content=message_content,
                    priority=2,  # Normal priority
                    time_sensitivity="hours",  # Can be read within hours
                    message_id=generate_id("msg"),
                )

                # Note: We don't create notification_beads for activity reports
                # Activity feed is for monitoring only, not actionable notifications
                # Notification beads are only created for escalations and direct messages

                _logger.info(f"Sent activity report for {worker_name} to activity feed")

                # Optionally create a bead for queryable activity history
                if self.create_beads:
                    self._create_activity_bead(
                        worker_id=worker_id,
                        worker_name=worker_name,
                        summary=summary,
                        activity_count=len(recent_activity),
                    )

        finally:
            db.close()

    def _create_activity_bead(
        self,
        worker_id: str,
        worker_name: str,
        summary: str,
        activity_count: int,
    ) -> None:
        """Create a bead for activity summary.

        Args:
            worker_id: Worker ID
            worker_name: Worker name
            summary: Activity summary markdown
            activity_count: Number of activity entries
        """
        try:
            now = datetime.now()
            timestamp = now.strftime("%Y-%m-%d %H:%M")

            # Create bead with activity summary
            args = [
                "create",
                f"Activity: {worker_name} ({activity_count} actions)",
                "--type=event",
                f"--meta=worker_id={worker_id}",
                f"--meta=timestamp={now.isoformat()}",
                f"--meta=activity_count={activity_count}",
                f"--desc={summary}",
            ]

            run_bd(
                args=args,
                org_path=self.org_path,
                worker_id="system",  # System-level bead creation
                skip_permission_check=True,  # System can always create beads
                capture_output=True,
            )

            _logger.debug(f"Created activity bead for {worker_name}")

        except Exception as e:
            _logger.warning(f"Failed to create activity bead for {worker_name}: {e}")
