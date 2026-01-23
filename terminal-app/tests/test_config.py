"""Tests for BoardConfig - explicit configuration injection.

Per CLAUDE.md: No config discovery. Configuration passed explicitly at startup.
"""

import pytest
from pathlib import Path

from board_ui.config import BoardConfig
from board_ui.interfaces.terminal import TerminalType


class TestBoardConfig:
    """Tests for BoardConfig dataclass."""

    def test_default_config(self):
        """Default config should have empty org_paths."""
        config = BoardConfig.default()
        assert config.org_paths == []
        assert config.preferred_terminal is None
        assert config.refresh_interval_seconds == 2.0

    def test_with_org_factory(self):
        """with_org should create config with single org path."""
        org_path = Path("/tmp/test-org")
        config = BoardConfig.with_org(org_path)

        assert len(config.org_paths) == 1
        assert config.org_paths[0] == org_path

    def test_multiple_org_paths(self):
        """Config should support multiple org paths."""
        config = BoardConfig(
            org_paths=[Path("/org1"), Path("/org2"), Path("/org3")]
        )

        assert len(config.org_paths) == 3

    def test_preferred_terminal_setting(self):
        """Preferred terminal should be settable."""
        config = BoardConfig(
            org_paths=[],
            preferred_terminal=TerminalType.KITTY,
        )

        assert config.preferred_terminal == TerminalType.KITTY

    def test_ui_preferences(self):
        """UI preferences should have sensible defaults."""
        config = BoardConfig.default()

        assert config.show_inactive_workers is True
        assert config.message_preview_length == 100

    def test_explicit_config_no_discovery(self):
        """Config should not do any path discovery - values are explicit."""
        # This test documents the principle: no magic, no env var scanning
        config = BoardConfig()

        # org_paths is empty by default - no auto-discovery
        assert config.org_paths == []

        # config_dir is None by default - no XDG scanning
        assert config.config_dir is None

        # preferred_terminal is None by default - but will auto-detect at runtime
        # (auto-detection happens in get_terminal_provider, not in config)
        assert config.preferred_terminal is None
