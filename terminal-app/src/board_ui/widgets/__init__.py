"""
Reusable widgets for the board UI.
"""

from .provider_config import ProviderConfigWidget, ProviderInfo
from .okr_editor import OKREditorWidget, Objective, KeyResult, OBJECTIVE_TEMPLATES
from .ceo_briefing import CEOBriefingWidget, BriefingContent, BRIEFING_TEMPLATES

__all__ = [
    "ProviderConfigWidget",
    "ProviderInfo",
    "OKREditorWidget",
    "Objective",
    "KeyResult",
    "OBJECTIVE_TEMPLATES",
    "CEOBriefingWidget",
    "BriefingContent",
    "BRIEFING_TEMPLATES",
]
