"""ProviderConfig — env-loaded configuration for the live LLM canary."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

KNOWN_PROVIDERS = ("claude_code", "anthropic", "openai")


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    provider: str
    model: str
    api_key_env: str
    budget_usd: float = 0.50
    budget_seconds: int = 300

    def __post_init__(self) -> None:
        if self.provider not in KNOWN_PROVIDERS:
            raise ValueError(
                f"unknown provider {self.provider!r} "
                f"(known: {KNOWN_PROVIDERS})"
            )
        if self.budget_usd <= 0:
            raise ValueError(f"budget_usd must be > 0, got {self.budget_usd}")
        if self.budget_seconds <= 0:
            raise ValueError(f"budget_seconds must be > 0, got {self.budget_seconds}")

    @classmethod
    def from_env(cls) -> "ProviderConfig":
        return cls(
            provider=os.environ.get("QUINNAI_CANARY_PROVIDER", "claude_code"),
            model=os.environ.get("QUINNAI_CANARY_MODEL", "claude-sonnet-4-5"),
            api_key_env=os.environ.get("QUINNAI_CANARY_API_KEY_ENV", "ANTHROPIC_API_KEY"),
            budget_usd=float(os.environ.get("QUINNAI_CANARY_BUDGET_USD", "0.50")),
            budget_seconds=int(os.environ.get("QUINNAI_CANARY_BUDGET_SECONDS", "300")),
        )
