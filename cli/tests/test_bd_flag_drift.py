"""Drift-detection for bd binary flags we depend on (quinn-ai-gudo).

We invoke bd from a few production code paths (`init_beads` in
scaffolding.py, plus `run_bd` for everything else). When a bd binary
upgrade silently renames or removes a flag, callers crash at runtime
with a confusing 'unknown flag' error.

This test checks the help output of every bd subcommand we touch and
asserts the flags we pass are still listed. If the bundled bd (or
system bd, when bundled is absent) drops one of these flags, the test
fails with a clear message before the change reaches users.

Skipped cleanly if no bd binary is resolvable.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from cli.core.bd_wrapper import get_bundled_bd_path


# Flags we rely on at the bd CLI surface. Keep this list in lockstep
# with the actual code — when adding a new bd flag callsite, add the
# flag here too.
#
# Format: (subcommand, [flags-we-depend-on])
REQUIRED_FLAGS: list[tuple[list[str], list[str]]] = [
    # init_beads() in cli/core/org_init/scaffolding.py
    (["init"], ["--skip-hooks", "--quiet"]),
    # bd config set export.auto false in scaffolding.py — no flags, args only
    # (skip)
    # qn org okr list / set / etc. via run_bd
    (["list"], ["--label", "--status", "--assignee", "--json", "--all"]),
    (["create"], ["--type", "--priority", "--description", "--label", "--json"]),
    (["update"], ["--status", "--assignee"]),
    (["close"], ["--reason"]),
    (["show"], ["--json"]),
]


def _resolve_bd() -> Path | None:
    """Return the bd path our production code would use, or None to skip."""
    try:
        return get_bundled_bd_path()
    except FileNotFoundError:
        # Fall back to PATH (mirrors init_beads, which uses bare 'bd')
        path_bd = shutil.which("bd")
        return Path(path_bd) if path_bd else None


_bd = _resolve_bd()
pytestmark = pytest.mark.skipif(
    _bd is None,
    reason="No bd binary resolvable (neither bundled nor on PATH)",
)


def _help_text(bd: Path, subcommand: list[str]) -> str:
    """Capture <subcommand> --help output."""
    result = subprocess.run(
        [str(bd), *subcommand, "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    # bd help may exit 0 or 2 depending on subcommand; we only care about output
    return (result.stdout or "") + "\n" + (result.stderr or "")


@pytest.mark.parametrize("subcommand,flags", REQUIRED_FLAGS, ids=lambda x: " ".join(x) if isinstance(x, list) else str(x))
def test_bd_subcommand_supports_required_flags(subcommand: list[str], flags: list[str]) -> None:
    """Every flag the codebase passes to `bd <subcommand>` must still be in --help.

    Catches silent flag drift after a bd upgrade — e.g. quinn-ai-gudo
    where bd 1.0 dropped --non-interactive on `bd init`.
    """
    assert _bd is not None  # pytestmark would have skipped otherwise
    help_output = _help_text(_bd, subcommand)
    missing = [f for f in flags if f not in help_output]
    assert not missing, (
        f"bd {' '.join(subcommand)} no longer advertises required flag(s): "
        f"{missing}\n"
        f"bd binary: {_bd}\n"
        f"--help output:\n{help_output[:2000]}"
    )
