"""
Log formatters for structured logging.

Provides JSON formatters for machine-readable log output.
"""

import json
import logging
import socket
import threading
from datetime import datetime, timezone
from typing import Optional


class StructuredJSONFormatter(logging.Formatter):
    """Format log records as structured JSON.

    Outputs single-line JSON (JSONL format) with fields:
    - timestamp: ISO 8601 UTC timestamp
    - level: Log level name (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    - component: Component name (cli, worker, session, board, system)
    - subcomponent: Optional subcomponent name
    - event_type: Optional semantic event type
    - message: Human-readable message
    - context: Event-specific structured data
    - metadata: System metadata (thread, pid, hostname)

    Usage:
        formatter = StructuredJSONFormatter(
            component="worker",
            subcomponent="lifecycle"
        )
        handler.setFormatter(formatter)

        logger.info(
            "Worker status changed",
            extra={
                "event_type": "status_change",
                "context": {"worker_id": "wrkr-123", "status": "active"}
            }
        )
    """

    def __init__(
        self,
        component: str,
        subcomponent: Optional[str] = None,
    ):
        """Initialize formatter.

        Args:
            component: Component name (cli, worker, session, board, system).
            subcomponent: Optional subcomponent name.
        """
        super().__init__()
        self.component = component
        self.subcomponent = subcomponent
        self.hostname = socket.gethostname()

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON string.

        Args:
            record: Log record to format.

        Returns:
            Single-line JSON string.
        """
        # Build base entry
        entry = {
            "timestamp": self._format_timestamp(record),
            "level": record.levelname,
            "component": self.component,
            "message": record.getMessage(),
        }

        # Add optional fields
        if self.subcomponent:
            entry["subcomponent"] = self.subcomponent

        # Extract custom fields from record
        if hasattr(record, "event_type"):
            entry["event_type"] = record.event_type

        if hasattr(record, "context"):
            entry["context"] = record.context
        else:
            entry["context"] = {}

        # Add metadata
        entry["metadata"] = {
            "thread": threading.current_thread().name,
            "pid": record.process,
            "hostname": self.hostname,
        }

        # Handle exception info
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)

        # Return single-line JSON
        return json.dumps(entry, ensure_ascii=False)

    def _format_timestamp(self, record: logging.LogRecord) -> str:
        """Format timestamp as ISO 8601 UTC.

        Args:
            record: Log record.

        Returns:
            ISO 8601 formatted timestamp with Z suffix.
        """
        # Convert record.created (float timestamp) to datetime
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        # Format as ISO 8601 with Z suffix
        return dt.isoformat().replace('+00:00', 'Z')
