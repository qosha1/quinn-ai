"""
Org initialization module.

Provides shared functionality for initializing new organizations,
used by both the CLI (qn org init) and the Board wizard.
"""

import shutil
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List
from importlib import resources

import yaml


@dataclass
class ProviderConfig:
    """Configuration for an AI provider."""
    id: str
    enabled: bool = True
    api_key: Optional[str] = None


@dataclass
class KeyResultConfig:
    """Configuration for a key result."""
    metric: str
    target: float
    unit: str = ""


@dataclass
class ObjectiveConfig:
    """Configuration for an objective."""
    title: str
    key_results: List[KeyResultConfig] = field(default_factory=list)


@dataclass
class CEOBriefingConfig:
    """Configuration for CEO briefing message."""
    context: str = ""
    goals: str = ""
    constraints: str = ""
    initial_action: str = ""

    def to_markdown(self) -> str:
        """Convert briefing to markdown format."""
        sections = []
        if self.context:
            sections.append(f"## Context\n\n{self.context}")
        if self.goals:
            sections.append(f"## Goals\n\n{self.goals}")
        if self.constraints:
            sections.append(f"## Constraints\n\n{self.constraints}")
        if self.initial_action:
            sections.append(f"## Initial Action\n\n{self.initial_action}")
        return "\n\n".join(sections) if sections else ""


@dataclass
class OrgInitConfig:
    """Configuration for initializing a new organization."""
    path: Path
    name: str = "My Organization"
    ceo_name: str = "CEO"
    ceo_role: str = "CEO"
    providers: List[ProviderConfig] = field(default_factory=list)
    objectives: List[ObjectiveConfig] = field(default_factory=list)
    ceo_briefing: Optional[CEOBriefingConfig] = None


@dataclass
class OrgInitResult:
    """Result of org initialization."""
    success: bool
    org_path: Path
    db_path: Path
    ceo_id: str
    ceo_name: str
    ceo_role: str
    error: Optional[str] = None


def _get_config_template_path() -> Path:
    """Get path to config templates using importlib.resources.

    Falls back to __file__-based path if resources are not available.
    This supports both development (editable install) and packaged installs.

    Returns:
        Path to the config templates directory
    """
    try:
        # Use importlib.resources for proper package data access
        # This works in packaged distributions and zip imports
        with resources.as_file(resources.files("cli.config")) as config_path:
            return config_path
    except (TypeError, ModuleNotFoundError, FileNotFoundError):
        # Fallback for development: use source-relative path
        # FileNotFoundError: config dir exists but isn't a package (no __init__.py)
        return Path(__file__).parent.parent / "config"


def create_folder_structure(org_path: Path) -> None:
    """Create the org folder structure.

    Structure per README spec:
        org_path/
        ├── config/             # Org config (providers, templates)
        ├── org-chart/          # Git-tracked hiring decisions output
        ├── live/               # Runtime state
        │   ├── quinn.db
        │   └── workers/        # Per-worker session state
        └── storage/            # Abstracted storage
            ├── shared/         # Org lifetime (topics, teams)
            │   ├── engineering/
            │   ├── legal/
            │   └── company/
            └── workers/        # Worker lifetime (mirrors org-chart)
    """
    from cli.core.storage import StorageManager

    # Config directory
    (org_path / "config").mkdir(parents=True, exist_ok=True)

    # Org-chart output directory
    (org_path / "org-chart").mkdir(parents=True, exist_ok=True)

    # Runtime state
    (org_path / "live").mkdir(parents=True, exist_ok=True)
    (org_path / "live" / "workers").mkdir(exist_ok=True)

    # Storage directories with default topics
    storage = StorageManager(org_path, db=None)
    storage.initialize_storage()


def copy_default_configs(org_path: Path) -> None:
    """Copy default config templates to org config directory.

    Copies providers.yaml and worker-templates.yaml from package defaults.
    """
    config_dir = org_path / "config"
    template_path = _get_config_template_path()

    # Copy providers.yaml
    providers_src = template_path / "providers.yaml"
    if providers_src.exists():
        shutil.copy(providers_src, config_dir / "providers.yaml")

    # Copy worker-templates.yaml
    templates_src = template_path / "worker-templates.yaml"
    if templates_src.exists():
        shutil.copy(templates_src, config_dir / "worker-templates.yaml")


def write_providers_config(org_path: Path, providers: List[ProviderConfig]) -> None:
    """Write providers configuration to org config directory.

    Args:
        org_path: Path to organization directory
        providers: List of provider configurations
    """
    if not providers:
        # No custom providers, use defaults
        copy_default_configs(org_path)
        return

    config_dir = org_path / "config"
    providers_content = "# AI Service Providers\n"
    providers_content += "default: claude_code\n\n"
    providers_content += "providers:\n"
    for provider in providers:
        if provider.enabled:
            providers_content += f"  {provider.id}:\n"
            providers_content += f"    enabled: true\n"
            if provider.api_key:
                providers_content += f"    api_key: {provider.api_key}\n"
    (config_dir / "providers.yaml").write_text(providers_content)


def write_initial_okrs(org_path: Path, objectives: List[ObjectiveConfig]) -> None:
    """Write initial OKRs to org config directory.

    Args:
        org_path: Path to organization directory
        objectives: List of objective configurations
    """
    if not objectives:
        return

    import json

    okrs_data = []
    for obj in objectives:
        okr = {
            "title": obj.title,
            "key_results": [
                {
                    "metric": kr.metric,
                    "target": kr.target,
                    "unit": kr.unit,
                }
                for kr in obj.key_results
            ],
        }
        okrs_data.append(okr)

    config_dir = org_path / "config"
    (config_dir / "initial_okrs.json").write_text(json.dumps(okrs_data, indent=2))


def write_ceo_briefing(org_path: Path, briefing: Optional[CEOBriefingConfig]) -> None:
    """Write CEO briefing to org config directory.

    Args:
        org_path: Path to organization directory
        briefing: CEO briefing configuration
    """
    if not briefing:
        return

    briefing_md = briefing.to_markdown()
    if briefing_md:
        config_dir = org_path / "config"
        (config_dir / "ceo_briefing.md").write_text(briefing_md)


def create_org_chart(org_path: Path, ceo) -> None:
    """Create initial org-chart file.

    The org-chart is the git-tracked output of hiring decisions.

    Args:
        org_path: Path to organization directory
        ceo: CEO worker object with id, name, role, lifecycle_status
    """
    org_chart = {
        "version": "1.0",
        "workers": {
            ceo.id: {
                "name": ceo.name,
                "role": ceo.role,
                "lifecycle": ceo.lifecycle_status,
                "manager": None,
                "reports": [],
            }
        },
        "hierarchy": {
            "root": ceo.id,
        }
    }

    chart_path = org_path / "org-chart" / "current.yaml"
    with open(chart_path, "w") as f:
        yaml.dump(org_chart, f, default_flow_style=False, sort_keys=False)


def init_org(config: OrgInitConfig) -> OrgInitResult:
    """Initialize a new organization.

    This is the main entry point for org initialization, used by both
    the CLI (qn org init) and the Board wizard.

    Args:
        config: Organization initialization configuration

    Returns:
        OrgInitResult with success status and details
    """
    from cli.core.db import init_database, get_org_db_path
    from cli.core.org import Org

    org_path = config.path
    db_path = get_org_db_path(org_path)

    try:
        # Check if already initialized
        if db_path.exists():
            return OrgInitResult(
                success=False,
                org_path=org_path,
                db_path=db_path,
                ceo_id="",
                ceo_name="",
                ceo_role="",
                error=f"Organization already initialized at '{org_path}'. "
                      "Run 'qn org status' to view or 'qn org start' to start it.",
            )

        # 1. Create folder structure
        create_folder_structure(org_path)

        # 2. Write config files
        if config.providers:
            write_providers_config(org_path, config.providers)
        else:
            copy_default_configs(org_path)

        # 3. Write initial OKRs if provided
        write_initial_okrs(org_path, config.objectives)

        # 4. Write CEO briefing if provided
        write_ceo_briefing(org_path, config.ceo_briefing)

        # 5. Initialize database
        db = init_database(db_path)

        try:
            # 6. Create CEO worker
            org = Org(db)
            ceo = org.init(config.ceo_name, config.ceo_role)

            # 7. Create org-chart
            create_org_chart(org_path, ceo)

            return OrgInitResult(
                success=True,
                org_path=org_path,
                db_path=db_path,
                ceo_id=ceo.id,
                ceo_name=ceo.name,
                ceo_role=ceo.role,
            )

        finally:
            db.close()

    except Exception as e:
        return OrgInitResult(
            success=False,
            org_path=org_path,
            db_path=db_path,
            ceo_id="",
            ceo_name="",
            ceo_role="",
            error=str(e),
        )
