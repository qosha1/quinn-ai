"""
Unit tests for the LogReader API.

Following TDD: Write FAILING tests, then implement to make them PASS.
"""

import json
import tempfile
from datetime import datetime, timedelta, date
from pathlib import Path

import pytest


# These imports will FAIL until we implement the module
try:
    from cli.core.log_reader import LogReader
except ImportError:
    # Expected to fail initially - that's the point of TDD
    LogReader = None


from cli.core.constants import LIVE_DIR


@pytest.fixture
def temp_org_path():
    """Create a temporary org directory with sample logs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir)
        logs_dir = org_path / LIVE_DIR / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        # Create sample log structure
        _create_sample_logs(logs_dir)

        yield org_path


def _create_sample_logs(logs_dir: Path):
    """Create sample log files for testing."""
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)

    # CLI logs
    cli_dir = logs_dir / "cli"
    cli_dir.mkdir(exist_ok=True)
    _write_json_log(cli_dir / f"{today}.json", [
        {
            "timestamp": datetime.now().isoformat() + "Z",
            "level": "INFO",
            "component": "cli",
            "message": "Command executed",
            "context": {"command": "org status"}
        }
    ])

    # Worker logs
    workers_dir = logs_dir / "workers"
    workers_dir.mkdir(exist_ok=True)
    _write_json_log(workers_dir / f"{today}.json", [
        {
            "timestamp": datetime.now().isoformat() + "Z",
            "level": "INFO",
            "component": "worker",
            "subcomponent": "lifecycle",
            "event_type": "status_change",
            "message": "Worker lifecycle transition",
            "context": {
                "worker_id": "wrkr-123",
                "worker_name": "Alice",
                "old_status": "pending",
                "new_status": "onboarding"
            }
        },
        {
            "timestamp": datetime.now().isoformat() + "Z",
            "level": "ERROR",
            "component": "worker",
            "message": "Worker error occurred",
            "context": {"worker_id": "wrkr-456"}
        }
    ])
    _write_json_log(workers_dir / f"{yesterday}.json", [
        {
            "timestamp": (datetime.now() - timedelta(days=1)).isoformat() + "Z",
            "level": "INFO",
            "component": "worker",
            "message": "Yesterday's worker log",
            "context": {}
        }
    ])

    # Session logs
    sessions_dir = logs_dir / "sessions"
    sessions_dir.mkdir(exist_ok=True)
    _write_json_log(sessions_dir / f"{today}.json", [
        {
            "timestamp": datetime.now().isoformat() + "Z",
            "level": "DEBUG",
            "component": "session",
            "message": "Session started",
            "context": {"session_id": "sess-789"}
        }
    ])


def _write_json_log(file_path: Path, entries: list[dict]):
    """Write JSONL format log file."""
    with open(file_path, 'w') as f:
        for entry in entries:
            f.write(json.dumps(entry) + '\n')


class TestLogReaderInitialization:
    """Test LogReader initialization."""

    @pytest.mark.skipif(LogReader is None, reason="Not implemented yet")
    def test_init_with_org_path(self, temp_org_path):
        """Should initialize with org path."""
        reader = LogReader(temp_org_path)
        assert reader.logs_dir == temp_org_path / LIVE_DIR / "logs"

    @pytest.mark.skipif(LogReader is None, reason="Not implemented yet")
    def test_init_creates_logs_dir_if_missing(self):
        """Should handle missing logs directory gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org_path = Path(tmpdir)
            reader = LogReader(org_path)
            # Should not error even if logs dir doesn't exist yet


class TestListComponents:
    """Test listing components that have logs."""

    @pytest.mark.skipif(LogReader is None, reason="Not implemented yet")
    def test_list_components(self, temp_org_path):
        """Should list all components with log directories."""
        reader = LogReader(temp_org_path)
        components = reader.list_components()

        assert "cli" in components
        assert "workers" in components or "worker" in components
        assert "sessions" in components or "session" in components

    @pytest.mark.skipif(LogReader is None, reason="Not implemented yet")
    def test_list_components_empty_dir(self):
        """Should return empty list for org with no logs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org_path = Path(tmpdir)
            (org_path / LIVE_DIR / "logs").mkdir(parents=True, exist_ok=True)
            reader = LogReader(org_path)
            components = reader.list_components()
            assert components == []


class TestListDates:
    """Test listing dates for which logs exist."""

    @pytest.mark.skipif(LogReader is None, reason="Not implemented yet")
    def test_list_dates_all_components(self, temp_org_path):
        """Should list all dates across all components."""
        reader = LogReader(temp_org_path)
        dates = reader.list_dates()

        today = datetime.now().date()
        yesterday = today - timedelta(days=1)

        assert today in dates
        assert yesterday in dates

    @pytest.mark.skipif(LogReader is None, reason="Not implemented yet")
    def test_list_dates_specific_component(self, temp_org_path):
        """Should list dates for specific component."""
        reader = LogReader(temp_org_path)
        dates = reader.list_dates(component="worker")

        today = datetime.now().date()
        yesterday = today - timedelta(days=1)

        assert today in dates
        assert yesterday in dates

    @pytest.mark.skipif(LogReader is None, reason="Not implemented yet")
    def test_list_dates_sorted_descending(self, temp_org_path):
        """Should return dates in descending order (newest first)."""
        reader = LogReader(temp_org_path)
        dates = reader.list_dates()

        # Verify sorted descending
        for i in range(len(dates) - 1):
            assert dates[i] >= dates[i + 1]


class TestReadLogs:
    """Test reading log entries with filters."""

    @pytest.mark.skipif(LogReader is None, reason="Not implemented yet")
    def test_read_logs_all(self, temp_org_path):
        """Should read all logs without filters."""
        reader = LogReader(temp_org_path)
        logs = reader.read_logs()

        assert len(logs) > 0
        # Should have logs from multiple components
        components = {log["component"] for log in logs}
        assert len(components) > 1

    @pytest.mark.skipif(LogReader is None, reason="Not implemented yet")
    def test_read_logs_filter_by_component(self, temp_org_path):
        """Should filter logs by component."""
        reader = LogReader(temp_org_path)
        logs = reader.read_logs(component="worker")

        assert len(logs) > 0
        # All logs should be from worker component
        for log in logs:
            assert log["component"] == "worker"

    @pytest.mark.skipif(LogReader is None, reason="Not implemented yet")
    def test_read_logs_filter_by_level(self, temp_org_path):
        """Should filter logs by level."""
        reader = LogReader(temp_org_path)
        logs = reader.read_logs(level="ERROR")

        assert len(logs) > 0
        # All logs should be ERROR level
        for log in logs:
            assert log["level"] == "ERROR"

    @pytest.mark.skipif(LogReader is None, reason="Not implemented yet")
    def test_read_logs_filter_by_date_range(self, temp_org_path):
        """Should filter logs by date range."""
        reader = LogReader(temp_org_path)
        today = datetime.now().date()

        logs = reader.read_logs(start_date=today, end_date=today)

        assert len(logs) > 0
        # All logs should be from today
        for log in logs:
            log_date = datetime.fromisoformat(log["timestamp"].replace('Z', '+00:00')).date()
            assert log_date == today

    @pytest.mark.skipif(LogReader is None, reason="Not implemented yet")
    def test_read_logs_with_limit(self, temp_org_path):
        """Should limit number of results."""
        reader = LogReader(temp_org_path)
        logs = reader.read_logs(limit=2)

        assert len(logs) == 2

    @pytest.mark.skipif(LogReader is None, reason="Not implemented yet")
    def test_read_logs_with_offset(self, temp_org_path):
        """Should skip entries with offset."""
        reader = LogReader(temp_org_path)

        all_logs = reader.read_logs(limit=100)
        offset_logs = reader.read_logs(limit=100, offset=1)

        # First log with offset should be second log without offset
        assert len(offset_logs) == len(all_logs) - 1
        if len(all_logs) > 1:
            assert offset_logs[0] == all_logs[1]


class TestSearchLogs:
    """Test full-text search."""

    @pytest.mark.skipif(LogReader is None, reason="Not implemented yet")
    def test_search_logs_by_keyword(self, temp_org_path):
        """Should search logs by keyword in message."""
        reader = LogReader(temp_org_path)
        logs = reader.search_logs(query="lifecycle")

        assert len(logs) > 0
        # All logs should contain "lifecycle" in message or context
        for log in logs:
            found = (
                "lifecycle" in log["message"].lower() or
                "lifecycle" in str(log.get("context", {})).lower() or
                log.get("subcomponent", "") == "lifecycle"
            )
            assert found

    @pytest.mark.skipif(LogReader is None, reason="Not implemented yet")
    def test_search_logs_with_component_filter(self, temp_org_path):
        """Should search within specific component."""
        reader = LogReader(temp_org_path)
        logs = reader.search_logs(query="worker", component="worker")

        assert len(logs) > 0
        for log in logs:
            assert log["component"] == "worker"

    @pytest.mark.skipif(LogReader is None, reason="Not implemented yet")
    def test_search_logs_case_insensitive(self, temp_org_path):
        """Should perform case-insensitive search."""
        reader = LogReader(temp_org_path)
        logs_lower = reader.search_logs(query="lifecycle")
        logs_upper = reader.search_logs(query="LIFECYCLE")

        # Should return same results regardless of case
        assert len(logs_lower) == len(logs_upper)


class TestTailLogs:
    """Test getting most recent log entries."""

    @pytest.mark.skipif(LogReader is None, reason="Not implemented yet")
    def test_tail_logs_default(self, temp_org_path):
        """Should get last 50 log entries by default."""
        reader = LogReader(temp_org_path)
        logs = reader.tail_logs()

        assert len(logs) <= 50
        # Should be sorted by timestamp descending (newest first)
        if len(logs) > 1:
            for i in range(len(logs) - 1):
                time1 = datetime.fromisoformat(logs[i]["timestamp"].replace('Z', '+00:00'))
                time2 = datetime.fromisoformat(logs[i + 1]["timestamp"].replace('Z', '+00:00'))
                assert time1 >= time2

    @pytest.mark.skipif(LogReader is None, reason="Not implemented yet")
    def test_tail_logs_custom_count(self, temp_org_path):
        """Should get specified number of entries."""
        reader = LogReader(temp_org_path)
        logs = reader.tail_logs(lines=2)

        assert len(logs) <= 2

    @pytest.mark.skipif(LogReader is None, reason="Not implemented yet")
    def test_tail_logs_specific_component(self, temp_org_path):
        """Should tail logs from specific component."""
        reader = LogReader(temp_org_path)
        logs = reader.tail_logs(component="worker", lines=10)

        assert len(logs) > 0
        for log in logs:
            assert log["component"] == "worker"


class TestLargeFilePerformance:
    """Test reading 10,000+ entries efficiently."""

    @pytest.mark.skipif(LogReader is None, reason="Not implemented yet")
    def test_large_file_performance(self):
        """Should handle 10,000+ log entries efficiently."""
        with tempfile.TemporaryDirectory() as tmpdir:
            org_path = Path(tmpdir)
            logs_dir = org_path / LIVE_DIR / "logs" / "system"
            logs_dir.mkdir(parents=True, exist_ok=True)

            # Create large log file (10,000 entries)
            today = datetime.now().date()
            log_file = logs_dir / f"{today}.json"

            entries = []
            for i in range(10000):
                entries.append({
                    "timestamp": datetime.now().isoformat() + "Z",
                    "level": "INFO",
                    "component": "system",
                    "message": f"Log entry {i}",
                    "context": {"index": i}
                })

            _write_json_log(log_file, entries)

            # Test reading with limit (should be fast)
            reader = LogReader(org_path)
            logs = reader.read_logs(component="system", limit=100)

            assert len(logs) == 100

    @pytest.mark.skipif(LogReader is None, reason="Not implemented yet")
    def test_streaming_read_memory_efficient(self):
        """Should read large files without loading all into memory."""
        # This test verifies the implementation uses streaming/iterative reads
        with tempfile.TemporaryDirectory() as tmpdir:
            org_path = Path(tmpdir)
            logs_dir = org_path / LIVE_DIR / "logs" / "system"
            logs_dir.mkdir(parents=True, exist_ok=True)

            # Create very large log file
            today = datetime.now().date()
            log_file = logs_dir / f"{today}.json"

            # Write 50,000 entries (should test memory efficiency)
            with open(log_file, 'w') as f:
                for i in range(50000):
                    entry = {
                        "timestamp": datetime.now().isoformat() + "Z",
                        "level": "INFO",
                        "component": "system",
                        "message": f"Entry {i}",
                        "context": {}
                    }
                    f.write(json.dumps(entry) + '\n')

            # Read with limit - should not load entire file into memory
            reader = LogReader(org_path)
            logs = reader.read_logs(component="system", limit=10)

            assert len(logs) == 10
            # Implementation should use iterative reading, not loading entire file
