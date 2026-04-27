"""
Unit tests for the logging module.
"""

import logging
import tempfile
from pathlib import Path

import pytest

from cli.core.logging import (
    get_logger,
    configure_logging,
    get_log_file_path,
    is_configured,
    log_session_spawn,
    log_session_stop,
    log_budget_check,
    log_budget_spend,
    log_worker_lifecycle,
    log_org_state_change,
    LOGS_DIR,
    LOG_FILE_NAME,
)
from cli.core.constants import LIVE_DIR


@pytest.fixture
def temp_org_path():
    """Create a temporary org directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir)
        # Create live directory structure
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


class TestGetLogger:
    """Test get_logger function."""

    def test_get_logger_returns_logger(self):
        """Should return a logger instance."""
        logger = get_logger("test_module")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "quinn.test_module"

    def test_get_logger_caches_logger(self):
        """Should return same logger for same name."""
        logger1 = get_logger("test_module")
        logger2 = get_logger("test_module")
        assert logger1 is logger2

    def test_get_logger_different_names(self):
        """Should return different loggers for different names."""
        logger1 = get_logger("module_a")
        logger2 = get_logger("module_b")
        assert logger1 is not logger2
        assert logger1.name == "quinn.module_a"
        assert logger2.name == "quinn.module_b"


class TestConfigureLogging:
    """Test configure_logging function."""

    def test_configure_without_org_path(self):
        """Should configure console logging without org path."""
        configure_logging(org_path=None, verbose=False)
        assert is_configured() is True

        # Should have console handler only
        root_logger = logging.getLogger("quinn")
        assert len(root_logger.handlers) == 1

    def test_configure_with_org_path(self, temp_org_path):
        """Should configure file logging with org path."""
        configure_logging(org_path=temp_org_path, verbose=False)
        assert is_configured() is True

        # Should have console + file handlers
        root_logger = logging.getLogger("quinn")
        assert len(root_logger.handlers) == 2

        # Log directory should exist
        log_dir = temp_org_path / LIVE_DIR / LOGS_DIR
        assert log_dir.exists()

    def test_configure_verbose_sets_info_level(self, temp_org_path):
        """Should set console handler to INFO level when verbose."""
        configure_logging(org_path=temp_org_path, verbose=True)

        root_logger = logging.getLogger("quinn")
        # Find console handler (StreamHandler)
        console_handler = None
        for handler in root_logger.handlers:
            if isinstance(handler, logging.StreamHandler) and not hasattr(handler, 'baseFilename'):
                console_handler = handler
                break

        assert console_handler is not None
        assert console_handler.level == logging.INFO

    def test_configure_debug_sets_debug_level(self, temp_org_path):
        """Should set console handler to DEBUG level when debug."""
        configure_logging(org_path=temp_org_path, debug=True)

        root_logger = logging.getLogger("quinn")
        # Find console handler
        console_handler = None
        for handler in root_logger.handlers:
            if isinstance(handler, logging.StreamHandler) and not hasattr(handler, 'baseFilename'):
                console_handler = handler
                break

        assert console_handler is not None
        assert console_handler.level == logging.DEBUG

    def test_configure_default_warning_level(self, temp_org_path):
        """Should default to WARNING level without verbose/debug."""
        configure_logging(org_path=temp_org_path, verbose=False, debug=False)

        root_logger = logging.getLogger("quinn")
        # Find console handler
        console_handler = None
        for handler in root_logger.handlers:
            if isinstance(handler, logging.StreamHandler) and not hasattr(handler, 'baseFilename'):
                console_handler = handler
                break

        assert console_handler is not None
        assert console_handler.level == logging.WARNING

    def test_configure_disables_file_logging(self, temp_org_path):
        """Should not create file handler when log_to_file=False."""
        configure_logging(org_path=temp_org_path, log_to_file=False)

        root_logger = logging.getLogger("quinn")
        # Should only have console handler
        assert len(root_logger.handlers) == 1


class TestGetLogFilePath:
    """Test get_log_file_path function."""

    def test_returns_none_without_org_path(self):
        """Should return None when not configured with org path."""
        configure_logging(org_path=None)
        assert get_log_file_path() is None

    def test_returns_path_with_org_path(self, temp_org_path):
        """Should return log file path when configured."""
        configure_logging(org_path=temp_org_path)
        log_path = get_log_file_path()
        assert log_path is not None
        assert log_path == temp_org_path / LIVE_DIR / LOGS_DIR / LOG_FILE_NAME


class TestStructuredLoggingHelpers:
    """Test structured logging helper functions."""

    def test_log_session_spawn(self, temp_org_path, caplog):
        """Should log session spawn event."""
        configure_logging(org_path=temp_org_path, verbose=True)
        logger = get_logger("test")

        with caplog.at_level(logging.INFO, logger="quinn.test"):
            log_session_spawn(
                logger,
                worker_id="wrkr-123",
                worker_name="alice",
                provider="claude_code",
                session_id="sess-456",
            )

        assert "Session spawned" in caplog.text
        assert "alice" in caplog.text
        assert "wrkr-123" in caplog.text
        assert "claude_code" in caplog.text

    def test_log_session_stop(self, temp_org_path, caplog):
        """Should log session stop event."""
        configure_logging(org_path=temp_org_path, verbose=True)
        logger = get_logger("test")

        with caplog.at_level(logging.INFO, logger="quinn.test"):
            log_session_stop(logger, worker_id="wrkr-123", worker_name="alice", force=False)

        assert "Session stopped" in caplog.text
        assert "graceful" in caplog.text
        assert "alice" in caplog.text

    def test_log_session_stop_forced(self, temp_org_path, caplog):
        """Should indicate forced stop."""
        configure_logging(org_path=temp_org_path, verbose=True)
        logger = get_logger("test")

        with caplog.at_level(logging.INFO, logger="quinn.test"):
            log_session_stop(logger, worker_id="wrkr-123", worker_name="alice", force=True)

        assert "forced" in caplog.text

    def test_log_budget_check_approved(self, temp_org_path, caplog):
        """Should log approved budget check."""
        configure_logging(org_path=temp_org_path, debug=True)
        logger = get_logger("test")

        with caplog.at_level(logging.DEBUG, logger="quinn.test"):
            log_budget_check(
                logger,
                worker_id="wrkr-123",
                required=10.0,
                available=100.0,
                allowed=True,
            )

        assert "Budget check" in caplog.text
        assert "approved" in caplog.text
        assert "wrkr-123" in caplog.text

    def test_log_budget_check_denied(self, temp_org_path, caplog):
        """Should log denied budget check."""
        configure_logging(org_path=temp_org_path, debug=True)
        logger = get_logger("test")

        with caplog.at_level(logging.DEBUG, logger="quinn.test"):
            log_budget_check(
                logger,
                worker_id="wrkr-123",
                required=100.0,
                available=10.0,
                allowed=False,
            )

        assert "denied" in caplog.text

    def test_log_budget_spend(self, temp_org_path, caplog):
        """Should log budget spend event."""
        configure_logging(org_path=temp_org_path, verbose=True)
        logger = get_logger("test")

        with caplog.at_level(logging.INFO, logger="quinn.test"):
            log_budget_spend(
                logger,
                worker_id="wrkr-123",
                amount=5.50,
                provider="anthropic",
                model="claude-3-5-sonnet",
            )

        assert "Budget spend" in caplog.text
        assert "wrkr-123" in caplog.text
        assert "anthropic" in caplog.text
        assert "claude-3-5-sonnet" in caplog.text

    def test_log_worker_lifecycle(self, temp_org_path, caplog):
        """Should log worker lifecycle change."""
        configure_logging(org_path=temp_org_path, verbose=True)
        logger = get_logger("test")

        with caplog.at_level(logging.INFO, logger="quinn.test"):
            log_worker_lifecycle(
                logger,
                worker_id="wrkr-123",
                worker_name="alice",
                old_status="pending",
                new_status="onboarding",
            )

        assert "Worker lifecycle" in caplog.text
        assert "alice" in caplog.text
        assert "pending" in caplog.text
        assert "onboarding" in caplog.text

    def test_log_org_state_change(self, temp_org_path, caplog):
        """Should log org state change."""
        configure_logging(org_path=temp_org_path, verbose=True)
        logger = get_logger("test")

        with caplog.at_level(logging.INFO, logger="quinn.test"):
            log_org_state_change(logger, old_status="initialized", new_status="running")

        assert "Org state change" in caplog.text
        assert "initialized" in caplog.text
        assert "running" in caplog.text


class TestFileLogging:
    """Test file logging functionality."""

    def test_logs_written_to_file(self, temp_org_path):
        """Should write logs to file."""
        configure_logging(org_path=temp_org_path, verbose=True)
        logger = get_logger("test")

        # Log a message
        logger.info("Test log message for file")

        # Check file exists and contains message
        log_file = temp_org_path / LIVE_DIR / LOGS_DIR / LOG_FILE_NAME
        assert log_file.exists()

        content = log_file.read_text()
        assert "Test log message for file" in content

    def test_debug_messages_in_file(self, temp_org_path):
        """Should write debug messages to file even when console is at WARNING."""
        configure_logging(org_path=temp_org_path, verbose=False)  # Console at WARNING
        logger = get_logger("test")

        # Log a debug message
        logger.debug("Debug message for file only")

        # Check file contains debug message
        log_file = temp_org_path / LIVE_DIR / LOGS_DIR / LOG_FILE_NAME
        content = log_file.read_text()
        assert "Debug message for file only" in content
