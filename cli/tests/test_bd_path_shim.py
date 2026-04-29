"""Tests for the QuinnAI bd PATH shim (host-mode-init).

The shim at scripts/quinnai-bd-shim is installed at
<project_root>/.quinnai/bin/bd by `qn org init --host`. Worker session
spawn prepends that dir to $PATH so workers' `bd` resolves to the shim.
The shim enforces per-assignee write isolation on close transitions:
workers can't close beads assigned to anyone but themselves; humans
(no $QUINN_WORKER_ID) bypass entirely.

Tests run the shim directly with a fake `bd` on PATH that returns
predictable JSON, so we lock the contract without needing a real bd
install.
"""
import os
import stat
import subprocess
import textwrap
from pathlib import Path

import pytest


SHIM_SOURCE = (
    Path(__file__).resolve().parents[2] / "scripts" / "quinnai-bd-shim"
)


def _make_fake_bd(tmp: Path, assignee: str | None) -> Path:
    """Create a fake `bd` script in `tmp` that returns canned JSON for
    `bd show --json <id>` and exits 0 for any other command (so the
    shim's exec at the end succeeds in 'allow' tests).
    """
    fake_bd = tmp / "bd"
    if assignee is None:
        json_block = "{}"
    else:
        json_block = '{"assignee": "%s"}' % assignee
    fake_bd.write_text(
        textwrap.dedent(
            f"""\
            #!/bin/bash
            # fake bd for shim tests
            if [ "$1" = "show" ]; then
              # bd show --json <id>
              echo '{json_block}'
              exit 0
            fi
            # Anything else (close, update, ...) just succeeds quietly so
            # the shim's `exec` path completes without error.
            echo "fake-bd: $@"
            exit 0
            """
        )
    )
    fake_bd.chmod(0o755)
    return fake_bd


def _run_shim(tmp: Path, args: list[str], env: dict) -> subprocess.CompletedProcess:
    """Invoke the shim with PATH constructed so it finds tmp/bd as the
    'real' bd. Inherits the host's other env minus PATH-related entries
    that could confuse the discovery."""
    full_env = {k: v for k, v in os.environ.items() if k not in {"QUINN_WORKER_ID"}}
    # Put tmp on PATH so the shim's "find real bd" walk locates the fake.
    # Place the shim's own dir on PATH too (representative of how it's
    # actually invoked from a worker session) — the shim must skip its
    # own dir during discovery.
    full_env["PATH"] = f"{SHIM_SOURCE.parent}:{tmp}:{full_env.get('PATH', '')}"
    full_env.update(env)
    return subprocess.run(
        [str(SHIM_SOURCE)] + args,
        env=full_env,
        capture_output=True,
        text=True,
    )


class TestShimSourceFile:
    """The shim source file must exist, be executable, and be bash 3.2 compatible."""

    def test_shim_exists(self):
        assert SHIM_SOURCE.exists(), f"shim missing at {SHIM_SOURCE}"

    def test_shim_is_executable(self):
        assert SHIM_SOURCE.stat().st_mode & stat.S_IXUSR

    def test_shim_uses_bash_3_2_compatible_shebang_and_idioms(self):
        content = SHIM_SOURCE.read_text()
        first_line = content.splitlines()[0]
        assert first_line in (
            "#!/bin/bash",
            "#!/usr/bin/env bash",
            "#!/bin/sh",
            "#!/usr/bin/env sh",
        ), f"unexpected shebang: {first_line!r}"
        # bash 3.2 doesn't have associative arrays or mapfile/readarray.
        assert "declare -A" not in content
        assert "mapfile" not in content
        assert "readarray" not in content


class TestShimEnforcement:
    """The trust-boundary enforcement scenarios."""

    def test_blocks_worker_closing_other_workers_bead(self, tmp_path):
        _make_fake_bd(tmp_path, assignee="wrkr-bbb")
        env = {"QUINN_WORKER_ID": "wrkr-aaa"}
        result = _run_shim(
            tmp_path, ["close", "bead-123", "--reason", "stealing"], env
        )

        assert result.returncode != 0
        assert "wrkr-aaa" in result.stderr
        assert "wrkr-bbb" in result.stderr

    def test_blocks_worker_closing_human_assigned_bead(self, tmp_path):
        _make_fake_bd(tmp_path, assignee="alice@example.com")
        env = {"QUINN_WORKER_ID": "wrkr-aaa"}
        result = _run_shim(tmp_path, ["close", "bead-123"], env)

        assert result.returncode != 0
        assert "alice@example.com" in result.stderr

    def test_allows_worker_closing_own_bead(self, tmp_path):
        _make_fake_bd(tmp_path, assignee="wrkr-aaa")
        env = {"QUINN_WORKER_ID": "wrkr-aaa"}
        result = _run_shim(tmp_path, ["close", "bead-123"], env)

        assert result.returncode == 0, (
            f"expected allow, got rc={result.returncode}, stderr={result.stderr!r}"
        )

    def test_allows_close_when_no_quinn_worker_id_env(self, tmp_path):
        """Humans (no $QUINN_WORKER_ID) bypass the check entirely."""
        _make_fake_bd(tmp_path, assignee="wrkr-aaa")
        # No QUINN_WORKER_ID in env.
        result = _run_shim(tmp_path, ["close", "bead-123"], env={})

        assert result.returncode == 0, (
            f"humans must bypass the check, got rc={result.returncode}"
        )

    def test_allows_non_close_status_changes_for_workers(self, tmp_path):
        """`bd update X --status=in_progress` is not gated, even for a
        cross-assignee mismatch. Only close is destructive enough to gate."""
        _make_fake_bd(tmp_path, assignee="wrkr-bbb")
        env = {"QUINN_WORKER_ID": "wrkr-aaa"}
        result = _run_shim(
            tmp_path,
            ["update", "bead-123", "--status=in_progress"],
            env,
        )

        assert result.returncode == 0

    def test_blocks_update_status_closed_form(self, tmp_path):
        """`bd update <id> --status=closed` is equivalent to `bd close <id>`
        and must be gated the same way."""
        _make_fake_bd(tmp_path, assignee="wrkr-bbb")
        env = {"QUINN_WORKER_ID": "wrkr-aaa"}
        result = _run_shim(
            tmp_path,
            ["update", "bead-123", "--status=closed"],
            env,
        )

        assert result.returncode != 0
        assert "wrkr-aaa" in result.stderr

    def test_passes_through_unrelated_commands(self, tmp_path):
        """`bd ready`, `bd list`, etc. must always pass through unchanged
        regardless of $QUINN_WORKER_ID."""
        _make_fake_bd(tmp_path, assignee=None)
        env = {"QUINN_WORKER_ID": "wrkr-aaa"}
        result = _run_shim(tmp_path, ["ready"], env)

        assert result.returncode == 0
        assert "fake-bd: ready" in result.stdout
