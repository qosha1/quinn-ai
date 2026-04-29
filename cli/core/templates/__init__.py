"""Org-structure templates — declarative team blueprints with composition.

Public surface (per u0h2 §2):
- Dataclasses: Template, TemplateMember, ChannelSpec, InitialOKR, TemplateRegistry, HireTeamResult
- (Forthcoming) Functions: load_templates, validate_parent_reference
- (Forthcoming) Class: TemplateOrchestrator
"""

from cli.core.templates.composition import validate_parent_reference
from cli.core.templates.loader import load_templates
from cli.core.templates.orchestrator import TemplateOrchestrator
from cli.core.templates.types import (
    ChannelSpec,
    HireTeamResult,
    InitialOKR,
    Template,
    TemplateMember,
    TemplateRegistry,
)

__all__ = [
    "ChannelSpec",
    "HireTeamResult",
    "InitialOKR",
    "Template",
    "TemplateMember",
    "TemplateOrchestrator",
    "TemplateRegistry",
    "load_templates",
    "validate_parent_reference",
]
