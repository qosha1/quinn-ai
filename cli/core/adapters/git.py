"""
Git adapter for version control operations.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .process import ProcessAdapter, SubprocessAdapter


@dataclass
class GitStatus:
    """Git repository status."""
    branch: str
    clean: bool
    staged: list[str]
    unstaged: list[str]
    untracked: list[str]


class GitAdapter:
    """Adapter for git operations."""

    def __init__(self, repo_path: Path, process: Optional[ProcessAdapter] = None):
        self._repo_path = repo_path
        self._process = process or SubprocessAdapter()

    def _run_git(self, *args: str, check: bool = False) -> tuple[bool, str]:
        """Run a git command in the repository."""
        result = self._process.run(
            ["git", *args],
            cwd=self._repo_path,
            capture_output=True,
        )
        if check and not result.success:
            raise RuntimeError(f"Git command failed: {result.stderr}")
        return result.success, result.stdout

    def is_repo(self) -> bool:
        """Check if path is a git repository."""
        success, _ = self._run_git("rev-parse", "--git-dir")
        return success

    def add(self, *files: str) -> bool:
        """Stage files for commit."""
        if not files:
            return False
        success, _ = self._run_git("add", *files)
        return success

    def commit(self, message: str) -> bool:
        """Create a commit with the given message."""
        success, _ = self._run_git("commit", "-m", message)
        return success

    def status(self) -> Optional[GitStatus]:
        """Get repository status."""
        success, output = self._run_git("status", "--porcelain", "-b")
        if not success:
            return None

        lines = output.strip().split("\n")
        branch = "unknown"
        staged = []
        unstaged = []
        untracked = []

        for line in lines:
            if line.startswith("##"):
                # Branch line: ## main...origin/main
                branch = line[3:].split("...")[0]
            elif line.startswith("??"):
                untracked.append(line[3:])
            elif line[0] != " ":
                staged.append(line[3:])
            elif line[1] != " ":
                unstaged.append(line[3:])

        return GitStatus(
            branch=branch,
            clean=not (staged or unstaged or untracked),
            staged=staged,
            unstaged=unstaged,
            untracked=untracked,
        )

    def get_current_branch(self) -> Optional[str]:
        """Get the current branch name."""
        success, output = self._run_git("rev-parse", "--abbrev-ref", "HEAD")
        return output.strip() if success else None
