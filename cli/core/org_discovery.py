"""
Org directory discovery utilities.

Provides functions to find org root directory from current working directory.
"""

from pathlib import Path
from typing import Optional

from .constants import DEFAULT_DB_NAME, LIVE_DIR


def find_org_root(start_path: Optional[Path] = None) -> Optional[Path]:
    """Find org root by walking up from start_path.

    Looks for live/quinn.db file to identify org root.

    Args:
        start_path: Path to start search from. Defaults to cwd.

    Returns:
        Path to org root if found, None otherwise.

    Examples:
        # From within org directory
        >>> find_org_root()
        Path('/path/to/my-org')

        # From subdirectory
        >>> find_org_root(Path('/path/to/my-org/storage/workers'))
        Path('/path/to/my-org')

        # Not in org
        >>> find_org_root(Path('/tmp'))
        None
    """
    if start_path is None:
        start_path = Path.cwd()

    current = start_path.resolve()

    # Walk up directory tree
    for parent in [current] + list(current.parents):
        db_path = parent / LIVE_DIR / DEFAULT_DB_NAME
        if db_path.exists():
            return parent

    return None


def require_org_root(start_path: Optional[Path] = None) -> Path:
    """Find org root or raise error.

    Args:
        start_path: Path to start search from. Defaults to cwd.

    Returns:
        Path to org root.

    Raises:
        FileNotFoundError: If no org root found.
    """
    org_path = find_org_root(start_path)
    if org_path is None:
        raise FileNotFoundError(
            "No QuinnAI organization found in current directory or parents.\n"
            "Either:\n"
            "  1. Run from within an org directory, or\n"
            "  2. Use --org-path option, or\n"
            "  3. Set QUINN_ORG_PATH environment variable, or\n"
            "  4. Run 'qn org init' to create a new org"
        )
    return org_path
