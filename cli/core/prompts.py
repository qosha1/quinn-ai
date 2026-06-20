"""Render agent-facing prompt templates from cli/config/templates/.

Onboarding / initial-task prompts are FILES, not triple-quoted Python strings,
so they can be edited and reviewed like any other content and never drift into
unmaintained magic strings (quinn-ai-58rw). This mirrors how BRIEFING.md /
WELCOME.md are already rendered (see cli.core.onboarding).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from cli.core.constants.prompts import INITIAL_TASK_TEMPLATES, TEMPLATES_DIR_NAME


def get_templates_dir() -> Path:
    """Absolute path to cli/config/templates/ (single source of truth)."""
    # cli/core/prompts.py -> parent=core, parent.parent=cli
    return Path(__file__).parent.parent / "config" / TEMPLATES_DIR_NAME


@lru_cache(maxsize=1)
def _env() -> Environment:
    # autoescape=False: these are plain-text/markdown prompts (backticks,
    # quotes, shell snippets), not HTML — escaping would corrupt them.
    return Environment(
        loader=FileSystemLoader(str(get_templates_dir())),
        autoescape=False,
        keep_trailing_newline=True,
    )


def render_template(template_name: str, **context: object) -> str:
    """Render a named template file from cli/config/templates/."""
    return _env().get_template(template_name).render(**context)


def render_initial_task(kind: str, **context: object) -> str:
    """Render an initial-task (kickstart) prompt.

    Args:
        kind: One of the INITIAL_TASK_KIND_* values (ceo / ceo_host / worker).
        **context: Template variables (e.g. self_intro, chat_intro, name, role).

    Raises:
        ValueError: If `kind` is not a known initial-task kind.
    """
    try:
        template_name = INITIAL_TASK_TEMPLATES[kind]
    except KeyError:
        raise ValueError(
            f"unknown initial-task kind {kind!r} "
            f"(known: {sorted(INITIAL_TASK_TEMPLATES)})"
        )
    return render_template(template_name, **context)
