"""
Org initialization module.

Provides shared functionality for initializing new organizations,
used by both the CLI (qn org init) and the Board wizard.
"""

import os
import shutil
import subprocess
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List
from importlib import resources

import yaml

from .constants import (
    BEADS_DIR,
    CONFIG_DIR,
    LIVE_DIR,
    ORG_CHART_DIR,
    WORKERS_DIR,
    STORAGE_DIR,
    SHARED_DIR,
    COMPANY_DIR,
)


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
    """Get path to config templates using __file__-based path.

    This supports development (editable install) mode.
    For packaged installs, config files should be included in package_data.

    Returns:
        Path to the config templates directory
    """
    # Use source-relative path - works in development and installed packages
    config_path = Path(__file__).parent.parent / "config"
    return config_path


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
    (org_path / CONFIG_DIR).mkdir(parents=True, exist_ok=True)

    # Org-chart output directory
    (org_path / ORG_CHART_DIR).mkdir(parents=True, exist_ok=True)

    # Runtime state
    (org_path / LIVE_DIR).mkdir(parents=True, exist_ok=True)
    (org_path / LIVE_DIR / WORKERS_DIR).mkdir(exist_ok=True)

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


def init_git_repo(org_path: Path) -> None:
    """Initialize git repository for org if not exists.

    Args:
        org_path: Path to organization directory
    """
    if (org_path / ".git").exists():
        return

    subprocess.run(["git", "init"], cwd=org_path, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=org_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "Initial org structure"],
        cwd=org_path,
        check=True,
        capture_output=True,
    )


def init_beads(org_path: Path) -> None:
    """Initialize beads work tracking system.

    Args:
        org_path: Path to organization directory
    """
    beads_dir = org_path / BEADS_DIR
    if beads_dir.exists():
        return

    env = os.environ.copy()
    env["BEADS_DIR"] = str(beads_dir)

    # --skip-hooks: bd's pre-commit hook calls `bd hooks run pre-commit`
    # which deadlocks on the db lock held by the parent `bd init` (and the
    # hook's `timeout` fallback isn't available on macOS by default).
    # --non-interactive: we're not on a TTY during programmatic init.
    subprocess.run(
        ["bd", "init", "--skip-hooks", "--non-interactive"],
        cwd=org_path,
        env=env,
        check=True,
        capture_output=True,
    )


def create_org_documentation(org_path: Path, org_name: str) -> None:
    """Create org-level documentation from templates.

    Args:
        org_path: Path to organization directory
        org_name: Organization name for template rendering
    """
    from jinja2 import Template

    templates_dir = _get_config_template_path() / "templates"

    # Shared company docs
    company_dir = org_path / STORAGE_DIR / SHARED_DIR / COMPANY_DIR

    for template_name in ["quickstart", "beads-workflow", "okr-guide"]:
        template_file = templates_dir / f"{template_name}.md.jinja2"
        if template_file.exists():
            template = Template(template_file.read_text())
            content = template.render(org_name=org_name)
            output_name = template_name.replace("-", "_").upper() + ".md"
            (company_dir / output_name).write_text(content)

    # Optional org-level README
    org_readme_template = templates_dir / "org-readme.md.jinja2"
    if org_readme_template.exists():
        template = Template(org_readme_template.read_text())
        content = template.render(org_name=org_name)
        (org_path / "README.md").write_text(content)


def create_initial_okrs(
    org_path: Path,
    db,
    ceo_id: str,
    objectives: Optional[List[ObjectiveConfig]] = None,
) -> list[str]:
    """Create initial OKRs in database from provided objectives, config file, or bootstrap.

    Priority order:
    1. Use objectives if provided directly (from CLI prompting or --okrs-file)
    2. Read from config/initial_okrs.json if it exists
    3. Create bootstrap OKR as fallback

    Args:
        org_path: Path to organization directory
        db: Database instance
        ceo_id: CEO worker ID (will be the owner of OKRs)
        objectives: Optional list of objectives passed directly from CLI

    Returns:
        List of OKR IDs created
    """
    from cli.core.queries.okr import create_okr, KeyResult
    from cli.core.constants import (
        DEFAULT_BOOTSTRAP_OKR_TITLE,
        DEFAULT_BOOTSTRAP_OKR_DESCRIPTION,
    )
    import json

    okr_ids = []

    # Priority 1: Use directly provided objectives
    if objectives:
        for obj in objectives:
            key_results = []
            for kr in obj.key_results:
                key_results.append(KeyResult(
                    metric=kr.metric,
                    target=kr.target,
                    current=0.0,
                    unit=kr.unit,
                ))

            okr_id = create_okr(
                db=db,
                title=obj.title,
                owner_id=ceo_id,
                description=None,
                status="active",
                key_results=key_results if key_results else None,
                due_date=None,
            )
            okr_ids.append(okr_id)
        return okr_ids

    # Priority 2: Check config file
    config_file = org_path / "config" / "initial_okrs.json"

    if config_file.exists():
        # Load OKRs from config file
        try:
            okrs_data = json.loads(config_file.read_text())

            for okr_config in okrs_data:
                # Parse key results
                key_results = []
                for kr_data in okr_config.get("key_results", []):
                    key_results.append(KeyResult(
                        metric=kr_data["metric"],
                        target=kr_data["target"],
                        current=kr_data.get("current", 0.0),
                        unit=kr_data.get("unit", "count"),
                    ))

                # Create OKR in database
                okr_id = create_okr(
                    db=db,
                    title=okr_config["title"],
                    owner_id=ceo_id,
                    description=okr_config.get("description"),
                    status="active",
                    key_results=key_results if key_results else None,
                    due_date=None,
                )
                okr_ids.append(okr_id)

            return okr_ids

        except (json.JSONDecodeError, KeyError) as e:
            # If config is malformed, fall through to bootstrap
            _logger = logging.getLogger(__name__)
            _logger.warning(f"Failed to parse initial_okrs.json: {e}. Creating bootstrap OKR.")

    # Priority 3: Create bootstrap OKR
    okr_id = _create_bootstrap_okr(org_path, db, ceo_id)
    okr_ids.append(okr_id)

    return okr_ids


def _create_okr_bead(
    org_path: Path,
    title: str,
    description: str,
    ceo_id: str,
    priority: int = 1,
) -> Optional[str]:
    """Create an OKR as a bead via `bd create` and return its id.

    Returns None if bd is unavailable or the create failed; callers
    should fall back to SQLite-only storage in that case.

    The returned id (e.g. 'myorg-abc123') is suitable as the okr_id
    parameter for cli.core.queries.okr.create_okr() so both stores
    share the same identifier (quinn-ai-lxp).
    """
    import json
    import re
    from cli.core.bd_wrapper import run_bd

    try:
        result = run_bd(
            args=[
                "create", title,
                "--type=epic",
                "--label=okr",
                f"--priority={priority}",
                f"--description={description}",
                f"--assignee={ceo_id}",
                "--json",
            ],
            org_path=org_path,
            worker_id=ceo_id,
            skip_permission_check=True,
            capture_output=True,
        )
        if result.returncode != 0:
            return None
        # bd may emit non-JSON warnings before the JSON object; find the
        # first '{' and parse from there.
        match = re.search(r"\{.*\}", result.stdout, re.DOTALL)
        if not match:
            return None
        data = json.loads(match.group(0))
        return data.get("id")
    except Exception:
        _logger = logging.getLogger(__name__)
        _logger.exception("Failed to create OKR bead for '%s'", title)
        return None


def _create_bootstrap_okr(org_path: Path, db, ceo_id: str) -> str:
    """Create a bootstrap OKR when no config exists.

    Writes the OKR to BOTH stores with the same id:
    1. As a bead (via bd create) — source of truth for the dependency graph
    2. To SQLite okrs table — supplemental for KR progress aggregation

    If the bead-creation step fails (bd unavailable, permission issue),
    we still write to SQLite with a generated id so init doesn't fail —
    but `qn org okr list` (which reads beads) will not surface this OKR.

    Args:
        org_path: Path to organization directory (for bd invocation)
        db: Database instance
        ceo_id: CEO worker ID

    Returns:
        OKR ID — either the bd issue id (when bead creation succeeded)
        or a locally-generated 'okr-...' id (fallback).
    """
    from cli.core.queries.okr import create_okr, KeyResult
    from cli.core.constants import (
        DEFAULT_BOOTSTRAP_OKR_TITLE,
        DEFAULT_BOOTSTRAP_OKR_DESCRIPTION,
    )

    # Bootstrap OKR with generic key results
    key_results = [
        KeyResult(
            metric="team_size",
            target=3.0,
            current=1.0,  # CEO is already hired
            unit="workers",
        ),
        KeyResult(
            metric="processes_documented",
            target=3.0,
            current=0.0,
            unit="docs",
        ),
    ]

    # Step 1: create as a bead so it shows up in `qn org okr list`
    bead_id = _create_okr_bead(
        org_path=org_path,
        title=DEFAULT_BOOTSTRAP_OKR_TITLE,
        description=DEFAULT_BOOTSTRAP_OKR_DESCRIPTION,
        ceo_id=ceo_id,
    )

    # Step 2: mirror to SQLite using the same id (or generate one if step 1 failed)
    okr_id = create_okr(
        db=db,
        title=DEFAULT_BOOTSTRAP_OKR_TITLE,
        owner_id=ceo_id,
        description=DEFAULT_BOOTSTRAP_OKR_DESCRIPTION,
        status="active",
        okr_id=bead_id,  # None → create_okr generates one
        key_results=key_results,
        due_date=None,
    )

    return okr_id


def create_initial_tasks(org_path: Path, db, ceo_id: str, okr_ids: list[str]) -> None:
    """Create initial tasks for CEO that serve the OKRs.

    This fixes GAP 2: CEO has OKRs but no actionable tasks to start working on.

    Args:
        org_path: Path to organization directory
        db: Database instance
        ceo_id: CEO worker ID
        okr_ids: List of OKR IDs to link tasks to
    """
    from cli.core.bd_wrapper import run_bd

    if not okr_ids:
        return

    # Use the first OKR (bootstrap or first from config)
    okr_id = okr_ids[0]

    # Create initial tasks that serve the bootstrap OKR
    initial_tasks = [
        {
            "title": "Review org structure and onboarding materials",
            "description": "Read BRIEFING.md, STORAGE.md, CLAUDE.md to understand org structure and your responsibilities.",
            "priority": 1,
        },
        {
            "title": "Document initial org processes",
            "description": "Create documentation for how the org should operate (workflows, communication, decision-making).",
            "priority": 2,
        },
        {
            "title": "Plan initial team hiring",
            "description": "Identify which roles are needed first and create hiring plan to reach team_size target.",
            "priority": 2,
        },
    ]

    try:
        for task in initial_tasks:
            # NOTE: passing worker_id=ceo_id (not "system") so the activity_signals
            # FK to workers.id holds. There is no "system" worker row.
            run_bd(
                args=[
                    "create",
                    task["title"],
                    "--type=task",
                    f"--priority={task['priority']}",
                    f"--description={task['description']}",
                    f"--assignee={ceo_id}",
                    f"--deps=serves:{okr_id}",
                ],
                org_path=org_path,
                worker_id=ceo_id,
                skip_permission_check=True,
                capture_output=True,
            )
    except Exception as e:
        # Don't fail org init if task creation fails
        _logger = logging.getLogger(__name__)
        _logger.warning(f"Failed to create initial tasks: {e}")
        _logger.warning("CEO will need to create tasks manually from OKRs")


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

        # 1. Initialize git repository
        init_git_repo(org_path)

        # 2. Create folder structure
        create_folder_structure(org_path)

        # 3. Initialize beads
        init_beads(org_path)

        # 4. Write config files
        if config.providers:
            write_providers_config(org_path, config.providers)
        else:
            copy_default_configs(org_path)

        # 5. Write initial OKRs if provided
        write_initial_okrs(org_path, config.objectives)

        # 6. Write CEO briefing if provided
        write_ceo_briefing(org_path, config.ceo_briefing)

        # 7. Initialize database
        db = init_database(db_path)

        try:
            # 8. Create CEO worker
            org = Org(db)
            ceo = org.init(config.ceo_name, config.ceo_role)

            # 8.5. Create initial OKRs in database (GAP 1 fix)
            # Pass objectives from config if provided (from CLI or wizard)
            okr_ids = create_initial_okrs(org_path, db, ceo.id, config.objectives)

            # 8.6. Create initial tasks for CEO (GAP 2 fix)
            create_initial_tasks(org_path, db, ceo.id, okr_ids)

            # 9. Create org-chart
            create_org_chart(org_path, ceo)

            # 10. Create org documentation from templates
            create_org_documentation(org_path, config.name)

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


def initialize_org(
    org_path: Path,
    org_name: str,
    ceo_name: str,
    ceo_role: str,
) -> bool:
    """Convenience wrapper around init_org with flat keyword arguments.

    Args:
        org_path: Directory to initialize the org in
        org_name: Human-readable org name
        ceo_name: CEO's name
        ceo_role: CEO's role title

    Returns:
        True if initialization succeeded, False otherwise
    """
    config = OrgInitConfig(
        path=org_path,
        name=org_name,
        ceo_name=ceo_name,
        ceo_role=ceo_role,
    )
    result = init_org(config)
    return result.success
