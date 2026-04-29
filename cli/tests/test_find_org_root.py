"""Failing tests for cli.core.host_mode.find_org_root (host-mode-init / quinn-ai-2vui).

Walks up from a starting path looking for a .quinnai/ marker dir,
returning the .quinnai/ path or None. Models git-style upward discovery.

These tests are written BEFORE the implementation exists. They will FAIL
with ImportError until cli/core/host_mode.py is created. That is the
intended red signal.
"""
import tempfile
from pathlib import Path

import pytest


def test_find_org_root_finds_dot_quinnai_in_cwd():
    """When start path itself contains .quinnai/, return that .quinnai/ path."""
    from cli.core.host_mode import find_org_root

    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        (project / ".quinnai").mkdir()

        result = find_org_root(project)

        assert result == project / ".quinnai"


def test_find_org_root_walks_up_to_dot_quinnai():
    """When start is deep inside a project tree, walk up to the .quinnai/ ancestor."""
    from cli.core.host_mode import find_org_root

    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        (project / ".quinnai").mkdir()
        deep = project / "src" / "feature" / "subdir"
        deep.mkdir(parents=True)

        result = find_org_root(deep)

        assert result == project / ".quinnai"


def test_find_org_root_returns_none_when_no_marker():
    """If no .quinnai/ exists anywhere on the path to /, return None."""
    from cli.core.host_mode import find_org_root

    with tempfile.TemporaryDirectory() as tmp:
        leaf = Path(tmp) / "a" / "b" / "c"
        leaf.mkdir(parents=True)

        result = find_org_root(leaf)

        # In a tmp dir with no .quinnai/ ancestor, expect None.
        # (If the test runner happens to live under a .quinnai/ this could
        # false-pass; tmp dirs on macOS are under /var/folders which is
        # outside any user-created .quinnai/.)
        assert result is None


def test_find_org_root_stops_at_filesystem_root():
    """Walking up must stop at filesystem root, not infinite-loop."""
    from cli.core.host_mode import find_org_root

    # Path("/") has no parent that differs from itself; the impl must
    # detect this and return None rather than spinning.
    result = find_org_root(Path("/"))

    assert result is None


def test_find_org_root_returns_dot_quinnai_not_parent():
    """Return value is the .quinnai/ directory itself, not the project root.

    Callers that need the project root use result.parent. Locking this
    contract so future changes don't silently flip the return value.
    """
    from cli.core.host_mode import find_org_root

    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        marker = project / ".quinnai"
        marker.mkdir()

        result = find_org_root(project)

        assert result.name == ".quinnai"
        assert result.parent == project
