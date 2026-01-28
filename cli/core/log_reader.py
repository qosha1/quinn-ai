"""
Log reader API for querying structured log files.

Provides efficient reading and filtering of JSON log files.
"""

import json
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from .constants import LIVE_DIR, LOG_DATE_FORMAT


class LogReader:
    """Read and query structured log files.

    Efficiently reads JSON log files with filtering by component, level,
    date range, and keyword search. Supports pagination and tailing.

    Usage:
        reader = LogReader(org_path)

        # List available data
        components = reader.list_components()
        dates = reader.list_dates(component="worker")

        # Read logs with filters
        logs = reader.read_logs(
            component="worker",
            level="ERROR",
            start_date=date(2026, 1, 28),
            limit=100
        )

        # Search logs
        results = reader.search_logs(query="lifecycle", component="worker")

        # Tail recent logs
        recent = reader.tail_logs(component="worker", lines=50)
    """

    def __init__(self, org_path: Path):
        """Initialize log reader.

        Args:
            org_path: Path to org folder.
        """
        self.org_path = org_path
        self.logs_dir = org_path / LIVE_DIR / "logs"

    def list_components(self) -> list[str]:
        """List components that have logs.

        Returns:
            List of component names with log directories.
        """
        if not self.logs_dir.exists():
            return []

        components = []
        for item in self.logs_dir.iterdir():
            if item.is_dir() and item.name != "__pycache__":
                components.append(item.name)

        return sorted(components)

    def list_dates(
        self,
        component: Optional[str] = None
    ) -> list[date]:
        """List dates for which logs exist.

        Args:
            component: Optional component to filter by. If None, lists
                      dates across all components.

        Returns:
            List of dates in descending order (newest first).
        """
        dates_set = set()

        if component:
            # List dates for specific component
            component_dirs = self._get_component_dirs(component)
            for comp_dir in component_dirs:
                if comp_dir.exists():
                    for log_file in comp_dir.glob("*.json"):
                        try:
                            date_str = log_file.stem
                            file_date = datetime.strptime(date_str, LOG_DATE_FORMAT).date()
                            dates_set.add(file_date)
                        except ValueError:
                            # Skip files that don't match date format
                            continue
        else:
            # List dates across all components
            for comp in self.list_components():
                component_dirs = self._get_component_dirs(comp)
                for comp_dir in component_dirs:
                    if comp_dir.exists():
                        for log_file in comp_dir.glob("*.json"):
                            try:
                                date_str = log_file.stem
                                file_date = datetime.strptime(date_str, LOG_DATE_FORMAT).date()
                                dates_set.add(file_date)
                            except ValueError:
                                continue

        # Return sorted descending (newest first)
        return sorted(dates_set, reverse=True)

    def read_logs(
        self,
        component: Optional[str] = None,
        level: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """Read log entries with filters.

        Args:
            component: Filter by component name. If None, reads all components.
            level: Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
            start_date: Filter logs from this date onwards.
            end_date: Filter logs up to this date.
            limit: Maximum number of entries to return.
            offset: Number of entries to skip.

        Returns:
            List of log entries as dictionaries, sorted by timestamp descending.
        """
        all_logs = []

        # Determine components to read
        if component:
            components = [component]
        else:
            components = self.list_components()

        # Determine date range
        if start_date or end_date:
            dates_to_read = self.list_dates(component=component)
            if start_date:
                dates_to_read = [d for d in dates_to_read if d >= start_date]
            if end_date:
                dates_to_read = [d for d in dates_to_read if d <= end_date]
        else:
            dates_to_read = self.list_dates(component=component)

        # Read log files
        for comp in components:
            component_dirs = self._get_component_dirs(comp)
            for comp_dir in component_dirs:
                if not comp_dir.exists():
                    continue

                for log_date in dates_to_read:
                    log_file = comp_dir / f"{log_date.strftime(LOG_DATE_FORMAT)}.json"
                    if log_file.exists():
                        logs_from_file = self._read_log_file(
                            log_file,
                            level_filter=level
                        )
                        all_logs.extend(logs_from_file)

        # Sort by timestamp descending (newest first)
        all_logs.sort(
            key=lambda x: x.get("timestamp", ""),
            reverse=True
        )

        # Apply offset and limit
        return all_logs[offset:offset + limit]

    def search_logs(
        self,
        query: str,
        component: Optional[str] = None,
        level: Optional[str] = None,
        start_date: Optional[date] = None,
    ) -> list[dict]:
        """Search logs by keyword.

        Performs case-insensitive search across message, context, and subcomponent fields.

        Args:
            query: Search keyword.
            component: Optional component filter.
            level: Optional level filter.
            start_date: Optional start date filter.

        Returns:
            List of matching log entries, sorted by timestamp descending.
        """
        # Read all matching logs
        all_logs = self.read_logs(
            component=component,
            level=level,
            start_date=start_date,
            limit=10000  # Large limit for search
        )

        # Filter by keyword
        query_lower = query.lower()
        matching_logs = []

        for log in all_logs:
            # Search in message
            if query_lower in log.get("message", "").lower():
                matching_logs.append(log)
                continue

            # Search in subcomponent
            if query_lower in log.get("subcomponent", "").lower():
                matching_logs.append(log)
                continue

            # Search in context (convert to string)
            context_str = str(log.get("context", {})).lower()
            if query_lower in context_str:
                matching_logs.append(log)
                continue

        return matching_logs

    def tail_logs(
        self,
        component: Optional[str] = None,
        lines: int = 50,
    ) -> list[dict]:
        """Get most recent log entries.

        Args:
            component: Optional component filter.
            lines: Number of recent entries to return.

        Returns:
            List of most recent log entries, sorted by timestamp descending.
        """
        return self.read_logs(
            component=component,
            limit=lines,
            offset=0
        )

    def _get_component_dirs(self, component: str) -> list[Path]:
        """Get possible directory paths for a component.

        Handles both singular and plural forms (worker/workers, session/sessions).

        Args:
            component: Component name.

        Returns:
            List of possible directory paths.
        """
        dirs = []

        # Exact match
        dirs.append(self.logs_dir / component)

        # Try plural form for worker/session
        if component in ["worker", "session"]:
            dirs.append(self.logs_dir / f"{component}s")

        # Try singular form if component ends with 's'
        if component.endswith("s"):
            dirs.append(self.logs_dir / component[:-1])

        return dirs

    def _read_log_file(
        self,
        log_file: Path,
        level_filter: Optional[str] = None,
    ) -> list[dict]:
        """Read and parse a JSON log file.

        Uses streaming reads for memory efficiency.

        Args:
            log_file: Path to JSONL log file.
            level_filter: Optional level to filter by.

        Returns:
            List of log entries from file.
        """
        logs = []

        try:
            with open(log_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        entry = json.loads(line)

                        # Apply level filter
                        if level_filter and entry.get("level") != level_filter:
                            continue

                        logs.append(entry)
                    except json.JSONDecodeError:
                        # Skip invalid JSON lines
                        continue
        except (OSError, IOError):
            # Skip files that can't be read
            pass

        return logs
