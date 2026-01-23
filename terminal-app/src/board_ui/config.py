"""
Board UI configuration.

Configuration is passed explicitly at startup - no searching cwd,
no env var magic (per CLAUDE.md architectural laws).
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .interfaces.terminal import TerminalType


@dataclass
class BoardConfig:
    """Configuration for the board UI.

    All configuration is explicit - no discovery, no magic.
    """

    # Org paths to monitor (can be multiple)
    org_paths: list[Path] = field(default_factory=list)

    # Preferred terminal emulator (None = auto-detect)
    preferred_terminal: Optional[TerminalType] = None

    # UI preferences
    refresh_interval_seconds: float = 2.0
    show_inactive_workers: bool = True
    message_preview_length: int = 100

    # Paths
    config_dir: Optional[Path] = None

    @classmethod
    def default(cls) -> "BoardConfig":
        """Create default configuration."""
        return cls()

    @classmethod
    def with_org(cls, org_path: Path) -> "BoardConfig":
        """Create configuration for a single org."""
        return cls(org_paths=[org_path])
