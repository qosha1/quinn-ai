"""Provider configuration writes (set default, validate)."""

import yaml

from ...logging_config import get_board_logger
from ._context import OrgContext

logger = get_board_logger(__name__)


class ProvidersCommander:
    """Write provider configuration directly to providers.yaml."""

    def __init__(self, ctx: OrgContext) -> None:
        self._ctx = ctx

    def set_default_provider(self, provider_name: str) -> tuple[bool, str]:
        """Set the default provider for the org."""
        try:
            from cli.core.sessions.registry import get_default_registry

            config_path = self._ctx.org_path / "config" / "providers.yaml"
            if not config_path.exists():
                return False, f"Provider config not found: {config_path}"

            registry = get_default_registry()
            if not registry.has(provider_name):
                available = registry.list_adapters()
                return False, (
                    f"Unknown provider '{provider_name}'. "
                    f"Available: {', '.join(sorted(available))}"
                )

            with open(config_path) as f:
                config = yaml.safe_load(f) or {}

            config["default"] = provider_name

            with open(config_path, "w") as f:
                yaml.dump(config, f, default_flow_style=False)

            return True, f"Default provider set to {provider_name}"

        except Exception as e:
            return False, f"Error setting provider: {e}"

    def validate_provider_config(self) -> tuple[bool, list[str]]:
        """Validate that providers.yaml only references registered providers."""
        try:
            from cli.core.sessions.registry import get_default_registry

            config_path = self._ctx.org_path / "config" / "providers.yaml"
            if not config_path.exists():
                return False, [f"Provider config not found: {config_path}"]

            with open(config_path) as f:
                config = yaml.safe_load(f) or {}

            registry = get_default_registry()
            available = set(registry.list_all())
            errors: list[str] = []

            default = config.get("default")
            if default and default not in available:
                errors.append(f"Default provider '{default}' is not registered")

            for name in config.get("authorized_providers", []):
                if name not in available:
                    errors.append(f"Authorized provider '{name}' is not registered")

            return (len(errors) == 0), errors

        except Exception as e:
            return False, [f"Error validating providers: {e}"]
