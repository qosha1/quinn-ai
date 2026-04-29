"""Host-mode discovery and state queries (host-mode-init / quinn-ai).

Host mode = a QuinnAI org overlaid on an existing project. Org metadata
lives under <project_root>/.quinnai/, the project's existing .beads/ is
the org's beads, and workers run with cwd=project_root rather than their
private storage dir.

Discovery is git-style: walk up from a starting path looking for the
.quinnai/ marker dir.

State is recorded in org_state.project_root (NULL for greenfield orgs,
absolute path for host-mode orgs).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

_QUINNAI_MARKER = ".quinnai"


def find_org_root(start: Path) -> Path | None:
    """Walk up from `start` looking for a .quinnai/ marker directory.

    Returns the .quinnai/ directory itself (caller uses .parent for the
    project root). Returns None if no marker is found anywhere on the
    path to the filesystem root.

    Pure: no side effects, no fs writes. Does not resolve symlinks —
    walking up is done on the path as given so callers comparing the
    returned path's .parent against the same input get the expected
    equality (macOS resolves /var → /private/var, which would otherwise
    surprise tests and consumers).
    """
    current = start if start.is_absolute() else start.absolute()
    while True:
        candidate = current / _QUINNAI_MARKER
        if candidate.is_dir():
            return candidate
        parent = current.parent
        if parent == current:
            # Reached filesystem root without finding the marker.
            return None
        current = parent


def is_host_mode(org_path: Path) -> bool:
    """True iff this org's org_state row has project_root populated.

    `org_path` is the directory containing live/quinn.db — for a host
    mode org that's <project_root>/.quinnai/, for a greenfield org that's
    the org dir itself.
    """
    db_path = org_path / "live" / "quinn.db"
    if not db_path.exists():
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT project_root FROM org_state WHERE id='default'"
        ).fetchone()
    except sqlite3.OperationalError:
        # Older db without the column → treat as greenfield.
        return False
    finally:
        conn.close()
    return row is not None and row[0] is not None


def get_project_root(org_path: Path) -> Path:
    """Return the project_root for a host-mode org as an absolute Path.

    Raises ValueError if the org is not in host mode (call is_host_mode
    first to discriminate).
    """
    db_path = org_path / "live" / "quinn.db"
    if not db_path.exists():
        raise ValueError(f"no quin.db at {db_path}")
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT project_root FROM org_state WHERE id='default'"
        ).fetchone()
    finally:
        conn.close()
    if row is None or row[0] is None:
        raise ValueError(
            f"org at {org_path} is not in host mode (project_root is NULL)"
        )
    return Path(row[0])
