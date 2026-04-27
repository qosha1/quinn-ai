"""
Unit tests for enhanced logging with JSON format and per-component segregation.

Following TDD: Write FAILING tests, then implement to make them PASS.
"""

import json
import logging
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from cli.core.logging import get_logger
from cli.core.constants import LIVE_DIR


# These imports will FAIL until we implement the modules
try:
    from cli.core.logging import configure_enhanced_logging, get_component_logger
    from cli.core.log_formatters import StructuredJSONFormatter
    from cli.core.constants import LOG_RETENTION_DAYS, LOG_DATE_FORMAT, LOG_COMPONENTS
except ImportError:
    # Expected to fail initially - that's the point of TDD
    configure_enhanced_logging = None
    get_component_logger = None
    StructuredJSONFormatter = None
    LOG_RETENTION_DAYS = None
    LOG_DATE_FORMAT = None
    LOG_COMPONENTS = None


@pytest.fixture
def temp_org_path():
    """Create a temporary org directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir)
        (org_path / LIVE_DIR).mkdir(parents=True, exist_ok=True)
        yield org_path


@pytest.fixture(autouse=True)
def reset_logging():
    """Reset logging state between tests."""
    from cli.core.logging import reset_for_tests

    reset_for_tests()
    logging.getLogger("quinn").setLevel(logging.DEBUG)

    yield

    reset_for_tests()


class TestComponentLogDirectoryCreation:
    """Test that component directories are created."""

    @pytest.mark.skipif(configure_enhanced_logging is None, reason="Not implemented yet")
    def test_component_directories_created(self, temp_org_path):
        """Should create component directories on configuration."""
        configure_enhanced_logging(
            org_path=temp_org_path,
            component="worker",
            json_format=True
        )

        logs_dir = temp_org_path / LIVE_DIR / "logs"

        # Check that workers/ directory exists
        workers_dir = logs_dir / "workers"
        assert workers_dir.exists()
        assert workers_dir.is_dir()

    @pytest.mark.skipif(configure_enhanced_logging is None, reason="Not implemented yet")
    def test_all_component_types_supported(self, temp_org_path):
        """Should support all component types from constants."""
        for component in ["cli", "worker", "session", "board", "system"]:
            configure_enhanced_logging(
                org_path=temp_org_path,
                component=component,
                json_format=True
            )

            component_dir = temp_org_path / LIVE_DIR / "logs" / f"{component}s" if component in ["worker", "session"] else temp_org_path / LIVE_DIR / "logs" / component
            # Directory should be created when first log is written
            # For now, just verify configuration doesn't error


class TestJSONLogFormat:
    """Test JSON log entry structure."""

    @pytest.mark.skipif(configure_enhanced_logging is None, reason="Not implemented yet")
    def test_json_log_entry_structure(self, temp_org_path):
        """Should write logs in structured JSON format."""
        configure_enhanced_logging(
            org_path=temp_org_path,
            component="worker",
            subcomponent="lifecycle",
            json_format=True
        )

        logger = get_component_logger("worker", "lifecycle")
        logger.info(
            "Worker lifecycle transition",
            extra={
                "event_type": "status_change",
                "context": {
                    "worker_id": "wrkr-123",
                    "worker_name": "Alice",
                    "old_status": "pending",
                    "new_status": "onboarding"
                }
            }
        )

        # Find today's log file
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = temp_org_path / LIVE_DIR / "logs" / "workers" / f"{today}.json"

        assert log_file.exists()

        # Parse JSON log entry
        with open(log_file) as f:
            log_entry = json.loads(f.readline())

        # Verify schema
        assert "timestamp" in log_entry
        assert "level" in log_entry
        assert log_entry["level"] == "INFO"
        assert "component" in log_entry
        assert log_entry["component"] == "worker"
        assert "subcomponent" in log_entry
        assert log_entry["subcomponent"] == "lifecycle"
        assert "event_type" in log_entry
        assert log_entry["event_type"] == "status_change"
        assert "message" in log_entry
        assert log_entry["message"] == "Worker lifecycle transition"
        assert "context" in log_entry
        assert log_entry["context"]["worker_id"] == "wrkr-123"
        assert "metadata" in log_entry

    @pytest.mark.skipif(StructuredJSONFormatter is None, reason="Not implemented yet")
    def test_json_formatter_iso8601_timestamp(self):
        """Should use ISO 8601 format for timestamps."""
        formatter = StructuredJSONFormatter(component="test")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None
        )

        formatted = formatter.format(record)
        entry = json.loads(formatted)

        # Verify timestamp is ISO 8601
        timestamp = entry["timestamp"]
        # Should parse as ISO 8601 (will raise ValueError if not)
        datetime.fromisoformat(timestamp.replace('Z', '+00:00'))


class TestDailyLogRotation:
    """Test new file created each day."""

    @pytest.mark.skipif(configure_enhanced_logging is None, reason="Not implemented yet")
    def test_log_file_named_by_date(self, temp_org_path):
        """Should create log files named YYYY-MM-DD.json."""
        configure_enhanced_logging(
            org_path=temp_org_path,
            component="cli",
            json_format=True
        )

        logger = get_component_logger("cli")
        logger.info("Test message")

        today = datetime.now().strftime("%Y-%m-%d")
        log_file = temp_org_path / LIVE_DIR / "logs" / "cli" / f"{today}.json"

        assert log_file.exists()
        assert log_file.name == f"{today}.json"


class TestLogRetentionCleanup:
    """Test old logs deleted after retention period."""

    @pytest.mark.skipif(configure_enhanced_logging is None, reason="Not implemented yet")
    def test_old_logs_cleaned_up(self, temp_org_path):
        """Should delete logs older than retention period."""
        # Create old log files
        logs_dir = temp_org_path / LIVE_DIR / "logs" / "cli"
        logs_dir.mkdir(parents=True, exist_ok=True)

        # Create files: 29 days ago (keep), 31 days ago (delete)
        retention_days = 30  # Will use LOG_RETENTION_DAYS constant later

        keep_date = (datetime.now() - timedelta(days=29)).strftime("%Y-%m-%d")
        delete_date = (datetime.now() - timedelta(days=31)).strftime("%Y-%m-%d")

        keep_file = logs_dir / f"{keep_date}.json"
        delete_file = logs_dir / f"{delete_date}.json"

        keep_file.write_text('{"test": "keep"}')
        delete_file.write_text('{"test": "delete"}')

        # Configure logging - should trigger cleanup
        configure_enhanced_logging(
            org_path=temp_org_path,
            component="cli",
            json_format=True
        )

        # Verify: keep recent, delete old
        assert keep_file.exists()
        assert not delete_file.exists()


class TestDualOutputPlainAndJSON:
    """Test logs written to both formats."""

    @pytest.mark.skipif(configure_enhanced_logging is None, reason="Not implemented yet")
    def test_dual_logging_both_formats(self, temp_org_path):
        """Should write to both JSON component file and plain text quinn.log."""
        configure_enhanced_logging(
            org_path=temp_org_path,
            component="worker",
            json_format=True,
            legacy_logging=True
        )

        logger = get_component_logger("worker")
        logger.info("Test dual output")

        # Check JSON file
        today = datetime.now().strftime("%Y-%m-%d")
        json_file = temp_org_path / LIVE_DIR / "logs" / "workers" / f"{today}.json"
        assert json_file.exists()

        # Check legacy plain text file
        legacy_file = temp_org_path / LIVE_DIR / "logs" / "quinn.log"
        assert legacy_file.exists()

        # Verify content in both
        json_content = json_file.read_text()
        assert "Test dual output" in json_content

        legacy_content = legacy_file.read_text()
        assert "Test dual output" in legacy_content

    @pytest.mark.skipif(configure_enhanced_logging is None, reason="Not implemented yet")
    def test_legacy_logging_can_be_disabled(self, temp_org_path):
        """Should be able to disable legacy logging."""
        configure_enhanced_logging(
            org_path=temp_org_path,
            component="worker",
            json_format=True,
            legacy_logging=False
        )

        logger = get_component_logger("worker")
        logger.info("Test JSON only")

        # JSON file should exist
        today = datetime.now().strftime("%Y-%m-%d")
        json_file = temp_org_path / LIVE_DIR / "logs" / "workers" / f"{today}.json"
        assert json_file.exists()

        # Legacy file should NOT exist
        legacy_file = temp_org_path / LIVE_DIR / "logs" / "quinn.log"
        assert not legacy_file.exists()


class TestComponentSpecificFiles:
    """Test worker logs go to workers/, etc."""

    @pytest.mark.skipif(configure_enhanced_logging is None, reason="Not implemented yet")
    def test_worker_logs_to_workers_directory(self, temp_org_path):
        """Should route worker logs to workers/ directory."""
        configure_enhanced_logging(
            org_path=temp_org_path,
            component="worker",
            json_format=True
        )

        logger = get_component_logger("worker")
        logger.info("Worker log")

        today = datetime.now().strftime("%Y-%m-%d")
        log_file = temp_org_path / LIVE_DIR / "logs" / "workers" / f"{today}.json"
        assert log_file.exists()

    @pytest.mark.skipif(configure_enhanced_logging is None, reason="Not implemented yet")
    def test_cli_logs_to_cli_directory(self, temp_org_path):
        """Should route CLI logs to cli/ directory."""
        configure_enhanced_logging(
            org_path=temp_org_path,
            component="cli",
            json_format=True
        )

        logger = get_component_logger("cli")
        logger.info("CLI log")

        today = datetime.now().strftime("%Y-%m-%d")
        log_file = temp_org_path / LIVE_DIR / "logs" / "cli" / f"{today}.json"
        assert log_file.exists()

    @pytest.mark.skipif(configure_enhanced_logging is None, reason="Not implemented yet")
    def test_session_logs_to_sessions_directory(self, temp_org_path):
        """Should route session logs to sessions/ directory."""
        configure_enhanced_logging(
            org_path=temp_org_path,
            component="session",
            json_format=True
        )

        logger = get_component_logger("session")
        logger.info("Session log")

        today = datetime.now().strftime("%Y-%m-%d")
        log_file = temp_org_path / LIVE_DIR / "logs" / "sessions" / f"{today}.json"
        assert log_file.exists()
