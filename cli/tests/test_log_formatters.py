"""
Unit tests for the StructuredJSONFormatter.

Following TDD: Write FAILING tests, then implement to make them PASS.
"""

import json
import logging
from datetime import datetime

import pytest


# This import will FAIL until we implement the module
try:
    from cli.core.log_formatters import StructuredJSONFormatter
except ImportError:
    # Expected to fail initially - that's the point of TDD
    StructuredJSONFormatter = None


class TestStructuredJSONFormatter:
    """Test StructuredJSONFormatter class."""

    @pytest.mark.skipif(StructuredJSONFormatter is None, reason="Not implemented yet")
    def test_formatter_creates_valid_json(self):
        """Should output valid JSON."""
        formatter = StructuredJSONFormatter(component="test")

        record = logging.LogRecord(
            name="quinn.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None
        )

        formatted = formatter.format(record)

        # Should parse as valid JSON
        entry = json.loads(formatted)
        assert isinstance(entry, dict)

    @pytest.mark.skipif(StructuredJSONFormatter is None, reason="Not implemented yet")
    def test_formatter_includes_required_fields(self):
        """Should include all required fields."""
        formatter = StructuredJSONFormatter(
            component="test_component",
            subcomponent="test_sub"
        )

        record = logging.LogRecord(
            name="quinn.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None
        )

        formatted = formatter.format(record)
        entry = json.loads(formatted)

        # Required fields
        assert "timestamp" in entry
        assert "level" in entry
        assert "component" in entry
        assert "message" in entry

        # Verify values
        assert entry["level"] == "INFO"
        assert entry["component"] == "test_component"
        assert entry["message"] == "Test message"

    @pytest.mark.skipif(StructuredJSONFormatter is None, reason="Not implemented yet")
    def test_formatter_includes_optional_fields(self):
        """Should include optional fields when present."""
        formatter = StructuredJSONFormatter(
            component="test_component",
            subcomponent="test_sub"
        )

        record = logging.LogRecord(
            name="quinn.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None
        )

        formatted = formatter.format(record)
        entry = json.loads(formatted)

        # Optional fields
        assert "subcomponent" in entry
        assert entry["subcomponent"] == "test_sub"

    @pytest.mark.skipif(StructuredJSONFormatter is None, reason="Not implemented yet")
    def test_formatter_extracts_context_from_extra(self):
        """Should extract context from LogRecord extra dict."""
        formatter = StructuredJSONFormatter(component="test")

        record = logging.LogRecord(
            name="quinn.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None
        )

        # Add extra fields (how logging.Logger.info(msg, extra={...}) works)
        record.event_type = "test_event"
        record.context = {
            "worker_id": "wrkr-123",
            "status": "active"
        }

        formatted = formatter.format(record)
        entry = json.loads(formatted)

        assert "event_type" in entry
        assert entry["event_type"] == "test_event"
        assert "context" in entry
        assert entry["context"]["worker_id"] == "wrkr-123"
        assert entry["context"]["status"] == "active"

    @pytest.mark.skipif(StructuredJSONFormatter is None, reason="Not implemented yet")
    def test_formatter_includes_metadata(self):
        """Should include system metadata."""
        formatter = StructuredJSONFormatter(component="test")

        record = logging.LogRecord(
            name="quinn.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
            func="test_func"
        )
        record.thread = 12345
        record.process = 67890

        formatted = formatter.format(record)
        entry = json.loads(formatted)

        assert "metadata" in entry
        metadata = entry["metadata"]

        # Should include thread, process info
        assert "thread" in metadata or "pid" in metadata

    @pytest.mark.skipif(StructuredJSONFormatter is None, reason="Not implemented yet")
    def test_formatter_handles_different_log_levels(self):
        """Should handle all log levels."""
        formatter = StructuredJSONFormatter(component="test")

        levels = [
            (logging.DEBUG, "DEBUG"),
            (logging.INFO, "INFO"),
            (logging.WARNING, "WARNING"),
            (logging.ERROR, "ERROR"),
            (logging.CRITICAL, "CRITICAL"),
        ]

        for level_int, level_name in levels:
            record = logging.LogRecord(
                name="quinn.test",
                level=level_int,
                pathname="test.py",
                lineno=42,
                msg=f"Test {level_name}",
                args=(),
                exc_info=None
            )

            formatted = formatter.format(record)
            entry = json.loads(formatted)

            assert entry["level"] == level_name

    @pytest.mark.skipif(StructuredJSONFormatter is None, reason="Not implemented yet")
    def test_formatter_timestamp_is_iso8601_utc(self):
        """Should format timestamp as ISO 8601 UTC."""
        formatter = StructuredJSONFormatter(component="test")

        record = logging.LogRecord(
            name="quinn.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None
        )

        formatted = formatter.format(record)
        entry = json.loads(formatted)

        timestamp = entry["timestamp"]

        # Should end with Z (UTC indicator)
        assert timestamp.endswith('Z')

        # Should parse as ISO 8601
        parsed = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        assert isinstance(parsed, datetime)

    @pytest.mark.skipif(StructuredJSONFormatter is None, reason="Not implemented yet")
    def test_formatter_handles_exception_info(self):
        """Should include exception info when present."""
        formatter = StructuredJSONFormatter(component="test")

        try:
            raise ValueError("Test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

            record = logging.LogRecord(
                name="quinn.test",
                level=logging.ERROR,
                pathname="test.py",
                lineno=42,
                msg="Error occurred",
                args=(),
                exc_info=exc_info
            )

            formatted = formatter.format(record)
            entry = json.loads(formatted)

            # Should include exception information
            # Either in message, context, or separate field
            json_str = json.dumps(entry)
            assert "ValueError" in json_str
            assert "Test error" in json_str

    @pytest.mark.skipif(StructuredJSONFormatter is None, reason="Not implemented yet")
    def test_formatter_context_defaults_to_empty_dict(self):
        """Should provide empty context dict when not present."""
        formatter = StructuredJSONFormatter(component="test")

        record = logging.LogRecord(
            name="quinn.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None
        )

        formatted = formatter.format(record)
        entry = json.loads(formatted)

        assert "context" in entry
        assert isinstance(entry["context"], dict)

    @pytest.mark.skipif(StructuredJSONFormatter is None, reason="Not implemented yet")
    def test_formatter_preserves_message_formatting(self):
        """Should handle printf-style message formatting."""
        formatter = StructuredJSONFormatter(component="test")

        record = logging.LogRecord(
            name="quinn.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Worker %s status: %s",
            args=("alice", "active"),
            exc_info=None
        )

        formatted = formatter.format(record)
        entry = json.loads(formatted)

        # Message should be formatted
        assert entry["message"] == "Worker alice status: active"

    @pytest.mark.skipif(StructuredJSONFormatter is None, reason="Not implemented yet")
    def test_formatter_output_is_single_line(self):
        """Should output single-line JSON (JSONL format)."""
        formatter = StructuredJSONFormatter(component="test")

        record = logging.LogRecord(
            name="quinn.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None
        )

        formatted = formatter.format(record)

        # Should not contain newlines (except trailing if any)
        assert '\n' not in formatted.rstrip('\n')

    @pytest.mark.skipif(StructuredJSONFormatter is None, reason="Not implemented yet")
    def test_formatter_handles_unicode(self):
        """Should handle unicode characters in messages."""
        formatter = StructuredJSONFormatter(component="test")

        record = logging.LogRecord(
            name="quinn.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message with unicode: 你好 🚀",
            args=(),
            exc_info=None
        )

        formatted = formatter.format(record)
        entry = json.loads(formatted)

        assert "你好" in entry["message"]
        assert "🚀" in entry["message"]
