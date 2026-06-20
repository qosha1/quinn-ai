"""Initial-task prompts must read as legitimate onboarding, not prompt injection.

quinn-ai-58rw: live canary workers (Opus 4.7+ / Sonnet 4.6) refused to act on
their onboarding because the CEO/worker INITIAL_TASK templates used
injection-shaped framing ("=== EXECUTE THIS NOW ===", "You ARE the worker",
"BEGIN EXECUTING immediately", "Do not summarize this") and absolutist
anti-confirmation language ("Do not ask for confirmation", "no confirmation
needed", "ship today"). Security-conscious models correctly flag exactly this
shape as authority-laundering and refuse.

These tests encode the lesson: the templates must NOT contain that language,
while STILL keeping the legitimate onboarding anchors (intro message, inbox
discipline, first steps). This mirrors the bd memory
`canary-okr-descriptions-must-not-use-imperative-anti`.
"""
import re

import pytest

from cli.core.constants.prompts import (
    INITIAL_TASK_KIND_CEO,
    INITIAL_TASK_KIND_CEO_HOST,
    INITIAL_TASK_KIND_WORKER,
)
from cli.core.prompts import render_initial_task

# Render each template from its file (the prompts now live under
# cli/config/templates/, not as magic strings — quinn-ai-58rw).
_CTX = {"self_intro": "Alex, the CEO", "chat_intro": "I'm Alex.",
        "name": "Alex", "role": "engineer"}
_INITIAL_PROMPT_TEMPLATE = render_initial_task(INITIAL_TASK_KIND_CEO, **_CTX)
_INITIAL_PROMPT_TEMPLATE_HOST_MODE = render_initial_task(INITIAL_TASK_KIND_CEO_HOST, **_CTX)
_WORKER_INITIAL_TASK_TEMPLATE = render_initial_task(INITIAL_TASK_KIND_WORKER, **_CTX)


# Phrases that give a prompt the *shape* of an injection / authority-laundering
# attack, or that absolutely forbid the model from ever confirming. Matched
# case-insensitively as substrings.
BANNED_PHRASES = [
    "execute this now",
    "begin executing immediately",
    "you are that worker",
    "you are the worker described",
    "do not summarize this",
    "do not describe what it would do",
    "do not ask for confirmation",
    "no confirmation needed",
    "execute now",
    "ship today",
    "do not wait for further instructions",
    "those phrases are blockers",
    "execute immediately without asking",
]

ALL_TEMPLATES = {
    "ceo": _INITIAL_PROMPT_TEMPLATE,
    "ceo_host": _INITIAL_PROMPT_TEMPLATE_HOST_MODE,
    "worker": _WORKER_INITIAL_TASK_TEMPLATE,
}


@pytest.mark.parametrize("name,template", ALL_TEMPLATES.items())
def test_template_has_no_injection_shaped_phrases(name, template):
    low = template.lower()
    hits = [p for p in BANNED_PHRASES if p in low]
    assert not hits, (
        f"{name} INITIAL_TASK template contains injection-shaped / "
        f"anti-confirmation phrasing {hits!r} — security-conscious workers "
        f"refuse this (quinn-ai-58rw). Reframe as legitimate tasking."
    )


@pytest.mark.parametrize("name,template", ALL_TEMPLATES.items())
def test_template_does_not_open_with_screaming_framing(name, template):
    """No '=== EXECUTE ... ===' banner header — the hallmark of the old framing."""
    head = template.lstrip()[:200].lower()
    assert "===" not in head or "execute" not in head, (
        f"{name} template still opens with an '=== EXECUTE ... ===' banner; "
        f"that framing reads as injection. Open with normal onboarding."
    )


def test_ceo_templates_keep_legitimate_anchors():
    """Reframing must NOT gut the real onboarding content."""
    for name in ("ceo", "ceo_host"):
        t = ALL_TEMPLATES[name]
        assert "msgr inbox" in t, f"{name}: must keep inbox discipline"
        assert "BRIEFING.md" in t, f"{name}: must point at the briefing"


def test_worker_template_keeps_legitimate_anchors():
    t = _WORKER_INITIAL_TASK_TEMPLATE
    assert "BRIEFING.md" in t, "worker: must point at the briefing"
    assert "bd ready" in t, "worker: must tell the worker to find ready work"
    # Still establishes identity (rendered name/role, not injection-shaped).
    assert _CTX["name"] in t and _CTX["role"] in t, (
        "worker: must address the worker by name/role"
    )
