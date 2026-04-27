"""Org initialization module.

Shared between the CLI (qn org init) and the board UI's new-org wizard.
Public surface re-exported here so existing 'from cli.core.org_init import X'
import sites keep working after the file → package split.

Internals:
- types.py        OrgInitConfig + child dataclasses
- scaffolding.py  filesystem + config writers (folder, providers.yaml,
                  initial_okrs.json, ceo_briefing.md, org-chart, git, beads,
                  docs from templates)
- bootstrap.py    create_initial_okrs + create_initial_tasks + bootstrap OKR
- init.py         init_org() orchestrator + initialize_org() shim
"""

# ruff: noqa: F401 — re-exports for the public package surface

from .bootstrap import (
    _create_bootstrap_okr,
    _create_okr_bead,
    create_initial_okrs,
    create_initial_tasks,
)
from .init import init_org, initialize_org
from .scaffolding import (
    copy_default_configs,
    create_folder_structure,
    create_org_chart,
    create_org_documentation,
    init_beads,
    init_git_repo,
    write_ceo_briefing,
    write_initial_okrs,
    write_providers_config,
)
from .types import (
    CEOBriefingConfig,
    KeyResultConfig,
    ObjectiveConfig,
    OrgInitConfig,
    OrgInitProviderConfig,
    OrgInitResult,
)

__all__ = [
    # types
    "CEOBriefingConfig",
    "KeyResultConfig",
    "ObjectiveConfig",
    "OrgInitConfig",
    "OrgInitProviderConfig",
    "OrgInitResult",
    # scaffolding
    "copy_default_configs",
    "create_folder_structure",
    "create_org_chart",
    "create_org_documentation",
    "init_beads",
    "init_git_repo",
    "write_ceo_briefing",
    "write_initial_okrs",
    "write_providers_config",
    # bootstrap
    "create_initial_okrs",
    "create_initial_tasks",
    # init
    "init_org",
    "initialize_org",
]
