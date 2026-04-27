"""Translate the new-org wizard's OrgConfig into cli.core.org_init.OrgInitConfig
and call init_org.

Lazy imports cli.core because the board UI can be installed without the CLI
on the path (rare; declared as a dep) — surfaces that as a typed exception.
"""

from dataclasses import dataclass
from typing import Optional

from ..views.org_wizard import OrgConfig


class CliCoreUnavailable(Exception):
    """Raised when cli.core can't be imported (no monorepo / no CLI install)."""


@dataclass
class WizardInitResult:
    success: bool
    error: Optional[str] = None


def init_org_from_wizard(config: OrgConfig) -> WizardInitResult:
    """Map wizard OrgConfig to OrgInitConfig and call init_org.

    Raises:
        CliCoreUnavailable: cli.core.org_init isn't importable.
        ValueError: config.path is missing.
    """
    try:
        from cli.core.org_init import (
            CEOBriefingConfig,
            KeyResultConfig,
            ObjectiveConfig,
            OrgInitConfig,
            OrgInitProviderConfig,
            init_org,
        )
    except ModuleNotFoundError as e:
        raise CliCoreUnavailable(
            "cli.core.org_init not importable — install quinnai or run from monorepo"
        ) from e

    if not config.path:
        raise ValueError("Org path is required")

    init_config = OrgInitConfig(
        path=config.path,
        name=config.name,
        ceo_name="CEO",
        ceo_role="CEO",
        providers=[
            OrgInitProviderConfig(id=p.id, enabled=p.enabled, api_key=p.api_key)
            for p in config.providers
            if p.enabled
        ],
        objectives=[
            ObjectiveConfig(
                title=obj.title,
                key_results=[
                    KeyResultConfig(metric=kr.metric, target=kr.target, unit=kr.unit)
                    for kr in obj.key_results
                ],
            )
            for obj in config.objectives
        ],
        ceo_briefing=(
            CEOBriefingConfig(
                context=config.ceo_briefing.context,
                # Wizard's "requirements" maps to org_init's "goals", and the
                # wizard's "success_criteria" maps to "initial_action".
                goals=config.ceo_briefing.requirements,
                constraints=config.ceo_briefing.constraints,
                initial_action=config.ceo_briefing.success_criteria,
            )
            if config.ceo_briefing
            else None
        ),
    )

    result = init_org(init_config)
    return WizardInitResult(success=result.success, error=result.error)
