"""Tests for the WorkerResult dataclass.

Tests result creation, factory methods, and all field behaviors.
"""

import pytest

from wrkr.core.result import WorkerResult


class TestWorkerResultCreation:
    """Tests for creating WorkerResult instances directly."""

    def test_minimal_success(self) -> None:
        """WorkerResult can be created with minimal successful state."""
        result = WorkerResult(succeeded=True)
        assert result.succeeded is True
        assert result.output == ""
        assert result.error is None

    def test_minimal_failure(self) -> None:
        """WorkerResult can be created with minimal failure state."""
        result = WorkerResult(succeeded=False, error="Something went wrong")
        assert result.succeeded is False
        assert result.error == "Something went wrong"

    def test_default_values(self) -> None:
        """WorkerResult has correct default values."""
        result = WorkerResult(succeeded=True)
        assert result.output == ""
        assert result.error is None
        assert result.needs_escalation is False
        assert result.escalation_reason == ""
        assert result.artifacts == []
        assert result.metadata == {}
        assert result.duration_ms is None

    def test_full_creation(self) -> None:
        """WorkerResult can be created with all fields specified."""
        result = WorkerResult(
            succeeded=True,
            output="Task output",
            error=None,
            needs_escalation=False,
            escalation_reason="",
            artifacts=["/path/to/file.txt", "/path/to/other.json"],
            metadata={"key": "value", "count": 42},
            duration_ms=150,
        )

        assert result.succeeded is True
        assert result.output == "Task output"
        assert result.error is None
        assert result.needs_escalation is False
        assert result.escalation_reason == ""
        assert result.artifacts == ["/path/to/file.txt", "/path/to/other.json"]
        assert result.metadata == {"key": "value", "count": 42}
        assert result.duration_ms == 150


class TestSuccessFactory:
    """Tests for the WorkerResult.success() factory method."""

    def test_success_basic(self) -> None:
        """success() creates a successful result with output."""
        result = WorkerResult.success("Task completed")
        assert result.succeeded is True
        assert result.output == "Task completed"
        assert result.error is None

    def test_success_with_duration(self) -> None:
        """success() can include duration_ms."""
        result = WorkerResult.success("Done", duration_ms=100)
        assert result.succeeded is True
        assert result.output == "Done"
        assert result.duration_ms == 100

    def test_success_with_artifacts(self) -> None:
        """success() can include artifacts list."""
        result = WorkerResult.success(
            "Done",
            artifacts=["/path/to/artifact.txt"],
        )
        assert result.succeeded is True
        assert result.artifacts == ["/path/to/artifact.txt"]

    def test_success_with_metadata(self) -> None:
        """success() can include metadata dict."""
        result = WorkerResult.success(
            "Done",
            metadata={"files_processed": 10},
        )
        assert result.succeeded is True
        assert result.metadata == {"files_processed": 10}

    def test_success_with_all_kwargs(self) -> None:
        """success() can include multiple kwargs."""
        result = WorkerResult.success(
            "All done",
            duration_ms=200,
            artifacts=["/file1.txt", "/file2.txt"],
            metadata={"key": "value"},
        )
        assert result.succeeded is True
        assert result.output == "All done"
        assert result.duration_ms == 200
        assert len(result.artifacts) == 2
        assert result.metadata["key"] == "value"


class TestFailureFactory:
    """Tests for the WorkerResult.failure() factory method."""

    def test_failure_basic(self) -> None:
        """failure() creates a failed result with error."""
        result = WorkerResult.failure("Connection timeout")
        assert result.succeeded is False
        assert result.error == "Connection timeout"

    def test_failure_with_duration(self) -> None:
        """failure() can include duration_ms."""
        result = WorkerResult.failure("Error occurred", duration_ms=50)
        assert result.succeeded is False
        assert result.error == "Error occurred"
        assert result.duration_ms == 50

    def test_failure_with_output(self) -> None:
        """failure() can include partial output."""
        result = WorkerResult.failure(
            "Partial failure",
            output="Partial progress before failure",
        )
        assert result.succeeded is False
        assert result.error == "Partial failure"
        assert result.output == "Partial progress before failure"

    def test_failure_with_metadata(self) -> None:
        """failure() can include metadata dict."""
        result = WorkerResult.failure(
            "Failed",
            metadata={"error_code": 500, "retry_count": 3},
        )
        assert result.succeeded is False
        assert result.metadata["error_code"] == 500
        assert result.metadata["retry_count"] == 3

    def test_failure_does_not_need_escalation_by_default(self) -> None:
        """failure() does not set needs_escalation by default."""
        result = WorkerResult.failure("Error")
        assert result.needs_escalation is False


class TestEscalateFactory:
    """Tests for the WorkerResult.escalate() factory method."""

    def test_escalate_basic(self) -> None:
        """escalate() creates a result requiring escalation."""
        result = WorkerResult.escalate("Requires admin approval")
        assert result.needs_escalation is True
        assert result.escalation_reason == "Requires admin approval"

    def test_escalate_defaults_to_not_succeeded(self) -> None:
        """escalate() defaults succeeded to False."""
        result = WorkerResult.escalate("Need help")
        assert result.succeeded is False

    def test_escalate_can_be_succeeded(self) -> None:
        """escalate() can explicitly set succeeded=True."""
        result = WorkerResult.escalate("Completed but needs review", succeeded=True)
        assert result.needs_escalation is True
        assert result.succeeded is True

    def test_escalate_with_output(self) -> None:
        """escalate() can include output."""
        result = WorkerResult.escalate(
            "Need guidance",
            output="Progress so far...",
        )
        assert result.needs_escalation is True
        assert result.output == "Progress so far..."

    def test_escalate_with_duration(self) -> None:
        """escalate() can include duration_ms."""
        result = WorkerResult.escalate("Stuck", duration_ms=300)
        assert result.needs_escalation is True
        assert result.duration_ms == 300

    def test_escalate_with_metadata(self) -> None:
        """escalate() can include metadata."""
        result = WorkerResult.escalate(
            "Complex decision required",
            metadata={"decision_type": "architectural"},
        )
        assert result.needs_escalation is True
        assert result.metadata["decision_type"] == "architectural"

    def test_escalate_with_all_kwargs(self) -> None:
        """escalate() can include multiple kwargs."""
        result = WorkerResult.escalate(
            "Human review needed",
            output="Analysis complete",
            duration_ms=500,
            artifacts=["/analysis.pdf"],
            metadata={"confidence": 0.7},
        )
        assert result.needs_escalation is True
        assert result.escalation_reason == "Human review needed"
        assert result.output == "Analysis complete"
        assert result.duration_ms == 500
        assert result.artifacts == ["/analysis.pdf"]
        assert result.metadata["confidence"] == 0.7


class TestResultFields:
    """Tests for individual result fields."""

    def test_output_field(self) -> None:
        """output field stores string output."""
        result = WorkerResult(succeeded=True, output="Hello, World!")
        assert result.output == "Hello, World!"

    def test_output_can_be_empty(self) -> None:
        """output field can be empty string."""
        result = WorkerResult(succeeded=True, output="")
        assert result.output == ""

    def test_output_can_be_multiline(self) -> None:
        """output field can contain multiline text."""
        result = WorkerResult(
            succeeded=True,
            output="Line 1\nLine 2\nLine 3",
        )
        assert "\n" in result.output
        assert result.output.count("\n") == 2

    def test_error_can_be_none(self) -> None:
        """error field can be None for success."""
        result = WorkerResult(succeeded=True, error=None)
        assert result.error is None

    def test_error_as_string(self) -> None:
        """error field stores string error message."""
        result = WorkerResult(succeeded=False, error="Error message")
        assert result.error == "Error message"

    def test_artifacts_empty_list(self) -> None:
        """artifacts defaults to empty list."""
        result = WorkerResult(succeeded=True)
        assert result.artifacts == []
        assert isinstance(result.artifacts, list)

    def test_artifacts_multiple_paths(self) -> None:
        """artifacts can contain multiple file paths."""
        result = WorkerResult(
            succeeded=True,
            artifacts=[
                "/path/to/file1.txt",
                "/path/to/file2.json",
                "/path/to/file3.md",
            ],
        )
        assert len(result.artifacts) == 3

    def test_metadata_empty_dict(self) -> None:
        """metadata defaults to empty dict."""
        result = WorkerResult(succeeded=True)
        assert result.metadata == {}
        assert isinstance(result.metadata, dict)

    def test_metadata_with_values(self) -> None:
        """metadata can contain various types."""
        result = WorkerResult(
            succeeded=True,
            metadata={
                "string": "value",
                "number": 42,
                "float": 3.14,
                "boolean": True,
                "list": [1, 2, 3],
                "nested": {"a": "b"},
            },
        )
        assert result.metadata["string"] == "value"
        assert result.metadata["number"] == 42
        assert result.metadata["float"] == 3.14
        assert result.metadata["boolean"] is True
        assert result.metadata["list"] == [1, 2, 3]
        assert result.metadata["nested"]["a"] == "b"

    def test_duration_ms_none(self) -> None:
        """duration_ms can be None when not measured."""
        result = WorkerResult(succeeded=True, duration_ms=None)
        assert result.duration_ms is None

    def test_duration_ms_zero(self) -> None:
        """duration_ms can be zero for very fast tasks."""
        result = WorkerResult(succeeded=True, duration_ms=0)
        assert result.duration_ms == 0

    def test_duration_ms_positive(self) -> None:
        """duration_ms stores positive integer milliseconds."""
        result = WorkerResult(succeeded=True, duration_ms=1500)
        assert result.duration_ms == 1500


class TestResultWithFixtures:
    """Tests using fixtures from conftest."""

    def test_success_result_fixture(self, success_result: WorkerResult) -> None:
        """success_result fixture has expected values."""
        assert success_result.succeeded is True
        assert success_result.output == "Task completed successfully"
        assert success_result.duration_ms == 100
        assert "/path/to/artifact.txt" in success_result.artifacts
        assert success_result.metadata["key"] == "value"

    def test_failure_result_fixture(self, failure_result: WorkerResult) -> None:
        """failure_result fixture has expected values."""
        assert failure_result.succeeded is False
        assert failure_result.error == "Task failed due to error"
        assert failure_result.duration_ms == 50
        assert failure_result.metadata["error_code"] == 500

    def test_escalation_result_fixture(self, escalation_result: WorkerResult) -> None:
        """escalation_result fixture has expected values."""
        assert escalation_result.needs_escalation is True
        assert escalation_result.escalation_reason == "Need manager approval"
        assert escalation_result.output == "Partial progress made"
        assert escalation_result.duration_ms == 200


class TestResultMutability:
    """Tests for result field mutability."""

    def test_artifacts_mutable(self) -> None:
        """artifacts list can be modified after creation."""
        result = WorkerResult(succeeded=True)
        result.artifacts.append("/new/artifact.txt")
        assert "/new/artifact.txt" in result.artifacts

    def test_metadata_mutable(self) -> None:
        """metadata dict can be modified after creation."""
        result = WorkerResult(succeeded=True)
        result.metadata["new_key"] = "new_value"
        assert result.metadata["new_key"] == "new_value"

    def test_separate_instances_have_separate_artifacts(self) -> None:
        """Each result instance has its own artifacts list."""
        result1 = WorkerResult(succeeded=True)
        result2 = WorkerResult(succeeded=True)

        result1.artifacts.append("/file1.txt")

        assert "/file1.txt" in result1.artifacts
        assert "/file1.txt" not in result2.artifacts

    def test_separate_instances_have_separate_metadata(self) -> None:
        """Each result instance has its own metadata dict."""
        result1 = WorkerResult(succeeded=True)
        result2 = WorkerResult(succeeded=True)

        result1.metadata["key"] = "value1"

        assert result1.metadata.get("key") == "value1"
        assert result2.metadata.get("key") is None
