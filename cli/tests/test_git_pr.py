"""Sanctioned worker git -> branch -> commit -> push -> PR flow (quinn-ai-a3pg.1.3).

Unit tests drive ship_bead with an injected command runner (assert the command
sequence + trust boundary). A real-git e2e pushes to a local bare remote.
"""

import subprocess
import types
from pathlib import Path

import pytest

from cli.core.git_pr import GitError, branch_name_for_bead, ship_bead


def _ok(stdout=""):
    return types.SimpleNamespace(returncode=0, stdout=stdout, stderr="")


class _Recorder:
    """Fake runner that records commands and returns canned results."""

    def __init__(self, results=None):
        self.calls = []
        self._results = results or {}

    def __call__(self, cmd, cwd):
        self.calls.append(cmd)
        # key on the git/gh subcommand
        key = cmd[1] if len(cmd) > 1 else cmd[0]
        return self._results.get(key, _ok())

    @property
    def verbs(self):
        return [c[1] if len(c) > 1 else c[0] for c in self.calls]


# --- branch naming ---------------------------------------------------------

def test_branch_name_plain():
    assert branch_name_for_bead("quinn-ai-abc") == "quinnai/quinn-ai-abc"


def test_branch_name_with_title_slug():
    assert branch_name_for_bead("quinn-ai-abc", "Add the Thing!") == (
        "quinnai/quinn-ai-abc-add-the-thing"
    )


# --- command sequence ------------------------------------------------------

def test_ship_sequence_with_pr():
    runner = _Recorder({"pr": _ok("https://github.com/o/r/pull/7\n")})
    result = ship_bead(
        Path("/repo"),
        "quinn-ai-abc",
        "Add thing",
        create_pr=True,
        runner=runner,
        which=lambda tool: "/usr/bin/gh",
    )
    assert runner.verbs == ["checkout", "add", "commit", "push", "pr"]
    assert result.committed and result.pushed
    assert result.pr_url == "https://github.com/o/r/pull/7"
    # pushed to the default remote name, by branch (no arbitrary URL)
    push_cmd = next(c for c in runner.calls if c[1] == "push")
    assert push_cmd == ["git", "push", "-u", "origin", result.branch]


def test_ship_no_pr_skips_gh():
    runner = _Recorder()
    result = ship_bead(
        Path("/repo"), "quinn-ai-abc", "x", create_pr=False, runner=runner,
        which=lambda tool: "/usr/bin/gh",
    )
    assert "pr" not in runner.verbs
    assert result.pr_url is None


def test_ship_gh_absent_warns_not_fails():
    runner = _Recorder()
    result = ship_bead(
        Path("/repo"), "quinn-ai-abc", "x", create_pr=True, runner=runner,
        which=lambda tool: None,
    )
    assert "pr" not in runner.verbs
    assert result.pushed
    assert any("gh" in w for w in result.warnings)


def test_ship_nothing_to_commit_is_non_fatal():
    runner = _Recorder(
        {"commit": types.SimpleNamespace(returncode=1, stdout="nothing to commit, working tree clean", stderr="")}
    )
    result = ship_bead(
        Path("/repo"), "quinn-ai-abc", "x", create_pr=False, runner=runner,
        which=lambda tool: None,
    )
    assert not result.committed
    assert result.pushed  # still pushes the branch
    assert any("nothing to commit" in w for w in result.warnings)


# --- trust boundary --------------------------------------------------------

@pytest.mark.parametrize("bad_remote", [
    "https://evil.example/repo.git",
    "git@github.com:evil/repo.git",
    "../some/path",
    "",
])
def test_ship_rejects_non_name_remotes(bad_remote):
    with pytest.raises(GitError):
        ship_bead(Path("/repo"), "quinn-ai-abc", "x", remote=bad_remote, runner=_Recorder())


# --- real-git e2e ----------------------------------------------------------

def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


def test_ship_pushes_branch_to_local_bare_remote(tmp_path):
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)

    repo = tmp_path / "work"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "Tester")
    _git(repo, "remote", "add", "origin", str(bare))
    (repo / "README.md").write_text("hi\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")
    _git(repo, "branch", "-M", "main")
    _git(repo, "push", "-u", "origin", "main")

    # a worker change in the repo's cwd
    (repo / "feature.txt").write_text("new\n")
    result = ship_bead(repo, "quinn-ai-xyz", "Add feature", create_pr=False)

    assert result.branch == "quinnai/quinn-ai-xyz-add-feature"
    assert result.committed and result.pushed

    ls = subprocess.run(
        ["git", "ls-remote", "--heads", str(bare), result.branch],
        capture_output=True, text=True,
    )
    assert result.branch in ls.stdout, ls.stdout


def test_qn_wrkr_ship_cli(tmp_path, monkeypatch):
    """`qn wrkr ship --no-pr` branches/commits/pushes from cwd (quinn-ai-a3pg.1.3)."""
    from click.testing import CliRunner

    from cli.commands.main import qn

    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    repo = tmp_path / "work"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "Tester")
    _git(repo, "remote", "add", "origin", str(bare))
    (repo / "README.md").write_text("hi\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")
    _git(repo, "branch", "-M", "main")
    _git(repo, "push", "-u", "origin", "main")
    (repo / "change.txt").write_text("y\n")

    monkeypatch.chdir(repo)
    result = CliRunner().invoke(
        qn,
        ["wrkr", "ship", "--bead", "quinn-ai-zzz", "--title", "Do work", "--no-pr"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert "quinnai/quinn-ai-zzz-do-work" in result.output

    ls = subprocess.run(
        ["git", "ls-remote", "--heads", str(bare), "quinnai/quinn-ai-zzz-do-work"],
        capture_output=True, text=True,
    )
    assert "quinnai/quinn-ai-zzz-do-work" in ls.stdout
