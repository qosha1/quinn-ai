"""Briefing profile/overlay rendering (quinn-ai-a3pg.4.4).

The briefing template injects a profile's conventions when a profile is
present, and renders unchanged when it is absent. Tested by rendering the
real template directly (lenient Undefined, like the onboarding env), so no
full OnboardingContext is needed.
"""

from pathlib import Path

import cli
from jinja2 import Environment, FileSystemLoader, select_autoescape

_CONVENTIONS = ["Shared packages over app src", "camelCase on the wire"]


def _render(profile):
    template_dir = Path(cli.__file__).parent / "config" / "templates"
    env = Environment(
        loader=FileSystemLoader(str(template_dir)), autoescape=select_autoescape()
    )
    template = env.get_template("briefing.md.jinja2")
    return template.render(
        profile=profile,
        worker_name="Quinn",
        worker_role="engineer",
        okrs=[],
        first_actions=[],
        rules_by_severity={},
        available_tools=[],
    )


def test_briefing_includes_profile_conventions():
    out = _render({"profile": "simpli", "conventions": _CONVENTIONS})
    for convention in _CONVENTIONS:
        assert convention in out, out


def test_briefing_without_profile_omits_conventions():
    out = _render(None)
    for convention in _CONVENTIONS:
        assert convention not in out
