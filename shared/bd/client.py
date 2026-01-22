"""
Beads CLI client for subprocess calls.

Provides a shared client for calling the bd CLI tool,
used by inbox, outbox, and notification handlers.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


class BdClientError(Exception):
    """Error from bd command execution."""

    def __init__(self, command: list[str], returncode: int, stderr: str):
        self.command = command
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f"bd command failed (exit {returncode}): {stderr}")


class BdClientProtocol(Protocol):
    """Protocol for bd client implementations.

    Allows easy mocking in tests.
    """

    def run(self, *args: str) -> str:
        """Run a bd command and return stdout.

        Args:
            *args: Command arguments after "bd".

        Returns:
            Command stdout.

        Raises:
            BdClientError: If command fails.
        """
        ...


@dataclass
class BdClient:
    """Client for running bd CLI commands.

    Provides consistent subprocess handling for all bd operations.
    Can be configured with custom bd path and optional database path.

    Usage:
        client = BdClient()
        output = client.run("list", "--json")

        # With custom db path
        client = BdClient(db_path="/path/to/.beads")
        output = client.run("show", "beads-abc123")
    """

    bd_command: str = "bd"
    db_path: str | None = None
    env: dict[str, str] = field(default_factory=dict)

    def run(self, *args: str) -> str:
        """Run a bd command and return stdout.

        Args:
            *args: Command arguments after "bd".

        Returns:
            Command stdout.

        Raises:
            BdClientError: If command fails (non-zero exit code).
        """
        cmd = self._build_command(args)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=self._get_env() if self.env else None,
        )

        if result.returncode != 0:
            raise BdClientError(
                command=cmd,
                returncode=result.returncode,
                stderr=result.stderr,
            )

        return result.stdout

    def run_silent(self, *args: str) -> str | None:
        """Run a bd command, returning None on failure instead of raising.

        Useful for best-effort operations like acknowledging notifications.

        Args:
            *args: Command arguments after "bd".

        Returns:
            Command stdout, or None if command failed.
        """
        try:
            return self.run(*args)
        except BdClientError:
            return None

    def _build_command(self, args: tuple[str, ...]) -> list[str]:
        """Build the full command list.

        Args:
            args: Command arguments.

        Returns:
            Full command list including bd path and optional db flag.
        """
        cmd = [self.bd_command] + list(args)
        if self.db_path:
            cmd.extend(["--db", self.db_path])
        return cmd

    def _get_env(self) -> dict[str, str]:
        """Get environment variables for subprocess.

        Returns:
            Merged environment with any custom vars.
        """
        import os

        env = os.environ.copy()
        env.update(self.env)
        return env


@dataclass
class InMemoryBdClient:
    """In-memory bd client for testing.

    Records all commands for verification and returns
    pre-configured responses.
    """

    responses: dict[str, str] = field(default_factory=dict)
    commands: list[tuple[str, ...]] = field(default_factory=list)
    fail_commands: set[str] = field(default_factory=set)

    def run(self, *args: str) -> str:
        """Record command and return configured response.

        Args:
            *args: Command arguments.

        Returns:
            Configured response or empty string.

        Raises:
            BdClientError: If command is in fail_commands set.
        """
        self.commands.append(args)

        # Check if this command should fail
        cmd_key = args[0] if args else ""
        if cmd_key in self.fail_commands:
            raise BdClientError(
                command=list(args),
                returncode=1,
                stderr=f"Mock failure for {cmd_key}",
            )

        # Return configured response
        return self.responses.get(cmd_key, "")

    def run_silent(self, *args: str) -> str | None:
        """Run command, returning None on failure."""
        try:
            return self.run(*args)
        except BdClientError:
            return None

    def set_response(self, command: str, response: str) -> None:
        """Configure response for a command.

        Args:
            command: The command name (first arg).
            response: The response to return.
        """
        self.responses[command] = response

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
        self.fail_commands.clear()
