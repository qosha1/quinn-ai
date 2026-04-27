"""Org-init configuration dataclasses.

Used by both the CLI (qn org init) and the board UI's new-org wizard
(via terminal-app/src/board_ui/services/wizard_init.py).
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class OrgInitProviderConfig:
    """Configuration for an AI provider during org init.

    Distinct from shared.provider_types.ProviderConfig (the canonical
    runtime provider config) — this carries the wizard-form fields
    (id, enabled, api_key) that get written into providers.yaml at
    org-creation time.
    """

    id: str
    enabled: bool = True
    api_key: Optional[str] = None


@dataclass
class KeyResultConfig:
    """Configuration for a key result on an OKR."""

    metric: str
    target: float
    unit: str = ""


@dataclass
class ObjectiveConfig:
    """Configuration for an objective (OKR) with its key results."""

    title: str
    key_results: List[KeyResultConfig] = field(default_factory=list)


@dataclass
class CEOBriefingConfig:
    """Initial CEO briefing message — written to config/ceo_briefing.md."""

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
    providers: List[OrgInitProviderConfig] = field(default_factory=list)
    objectives: List[ObjectiveConfig] = field(default_factory=list)
    ceo_briefing: Optional[CEOBriefingConfig] = None


@dataclass
class OrgInitResult:
    """Result returned by init_org."""

    success: bool
    org_path: Path
    db_path: Path
    ceo_id: str
    ceo_name: str
    ceo_role: str
    error: Optional[str] = None
