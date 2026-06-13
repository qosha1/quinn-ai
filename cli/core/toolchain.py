"""Worker/org toolchain contract + preflight (quinn-ai-a3pg.1.2).

A declarative list of CLIs an org's workers need, sourced from org.yml's
`toolchain` block and persisted to <org config>/toolchain.yaml by the loader.
The org-start preflight fails fast when a REQUIRED tool is missing from PATH
and warns on missing OPTIONAL tools.

Pure: PATH resolution is injected (defaults to shutil.which), so checks are
trivially unit-testable without touching the real environment.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from cli.core.constants import TOOLCHAIN_FILE


@dataclass
class ToolchainReport:
    """Result of a toolchain check.

    Attributes:
        missing_required: Required tools not found on PATH (a failure).
        missing_optional: Optional tools not found on PATH (a warning).
    """

    missing_required: list[str] = field(default_factory=list)
    missing_optional: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when every required tool is present."""
        return not self.missing_required


def check_toolchain(
    require: list[str],
    optional: Optional[list[str]] = None,
    *,
    which: Callable[[str], Optional[str]] = shutil.which,
) -> ToolchainReport:
    """Check which declared tools are missing from PATH.

    Args:
        require: Tools that must be present.
        optional: Tools that are nice-to-have.
        which: PATH-resolution function (injected for testing).

    Returns:
        A ToolchainReport listing the missing required/optional tools.
    """
    optional = optional or []
    return ToolchainReport(
        missing_required=[tool for tool in require if not which(tool)],
        missing_optional=[tool for tool in optional if not which(tool)],
    )


def load_toolchain(org_path: Path) -> tuple[list[str], list[str]]:
    """Load the persisted (require, optional) toolchain contract.

    Args:
        org_path: Org metadata root.

    Returns:
        (require, optional) lists; ([], []) when no contract is persisted.
    """
    import yaml

    from cli.core.config import get_org_config_path

    path = get_org_config_path(org_path) / TOOLCHAIN_FILE
    if not path.exists():
        return [], []
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except Exception:
        return [], []
    return list(data.get("require", []) or []), list(data.get("optional", []) or [])
