"""LiveSessionDriver — bridge to the real claude_code provider.

The actual session interface is heavyweight (tmux + subprocess + onboarding
materials) and tightly coupled to the org filesystem layout. For the canary
we expose a minimal contract:

  - build_live_session(config: ProviderConfig) -> SessionInterface

Tests monkeypatch build_live_session to return a stub; production canary
runs delegate to the real claude_code spawner.

Lazy-imports the provider so unit tests don't need it on the path.
"""
from __future__ import annotations

from typing import Any

from .provider_config import ProviderConfig


def build_live_session(config: ProviderConfig) -> Any:
    """Construct a live SessionInterface based on ProviderConfig.

    For now this is a placeholder that imports the claude_code provider on
    demand. The actual canary flow drives the org via the qn CLI rather than
    the SessionInterface directly — see orchestrator.run_canary — so the
    SessionInterface return value is currently unused but kept for future
    direct-API canary flows.
    """
    if config.provider in ("claude_code", "anthropic"):
        # Lazy import; keeps unit tests light.
        try:
            from cli.providers import claude_code as _provider  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                f"cli.providers.claude_code is not available — cannot run live canary. {e}"
            ) from e
        return _LiveSessionStub(config)
    raise NotImplementedError(f"live driver for provider {config.provider!r} not wired")


class _LiveSessionStub:
    """Minimal placeholder until the canary needs direct SessionInterface access.

    Today's canary flow drives via the qn CLI (which spawns its own session
    via the registry); the BudgetGuard accounts for token usage by polling
    the org's session log. This stub satisfies the interface that
    tests/canary/unit/test_run_canary.py expects.
    """

    def __init__(self, config: ProviderConfig):
        self.config = config
        self.transcript_lines: list[str] = []
        self.usage = {"input_tokens": 0, "output_tokens": 0}

    def send(self, message: str) -> str:
        # In the real flow this would deliver the message to the live CEO
        # session via msgr or session.send(). Today's canary flow uses
        # `qn` directly so this is unused; left in place for a future
        # interface-driven canary.
        self.transcript_lines.append(f">>> {message}")
        return ""

    def close(self) -> None:
        pass
