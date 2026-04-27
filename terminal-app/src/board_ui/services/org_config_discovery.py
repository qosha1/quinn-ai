"""Discover org configurations on disk (config/providers.yaml + templates)."""

from pathlib import Path

from .discovery_types import DiscoveredOrgConfig


def get_org_configs(search_paths: list[Path]) -> list[DiscoveredOrgConfig]:
    """List org configurations under search_paths.

    Recognizes `<dir>/config/` as an org config root. Returns DiscoveredOrgConfig
    for each unique config root found.
    """
    configs: list[DiscoveredOrgConfig] = []
    seen_paths: set[Path] = set()

    for search_path in search_paths:
        if not search_path.exists():
            continue

        config_dir = search_path / "config"
        if config_dir.exists() and config_dir.is_dir():
            if search_path not in seen_paths:
                seen_paths.add(search_path)
                configs.append(_build_org_config(search_path))
            continue

        if search_path.is_dir():
            for child in search_path.iterdir():
                if not child.is_dir():
                    continue

                config_dir = child / "config"
                if config_dir.exists() and config_dir.is_dir():
                    if child not in seen_paths:
                        seen_paths.add(child)
                        configs.append(_build_org_config(child))

    return configs


def _build_org_config(org_path: Path) -> DiscoveredOrgConfig:
    """Build DiscoveredOrgConfig from the contents of `<org_path>/config/`."""
    config_dir = org_path / "config"
    providers_path = config_dir / "providers.yaml"
    templates_path = config_dir / "worker-templates.yaml"

    has_providers = providers_path.exists()
    has_templates = templates_path.exists()

    default_provider = None
    if has_providers:
        try:
            import yaml

            with open(providers_path) as f:
                data = yaml.safe_load(f)
                if data:
                    default_provider = data.get("default")
        except Exception:
            pass

    return DiscoveredOrgConfig(
        path=org_path,
        name=org_path.name,
        has_providers=has_providers,
        has_worker_templates=has_templates,
        default_provider=default_provider,
    )
