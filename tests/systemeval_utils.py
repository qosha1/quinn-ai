"""Utilities for parsing and validating systemeval-results.csv from example org runs.

This module provides helpers for e2e tests to validate example org results
in a consistent, comparable way across all example types.
"""

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class SystemevalResult:
    """Parsed result from systemeval-results.csv."""

    run_id: str
    org_name: str
    example_type: str
    timestamp: datetime
    label: str
    duration_seconds: int
    org_status: str
    worker_count: int
    worker_active_count: int
    worker_terminated_count: int
    tasks_completed: int
    tasks_failed: int
    message_count: int
    channel_count: int
    team_count: int
    okr_count: int
    okr_completed_count: int
    total_spent: float
    total_tokens_in: int
    total_tokens_out: int
    session_count: int

    @classmethod
    def from_csv_row(cls, row: dict) -> "SystemevalResult":
        """Parse a CSV row into a SystemevalResult."""
        return cls(
            run_id=row["run_id"],
            org_name=row["org_name"],
            example_type=row["example_type"],
            timestamp=datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")),
            label=row.get("label", ""),
            duration_seconds=int(row["duration_seconds"]),
            org_status=row["org_status"],
            worker_count=int(row["worker_count"]),
            worker_active_count=int(row["worker_active_count"]),
            worker_terminated_count=int(row["worker_terminated_count"]),
            tasks_completed=int(row["tasks_completed"]),
            tasks_failed=int(row["tasks_failed"]),
            message_count=int(row["message_count"]),
            channel_count=int(row["channel_count"]),
            team_count=int(row["team_count"]),
            okr_count=int(row["okr_count"]),
            okr_completed_count=int(row["okr_completed_count"]),
            total_spent=float(row["total_spent"]),
            total_tokens_in=int(row["total_tokens_in"]),
            total_tokens_out=int(row["total_tokens_out"]),
            session_count=int(row["session_count"]),
        )


def parse_systemeval_csv(csv_path: Path) -> SystemevalResult:
    """Parse a systemeval-results.csv file.

    Args:
        csv_path: Path to the systemeval-results.csv file

    Returns:
        Parsed SystemevalResult

    Raises:
        FileNotFoundError: If CSV doesn't exist
        ValueError: If CSV is malformed
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"Systemeval results not found: {csv_path}")

    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if len(rows) != 1:
        raise ValueError(f"Expected 1 data row, got {len(rows)}")

    return SystemevalResult.from_csv_row(rows[0])


def find_latest_archive(run_history_dir: Path, org_name: str) -> Optional[Path]:
    """Find the most recent archive for an org.

    Args:
        run_history_dir: Path to run-history directory
        org_name: Name of the example org

    Returns:
        Path to the latest archive directory, or None if none found
    """
    org_dir = run_history_dir / org_name
    if not org_dir.exists():
        return None

    archives = sorted(org_dir.iterdir(), reverse=True)
    return archives[0] if archives else None


def get_latest_result(run_history_dir: Path, org_name: str) -> Optional[SystemevalResult]:
    """Get the most recent systemeval result for an org.

    Args:
        run_history_dir: Path to run-history directory
        org_name: Name of the example org

    Returns:
        Parsed SystemevalResult, or None if no archives found
    """
    archive_dir = find_latest_archive(run_history_dir, org_name)
    if not archive_dir:
        return None

    csv_path = archive_dir / "systemeval-results.csv"
    if not csv_path.exists():
        return None

    return parse_systemeval_csv(csv_path)


class ResultValidator:
    """Fluent assertion builder for validating systemeval results."""

    def __init__(self, result: SystemevalResult):
        self.result = result
        self.errors: list[str] = []

    def expect_org_name(self, expected: str) -> "ResultValidator":
        """Assert org_name matches expected value."""
        if self.result.org_name != expected:
            self.errors.append(
                f"org_name: expected '{expected}', got '{self.result.org_name}'"
            )
        return self

    def expect_example_type(self, expected: str) -> "ResultValidator":
        """Assert example_type matches expected value."""
        if self.result.example_type != expected:
            self.errors.append(
                f"example_type: expected '{expected}', got '{self.result.example_type}'"
            )
        return self

    def expect_org_status(self, expected: str) -> "ResultValidator":
        """Assert org_status matches expected value."""
        if self.result.org_status != expected:
            self.errors.append(
                f"org_status: expected '{expected}', got '{self.result.org_status}'"
            )
        return self

    def expect_min_workers(self, min_count: int) -> "ResultValidator":
        """Assert at least min_count workers."""
        if self.result.worker_count < min_count:
            self.errors.append(
                f"worker_count: expected >= {min_count}, got {self.result.worker_count}"
            )
        return self

    def expect_min_active_workers(self, min_count: int) -> "ResultValidator":
        """Assert at least min_count active workers."""
        if self.result.worker_active_count < min_count:
            self.errors.append(
                f"worker_active_count: expected >= {min_count}, got {self.result.worker_active_count}"
            )
        return self

    def expect_min_messages(self, min_count: int) -> "ResultValidator":
        """Assert at least min_count messages."""
        if self.result.message_count < min_count:
            self.errors.append(
                f"message_count: expected >= {min_count}, got {self.result.message_count}"
            )
        return self

    def expect_min_sessions(self, min_count: int) -> "ResultValidator":
        """Assert at least min_count sessions."""
        if self.result.session_count < min_count:
            self.errors.append(
                f"session_count: expected >= {min_count}, got {self.result.session_count}"
            )
        return self

    def expect_no_failed_tasks(self) -> "ResultValidator":
        """Assert no tasks failed."""
        if self.result.tasks_failed > 0:
            self.errors.append(
                f"tasks_failed: expected 0, got {self.result.tasks_failed}"
            )
        return self

    def expect_budget_spent(self) -> "ResultValidator":
        """Assert some budget was spent (org did work)."""
        if self.result.total_spent <= 0:
            self.errors.append(
                f"total_spent: expected > 0, got {self.result.total_spent}"
            )
        return self

    def expect_tokens_used(self) -> "ResultValidator":
        """Assert tokens were consumed."""
        total_tokens = self.result.total_tokens_in + self.result.total_tokens_out
        if total_tokens <= 0:
            self.errors.append(
                f"total_tokens: expected > 0, got in={self.result.total_tokens_in}, out={self.result.total_tokens_out}"
            )
        return self

    def expect_min_okrs(self, min_count: int) -> "ResultValidator":
        """Assert at least min_count OKRs created."""
        if self.result.okr_count < min_count:
            self.errors.append(
                f"okr_count: expected >= {min_count}, got {self.result.okr_count}"
            )
        return self

    def expect_duration_positive(self) -> "ResultValidator":
        """Assert duration was calculated (org started and stopped)."""
        if self.result.duration_seconds <= 0:
            self.errors.append(
                f"duration_seconds: expected > 0, got {self.result.duration_seconds}"
            )
        return self

    def validate(self) -> None:
        """Raise AssertionError if any expectations failed."""
        if self.errors:
            raise AssertionError(
                f"Systemeval validation failed for {self.result.org_name}:\n"
                + "\n".join(f"  - {e}" for e in self.errors)
            )


def validate_result(result: SystemevalResult) -> ResultValidator:
    """Create a validator for fluent assertions on a result.

    Example:
        validate_result(result)
            .expect_org_status("stopped")
            .expect_min_workers(1)
            .expect_no_failed_tasks()
            .validate()
    """
    return ResultValidator(result)
