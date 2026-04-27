"""Read provider configuration (default + capabilities from `qn org provider list`)."""

import subprocess
from pathlib import Path
from typing import Any

import yaml

from ...logging_config import get_board_logger

logger = get_board_logger(__name__)


class ProviderReader:
    """Read provider configuration from providers.yaml + the qn CLI."""

    def __init__(self, db: Any, org_path: Path) -> None:
        self._org_path = org_path

    def get_provider_config(self) -> dict:
        """Get provider configuration for the org."""
        try:
            config_path = self._org_path / "config" / "providers.yaml"
            if not config_path.exists():
                return {"default": "claude_code", "providers": {}}

            with open(config_path) as f:
                config = yaml.safe_load(f) or {}

            default_provider = config.get("default", "claude_code")

            result = subprocess.run(
                ["qn", "--org-path", str(self._org_path), "org", "provider", "list"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            providers = {}
            if result.returncode == 0:
                providers = self._parse_provider_list(result.stdout)

            return {"default": default_provider, "providers": providers}

        except Exception as e:
            logger.error(f"Failed to get provider config: {e}")
            return {"default": "claude_code", "providers": {}}

    def _parse_provider_list(self, output: str) -> dict[str, dict]:
        providers: dict[str, dict] = {}
        current_provider = None

        for line in output.split("\n"):
            line = line.strip()
            if not line or line.startswith("Available") or line.startswith("Total"):
                continue

            if line and not line.startswith(" "):
                current_provider = line
                providers[current_provider] = {
                    "enabled": True,
                    "capabilities": [],
                    "aliases": [],
                }
            elif current_provider and line.startswith(" "):
                if "Aliases:" in line:
                    aliases_str = line.split("Aliases:", 1)[1].strip()
                    providers[current_provider]["aliases"] = [
                        a.strip() for a in aliases_str.split(",")
                    ]
                elif "Capabilities:" in line:
                    caps_str = line.split("Capabilities:", 1)[1].strip()
                    providers[current_provider]["capabilities"] = [
                        c.strip() for c in caps_str.split(",")
                    ]

        return providers
