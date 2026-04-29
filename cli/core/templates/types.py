"""Data model for org-structure templates.

Per iabn §B and u0h2 §2. All dataclasses are frozen for value semantics; tuples
(not lists) for collection fields so Template/TemplateRegistry remain hashable
and immutable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TemplateMember:
    role: str
    count: int
    cost: int
    is_manager: bool = False


@dataclass(frozen=True)
class ChannelSpec:
    auto_create: bool
    name_template: str


@dataclass(frozen=True)
class InitialOKR:
    title: str
    description: str
    key_results: tuple[dict, ...]


@dataclass(frozen=True)
class Template:
    name: str
    description: str
    members: tuple[TemplateMember, ...]
    channel: Optional[ChannelSpec] = None
    requires: tuple[str, ...] = ()
    initial_okrs: tuple[InitialOKR, ...] = ()
    ttl_hours: Optional[int] = None


@dataclass(frozen=True)
class TemplateRegistry:
    version: int
    templates: tuple[Template, ...]
    source_path: str

    def get(self, name: str) -> Template:
        """Return the template with the given name. Raises TemplateNotFound if absent."""
        from shared.exceptions import TemplateNotFound

        for tmpl in self.templates:
            if tmpl.name == name:
                return tmpl
        raise TemplateNotFound(f"Template not found: {name!r}")


@dataclass(frozen=True)
class HireTeamResult:
    team_id: str
    channel_id: Optional[str]
    worker_ids: tuple[str, ...]
    okr_ids: tuple[str, ...]
    rolled_back: bool = False
    failure_reason: Optional[str] = None
