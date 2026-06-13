"""Sanctioned worker git flow: branch -> commit -> push -> PR (quinn-ai-a3pg.1.3).

Gives a QuinnAI worker a single, trust-bounded way to land a change for a bead:
create a branch named for the bead, commit the working tree, push to a
*configured remote name* (never an arbitrary URL — the trust boundary), and
open a PR via `gh` when available. In a monorepo each app submodule has its own
`origin`, so pushing to "origin" from the app's cwd targets the right remote.

The command runner is injected (defaults to subprocess) so the orchestration is
unit-testable without a real repo; a real-git e2e covers the end-to-end push.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from cli.core.constants import (
    GIT_BRANCH_PREFIX,
    GIT_BRANCH_SLUG_MAX_LEN,
    GIT_DEFAULT_BASE,
    GIT_DEFAULT_REMOTE,
)


class GitError(Exception):
    """Raised when a git/PR step fails or a request violates the trust boundary."""


# A runner takes (argv, cwd) and returns an object with returncode/stdout/stderr.
Runner = Callable[[list[str], Path], "subprocess.CompletedProcess"]
WhichFn = Callable[[str], Optional[str]]

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _default_runner(cmd: list[str], cwd: Path) -> "subprocess.CompletedProcess":
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)


def _slugify(text: str, max_len: int = GIT_BRANCH_SLUG_MAX_LEN) -> str:
    slug = _SLUG_RE.sub("-", text.strip().lower()).strip("-")
    return slug[:max_len].strip("-")


def branch_name_for_bead(bead_id: str, title: Optional[str] = None) -> str:
    """Deterministic branch name for a bead: quinnai/<bead-id>[-<slug>]."""
    branch = f"{GIT_BRANCH_PREFIX}/{bead_id}"
    if title:
        slug = _slugify(title)
        if slug:
            branch = f"{branch}-{slug}"
    return branch


def _validate_remote(remote: str) -> None:
    """Trust boundary: only a configured remote NAME, never a URL or path."""
    if not remote or any(token in remote for token in ("://", ":", "/", "\\", " ")):
        raise GitError(
            f"remote must be a configured remote name (e.g. 'origin'), "
            f"not a URL/path: {remote!r}"
        )


@dataclass
class ShipResult:
    """Outcome of ship_bead."""

    branch: str
    committed: bool = False
    pushed: bool = False
    pr_url: Optional[str] = None
    warnings: list[str] = field(default_factory=list)


def ship_bead(
    repo: Path,
    bead_id: str,
    title: Optional[str] = None,
    *,
    base: str = GIT_DEFAULT_BASE,
    remote: str = GIT_DEFAULT_REMOTE,
    body: Optional[str] = None,
    create_pr: bool = True,
    runner: Runner = _default_runner,
    which: WhichFn = shutil.which,
) -> ShipResult:
    """Branch, commit, push, and (optionally) open a PR for a bead's work.

    Args:
        repo: Repository working directory (the worker's cwd / app subtree).
        bead_id: The bead this work serves; drives the branch name + commit ref.
        title: Human title for the branch slug, commit, and PR.
        base: PR base branch.
        remote: Configured remote NAME to push to (trust boundary — not a URL).
        body: PR body (defaults to the commit message).
        create_pr: Open a PR via gh when available.
        runner: Injected command runner (argv, cwd) -> CompletedProcess.
        which: Injected PATH lookup (for gh availability).

    Returns:
        A ShipResult describing branch/commit/push/PR outcomes + warnings.

    Raises:
        GitError: On an invalid remote, branch failure, fatal commit error,
            or push failure.
    """
    repo = Path(repo)
    _validate_remote(remote)
    branch = branch_name_for_bead(bead_id, title)
    result = ShipResult(branch=branch)
    headline = title or f"Work on {bead_id}"
    commit_message = f"{headline}\n\n{bead_id}"

    def run(cmd: list[str]) -> "subprocess.CompletedProcess":
        return runner(cmd, repo)

    # 1. Create the branch (or switch to it if it already exists).
    checkout = run(["git", "checkout", "-b", branch])
    if checkout.returncode != 0:
        switch = run(["git", "checkout", branch])
        if switch.returncode != 0:
            raise GitError(
                f"could not create or switch to branch {branch!r}: "
                f"{checkout.stderr or switch.stderr}"
            )

    # 2. Stage everything + commit (nothing-to-commit is non-fatal).
    run(["git", "add", "-A"])
    commit = run(["git", "commit", "-m", commit_message])
    if commit.returncode == 0:
        result.committed = True
    elif "nothing to commit" in f"{commit.stdout}{commit.stderr}".lower():
        result.warnings.append("nothing to commit; pushing branch as-is")
    else:
        raise GitError(f"commit failed: {commit.stderr or commit.stdout}")

    # 3. Push to the configured remote by branch name.
    push = run(["git", "push", "-u", remote, branch])
    if push.returncode != 0:
        raise GitError(f"push to {remote!r} failed: {push.stderr or push.stdout}")
    result.pushed = True

    # 4. Open a PR (best-effort; missing/failing gh is a warning, not a failure).
    if create_pr:
        if which("gh") is None:
            result.warnings.append(
                "gh not found; skipped PR creation. Open a PR manually for "
                f"branch {branch!r}."
            )
        else:
            pr = run(
                [
                    "gh", "pr", "create",
                    "--base", base,
                    "--head", branch,
                    "--title", headline,
                    "--body", body or commit_message,
                ]
            )
            if pr.returncode == 0:
                lines = [ln for ln in (pr.stdout or "").splitlines() if ln.strip()]
                result.pr_url = lines[-1].strip() if lines else None
            else:
                result.warnings.append(
                    f"gh pr create failed: {pr.stderr or pr.stdout}"
                )

    return result
