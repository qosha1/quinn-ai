"""Filesystem + config-file scaffolding for new orgs.

Creates directory structure, copies / writes config templates, initializes
the git repo and the beads tracking system, generates org-level documentation.
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

import yaml

from ..constants import (
    BEADS_DIR,
    COMPANY_DIR,
    CONFIG_DIR,
    LIVE_DIR,
    ORG_CHART_DIR,
    SHARED_DIR,
    STORAGE_DIR,
    WORKERS_DIR,
)
from .types import CEOBriefingConfig, ObjectiveConfig, OrgInitProviderConfig


def _get_config_template_path() -> Path:
    """Get path to config templates using __file__-based path.

    Works in development (editable install) and packaged installs where
    config files are included in package_data.
    """
    # Walk up to cli/, then into config/
    return Path(__file__).resolve().parent.parent.parent / "config"


def create_folder_structure(org_path: Path) -> None:
    """Create the org folder structure (config/, org-chart/, live/, storage/)."""
    from cli.core.storage import StorageManager

    (org_path / CONFIG_DIR).mkdir(parents=True, exist_ok=True)
    (org_path / ORG_CHART_DIR).mkdir(parents=True, exist_ok=True)
    (org_path / LIVE_DIR).mkdir(parents=True, exist_ok=True)
    (org_path / LIVE_DIR / WORKERS_DIR).mkdir(exist_ok=True)

    storage = StorageManager(org_path, db=None)
    storage.initialize_storage()


def copy_default_configs(org_path: Path) -> None:
    """Copy default providers.yaml + worker-templates.yaml into config/."""
    config_dir = org_path / "config"
    template_path = _get_config_template_path()

    providers_src = template_path / "providers.yaml"
    if providers_src.exists():
        shutil.copy(providers_src, config_dir / "providers.yaml")

    templates_src = template_path / "worker-templates.yaml"
    if templates_src.exists():
        shutil.copy(templates_src, config_dir / "worker-templates.yaml")


def write_providers_config(
    org_path: Path,
    providers: List[OrgInitProviderConfig],
) -> None:
    """Write providers.yaml from wizard input. Falls through to defaults if empty."""
    if not providers:
        copy_default_configs(org_path)
        return

    config_dir = org_path / "config"
    lines = ["# AI Service Providers", "default: claude_code", "", "providers:"]
    for provider in providers:
        if provider.enabled:
            lines.append(f"  {provider.id}:")
            lines.append(f"    enabled: true")
            if provider.api_key:
                lines.append(f"    api_key: {provider.api_key}")
    (config_dir / "providers.yaml").write_text("\n".join(lines) + "\n")


def write_initial_okrs(org_path: Path, objectives: List[ObjectiveConfig]) -> None:
    """Write objectives to config/initial_okrs.json (read later by create_initial_okrs)."""
    if not objectives:
        return

    import json

    okrs_data = [
        {
            "title": obj.title,
            "key_results": [
                {"metric": kr.metric, "target": kr.target, "unit": kr.unit}
                for kr in obj.key_results
            ],
        }
        for obj in objectives
    ]

    (org_path / "config" / "initial_okrs.json").write_text(
        json.dumps(okrs_data, indent=2)
    )


def write_ceo_briefing(
    org_path: Path,
    briefing: Optional[CEOBriefingConfig],
) -> None:
    """Write CEO briefing markdown to config/ceo_briefing.md."""
    if not briefing:
        return

    briefing_md = briefing.to_markdown()
    if briefing_md:
        (org_path / "config" / "ceo_briefing.md").write_text(briefing_md)


def create_org_chart(org_path: Path, ceo) -> None:
    """Create initial org-chart/current.yaml with CEO as root."""
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
        "hierarchy": {"root": ceo.id},
    }

    chart_path = org_path / "org-chart" / "current.yaml"
    with open(chart_path, "w") as f:
        yaml.dump(org_chart, f, default_flow_style=False, sort_keys=False)


def init_git_repo(org_path: Path) -> None:
    """Initialize git repo + commit the initial structure (idempotent)."""
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
    """Initialize the .beads/ tracking dir + disable bd auto-export-on-write."""
    beads_dir = org_path / BEADS_DIR
    if beads_dir.exists():
        return

    env = os.environ.copy()
    env["BEADS_DIR"] = str(beads_dir)

    # --skip-hooks: bd's pre-commit hook calls `bd hooks run pre-commit` which
    # deadlocks on the db lock held by the parent `bd init` (and the hook's
    # `timeout` fallback isn't available on macOS by default).
    # --non-interactive: we're not on a TTY during programmatic init.
    subprocess.run(
        ["bd", "init", "--skip-hooks", "--non-interactive"],
        cwd=org_path,
        env=env,
        check=True,
        capture_output=True,
        timeout=30,
    )

    # Disable auto-export-on-write. bd's default behaviour is to dump
    # issues.jsonl after every create/update; under concurrent test load this
    # produces multi-minute contention hangs (quinn-ai-5d4). The JSONL is
    # recoverable via 'bd export' on demand.
    subprocess.run(
        ["bd", "config", "set", "export.auto", "false"],
        cwd=org_path,
        env=env,
        check=False,  # not fatal if bd doesn't have this config
        capture_output=True,
        timeout=10,
    )


def create_org_documentation(org_path: Path, org_name: str) -> None:
    """Render org-level docs from jinja2 templates into storage/shared/company/."""
    from jinja2 import Template

    templates_dir = _get_config_template_path() / "templates"
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
