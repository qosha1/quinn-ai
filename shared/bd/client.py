"""
Beads CLI client for subprocess calls.

Provides a shared client for calling the bd CLI tool,
used by inbox, outbox, notification handlers, and work management.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from typing import Any, Protocol

logger = logging.getLogger(__name__)


# =============================================================================
# Exceptions
# =============================================================================


class BdError(Exception):
    """Base exception for bd CLI errors."""

    def __init__(self, message: str, stderr: str = "", returncode: int = 1):
        super().__init__(message)
        self.stderr = stderr
        self.returncode = returncode


class BdCommandError(BdError):
    """bd command failed to execute."""

    pass


class BdParseError(BdError):
    """Failed to parse bd output."""

    pass


class BdNotFoundError(BdError):
    """Requested issue/resource not found."""

    pass


# Legacy alias for backward compatibility
BdClientError = BdCommandError


# =============================================================================
# Result Type
# =============================================================================


@dataclass
class BdResult:
    """Result from a bd command."""

    stdout: str
    stderr: str
    returncode: int

    @property
    def success(self) -> bool:
        """Whether command succeeded."""
        return self.returncode == 0

    def json(self) -> Any:
        """Parse stdout as JSON.

        Returns:
            Parsed JSON data.

        Raises:
            BdParseError: If JSON parsing fails.
        """
        if not self.stdout.strip():
            return None
        try:
            return json.loads(self.stdout)
        except json.JSONDecodeError as e:
            raise BdParseError(f"Failed to parse JSON: {e}", self.stderr)

    def get_created_id(self) -> str | None:
        """Extract issue ID from 'Created: beads-xxx' output.

        Returns:
            The created issue ID, or None if not found.
        """
        for line in self.stdout.strip().split("\n"):
            # Handle both "Created: beads-xxx" and "✓ Created issue: quinnai-xxx"
            if "Created" in line and ("beads-" in line or "quinnai-" in line):
                # Extract the ID (last word or after colon)
                parts = line.split()
                for part in reversed(parts):
                    if part.startswith(("beads-", "quinnai-")):
                        return part.strip()
                # Try after colon
                if ":" in line:
                    return line.split(":")[-1].strip()
        return None


# =============================================================================
# Protocol for Mocking
# =============================================================================


class BdClientProtocol(Protocol):
    """Protocol for bd client implementations.

    Allows easy mocking in tests.
    """

    def run(self, *args: str, check: bool = True) -> BdResult:
        """Run a bd command and return result.

        Args:
            *args: Command arguments after "bd".
            check: If True, raise BdCommandError on non-zero exit.

        Returns:
            BdResult with stdout, stderr, returncode.

        Raises:
            BdCommandError: If command fails and check=True.
        """
        ...


# =============================================================================
# Main Client
# =============================================================================


class BdClient:
    """
    Client for executing bd CLI commands.

    Provides consistent command execution, error handling, and output parsing
    for all beads-related operations.

    Example:
        client = BdClient()
        result = client.run("list", "--json", "--type=task")
        issues = result.json()

        # Or use convenience methods
        issues = client.list_issues(type="task", status="open")
        issue = client.get_issue("beads-abc123")
    """

    def __init__(
        self,
        bd_command: str = "bd",
        db_path: str | None = None,
        timeout_seconds: int = 30,
        env: dict[str, str] | None = None,
    ):
        """
        Initialize the bd client.

        Args:
            bd_command: Path to bd executable.
            db_path: Optional database path override.
            timeout_seconds: Command timeout in seconds.
            env: Optional environment variables to merge.
        """
        self._bd_command = bd_command
        self._db_path = db_path
        self._timeout = timeout_seconds
        self._env = env or {}

    def run(self, *args: str, check: bool = True) -> BdResult:
        """
        Run a bd command.

        Args:
            *args: Command arguments (e.g., "list", "--json").
            check: If True, raise BdCommandError on non-zero exit.

        Returns:
            BdResult with stdout, stderr, returncode.

        Raises:
            BdCommandError: If command fails and check=True.
        """
        cmd = [self._bd_command] + list(args)
        if self._db_path:
            cmd.extend(["--db", self._db_path])

        logger.debug("Running bd command: %s", " ".join(cmd))

        # Build environment
        import os

        env = os.environ.copy()
        env.update(self._env)

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                env=env if self._env else None,
            )
        except subprocess.TimeoutExpired as e:
            raise BdCommandError(
                f"bd command timed out after {self._timeout}s",
                stderr=str(e),
                returncode=-1,
            )
        except FileNotFoundError:
            raise BdCommandError(
                f"bd command not found: {self._bd_command}",
                returncode=-1,
            )

        result = BdResult(
            stdout=proc.stdout,
            stderr=proc.stderr,
            returncode=proc.returncode,
        )

        if check and not result.success:
            logger.warning("bd command failed: %s", result.stderr)
            raise BdCommandError(
                f"bd command failed: {result.stderr}",
                stderr=result.stderr,
                returncode=result.returncode,
            )

        return result

    def run_silent(self, *args: str) -> BdResult | None:
        """Run a bd command, returning None on failure instead of raising.

        Useful for best-effort operations like acknowledging notifications.

        Args:
            *args: Command arguments after "bd".

        Returns:
            BdResult, or None if command failed.
        """
        try:
            return self.run(*args, check=True)
        except BdCommandError:
            return None

    def run_json(self, *args: str) -> Any:
        """
        Run a bd command and parse JSON output.

        Args:
            *args: Command arguments.

        Returns:
            Parsed JSON data.

        Raises:
            BdCommandError: If command fails.
            BdParseError: If JSON parsing fails.
        """
        result = self.run(*args)
        return result.json()

    # =========================================================================
    # Convenience Methods
    # =========================================================================

    def list_issues(
        self,
        type: str | None = None,
        status: str | None = None,
        limit: int | None = None,
        **filters: str,
    ) -> list[dict[str, Any]]:
        """
        List issues with optional filters.

        Args:
            type: Filter by issue type.
            status: Filter by status (open, closed, in_progress).
            limit: Maximum number of results.
            **filters: Additional filters as --key=value.

        Returns:
            List of issue dictionaries.
        """
        args = ["list", "--json"]
        if type:
            args.append(f"--type={type}")
        if status:
            args.append(f"--status={status}")
        if limit:
            args.append(f"--limit={limit}")
        for key, value in filters.items():
            args.append(f"--{key}={value}")

        try:
            data = self.run_json(*args)
            return data if data else []
        except (BdCommandError, BdParseError) as e:
            logger.warning("Failed to list issues: %s", e)
            return []

    def get_issue(self, issue_id: str) -> dict[str, Any] | None:
        """
        Get a single issue by ID.

        Args:
            issue_id: The issue ID.

        Returns:
            Issue dictionary, or None if not found.
        """
        try:
            return self.run_json("show", issue_id, "--json")
        except BdCommandError:
            return None
        except BdParseError as e:
            logger.warning("Failed to parse issue %s: %s", issue_id, e)
            return None

    def create_issue(
        self,
        title: str,
        type: str,
        priority: int = 2,
        metadata: dict[str, Any] | None = None,
        ephemeral: bool = False,
        description: str | None = None,
        **kwargs: str,
    ) -> str | None:
        """
        Create a new issue.

        Args:
            title: Issue title.
            type: Issue type.
            priority: Priority (0-4).
            metadata: Optional metadata dict.
            ephemeral: If True, mark as ephemeral.
            description: Optional description.
            **kwargs: Additional flags as --key=value.

        Returns:
            Created issue ID, or None if creation failed.
        """
        args = [
            "create",
            f"--title={title}",
            f"--type={type}",
            f"--priority={priority}",
        ]

        if metadata:
            args.append(f"--metadata={json.dumps(metadata)}")
        if ephemeral:
            args.append("--ephemeral")
        if description:
            args.append(f"--description={description}")
        for key, value in kwargs.items():
            args.append(f"--{key.replace('_', '-')}={value}")

        try:
            result = self.run(*args)
            return result.get_created_id()
        except BdCommandError as e:
            logger.warning("Failed to create issue: %s", e)
            return None

    def close_issue(self, issue_id: str, reason: str | None = None) -> bool:
        """
        Close an issue.

        Args:
            issue_id: The issue ID.
            reason: Optional close reason.

        Returns:
            True if closed successfully.
        """
        args = ["close", issue_id]
        if reason:
            args.append(f"--reason={reason}")

        try:
            self.run(*args)
            return True
        except BdCommandError:
            return False

    def update_issue(
        self,
        issue_id: str,
        status: str | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: str,
    ) -> bool:
        """
        Update an issue.

        Args:
            issue_id: The issue ID.
            status: New status.
            metadata: Metadata to merge.
            **kwargs: Additional update flags.

        Returns:
            True if updated successfully.
        """
        args = ["update", issue_id]
        if status:
            args.append(f"--status={status}")
        if metadata:
            args.append(f"--metadata={json.dumps(metadata)}")
        for key, value in kwargs.items():
            args.append(f"--{key.replace('_', '-')}={value}")

        try:
            self.run(*args)
            return True
        except BdCommandError:
            return False

    def add_dependency(
        self,
        issue_id: str,
        depends_on: str,
        dep_type: str = "depends-on",
    ) -> bool:
        """
        Add a dependency between issues.

        Args:
            issue_id: The issue that depends.
            depends_on: The issue being depended on.
            dep_type: Dependency type.

        Returns:
            True if added successfully.
        """
        try:
            self.run("dep", "add", issue_id, depends_on, f"--type={dep_type}")
            return True
        except BdCommandError:
            return False


# =============================================================================
# In-Memory Client for Testing
# =============================================================================


@dataclass
class InMemoryBdClient:
    """In-memory bd client for testing.

    Records all commands for verification and returns
    pre-configured responses.
    """

    responses: dict[str, str] = field(default_factory=dict)
    json_responses: dict[str, Any] = field(default_factory=dict)
    commands: list[tuple[str, ...]] = field(default_factory=list)
    fail_commands: set[str] = field(default_factory=set)

    def run(self, *args: str, check: bool = True) -> BdResult:
        """Record command and return configured response.

        Args:
            *args: Command arguments.
            check: If True, raise on configured failures.

        Returns:
            BdResult with configured response.

        Raises:
            BdCommandError: If command is in fail_commands set and check=True.
        """
        self.commands.append(args)

        # Check if this command should fail
        cmd_key = args[0] if args else ""
        if cmd_key in self.fail_commands:
            if check:
                raise BdCommandError(
                    f"Mock failure for {cmd_key}",
                    stderr=f"Mock failure for {cmd_key}",
                    returncode=1,
                )
            return BdResult(stdout="", stderr=f"Mock failure for {cmd_key}", returncode=1)

        # Return configured response
        stdout = self.responses.get(cmd_key, "")
        if cmd_key in self.json_responses:
            stdout = json.dumps(self.json_responses[cmd_key])

        return BdResult(stdout=stdout, stderr="", returncode=0)

    def run_silent(self, *args: str) -> BdResult | None:
        """Run command, returning None on failure."""
        try:
            return self.run(*args, check=True)
        except BdCommandError:
            return None

    def run_json(self, *args: str) -> Any:
        """Run command and return JSON response."""
        result = self.run(*args)
        return result.json()

    def set_response(self, command: str, response: str) -> None:
        """Configure response for a command.

        Args:
            command: The command name (first arg).
            response: The response to return.
        """
        self.responses[command] = response

    def set_json_response(self, command: str, data: Any) -> None:
        """Configure JSON response for a command.

        Args:
            command: The command name (first arg).
            data: The data to return as JSON.
        """
        self.json_responses[command] = data

    def set_fail(self, command: str) -> None:
        """Configure a command to fail.

        Args:
            command: The command name to fail.
        """
        self.fail_commands.add(command)

    def clear(self) -> None:
        """Clear recorded commands and responses."""
        self.commands.clear()
        self.responses.clear()
        self.json_responses.clear()
        self.fail_commands.clear()

    # Convenience methods return empty/False for testing
    def list_issues(self, **kwargs: Any) -> list[dict[str, Any]]:
        """Return configured list response or empty list."""
        result = self.run("list")
        try:
            return result.json() or []
        except BdParseError:
            return []

    def get_issue(self, issue_id: str) -> dict[str, Any] | None:
        """Return configured show response or None."""
        try:
            result = self.run("show", issue_id)
            return result.json()
        except (BdCommandError, BdParseError):
            return None

    def create_issue(self, **kwargs: Any) -> str | None:
        """Return configured create response ID or None."""
        try:
            result = self.run("create")
            return result.get_created_id()
        except BdCommandError:
            return None

    def close_issue(self, issue_id: str, **kwargs: Any) -> bool:
        """Return True if close doesn't fail."""
        try:
            self.run("close", issue_id)
            return True
        except BdCommandError:
            return False

    def update_issue(self, issue_id: str, **kwargs: Any) -> bool:
        """Return True if update doesn't fail."""
        try:
            self.run("update", issue_id)
            return True
        except BdCommandError:
            return False

    def add_dependency(self, issue_id: str, depends_on: str, **kwargs: Any) -> bool:
        """Return True if dep add doesn't fail."""
        try:
            self.run("dep", "add", issue_id, depends_on)
            return True
        except BdCommandError:
            return False
