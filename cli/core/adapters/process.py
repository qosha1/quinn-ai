"""
Process adapter abstraction for subprocess calls.

Provides a unified interface for executing external processes,
enabling testing and swapping implementations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ProcessResult:
    """Result from a process execution."""
    returncode: int
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        return self.returncode == 0


class ProcessAdapter(ABC):
    """Abstract base for process execution."""

    @abstractmethod
    def run(
        self,
        cmd: list[str],
        cwd: Optional[Path] = None,
        env: Optional[dict[str, str]] = None,
        timeout: Optional[float] = None,
        capture_output: bool = True,
    ) -> ProcessResult:
        """Execute a command and return the result."""
        pass


class SubprocessAdapter(ProcessAdapter):
    """Default implementation using subprocess."""

    def run(
        self,
        cmd: list[str],
        cwd: Optional[Path] = None,
        env: Optional[dict[str, str]] = None,
        timeout: Optional[float] = None,
        capture_output: bool = True,
    ) -> ProcessResult:
        import os
        import subprocess

        # Merge with current environment
        full_env = os.environ.copy()
        if env:
            full_env.update(env)

        result = subprocess.run(
            cmd,
            cwd=cwd,
            env=full_env,
            timeout=timeout,
            capture_output=capture_output,
            text=True,
        )

        return ProcessResult(
            returncode=result.returncode,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
        )
