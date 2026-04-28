"""ProviderConfig tests — env loading + validation."""
import pytest

from shared.testing.canary import ProviderConfig


def test_construct_with_required_fields():
    cfg = ProviderConfig(provider="claude_code", model="claude-sonnet-4-5", api_key_env="ANTHROPIC_API_KEY")
    assert cfg.provider == "claude_code"
    assert cfg.budget_usd == pytest.approx(0.50)  # default
    assert cfg.budget_seconds == 300  # default


def test_immutable():
    cfg = ProviderConfig(provider="claude_code", model="x", api_key_env="X")
    with pytest.raises((AttributeError, TypeError)):
        cfg.provider = "openai"


def test_from_env(monkeypatch):
    monkeypatch.setenv("QUINNAI_CANARY_PROVIDER", "anthropic")
    monkeypatch.setenv("QUINNAI_CANARY_MODEL", "claude-haiku-4-5")
    monkeypatch.setenv("QUINNAI_CANARY_API_KEY_ENV", "ANTHROPIC_API_KEY")
    monkeypatch.setenv("QUINNAI_CANARY_BUDGET_USD", "0.10")
    monkeypatch.setenv("QUINNAI_CANARY_BUDGET_SECONDS", "120")

    cfg = ProviderConfig.from_env()
    assert cfg.provider == "anthropic"
    assert cfg.model == "claude-haiku-4-5"
    assert cfg.budget_usd == pytest.approx(0.10)
    assert cfg.budget_seconds == 120


def test_from_env_uses_defaults_when_unset(monkeypatch):
    for var in (
        "QUINNAI_CANARY_PROVIDER", "QUINNAI_CANARY_MODEL",
        "QUINNAI_CANARY_API_KEY_ENV", "QUINNAI_CANARY_BUDGET_USD",
        "QUINNAI_CANARY_BUDGET_SECONDS",
    ):
        monkeypatch.delenv(var, raising=False)

    cfg = ProviderConfig.from_env()
    # Defaults
    assert cfg.provider == "claude_code"
    assert cfg.api_key_env == "ANTHROPIC_API_KEY"
    assert cfg.budget_usd == pytest.approx(0.50)
    assert cfg.budget_seconds == 300


def test_unknown_provider_rejected():
    with pytest.raises(ValueError, match="unknown provider"):
        ProviderConfig(provider="megacorp_ai", model="x", api_key_env="X")
