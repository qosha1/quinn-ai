"""E2E tests for `qn org provider` + `qn config set-provider` + `qn config validate`.

Covers the read/write surface for provider configuration. No real LLM calls.
"""

import re

import pytest

import yaml


# ---------------------------------------------------------------------------
# qn org provider list
# ---------------------------------------------------------------------------


def test_provider_list_against_initialized_org(initialized_org, qn_runner):
    """`qn org provider list` lists the 4 built-in providers."""
    result = qn_runner(
        ["--org-path", str(initialized_org), "org", "provider", "list"],
    )
    assert result.returncode == 0, result.stderr

    # 4 providers ship out of the box (claude_code, codex, gemini, openai)
    for expected in ("claude_code", "codex", "gemini", "openai"):
        assert expected in result.stdout, (
            f"provider {expected!r} missing from list output:\n{result.stdout}"
        )

    # Total line confirms count
    assert re.search(r"Total:\s*[1-9]\d*\s*provider", result.stdout), result.stdout


def test_provider_list_uninitialized_org_still_lists(temp_org_dir, qn_runner):
    """provider list works even on an uninitialized path — providers are global."""
    result = qn_runner(
        ["--org-path", str(temp_org_dir), "org", "provider", "list"],
    )
    # Either succeeds (provider list is global) or fails with a clean message.
    # We only require: no Python traceback in output.
    assert "Traceback" not in result.stderr, result.stderr
    assert "Traceback" not in result.stdout, result.stdout


# ---------------------------------------------------------------------------
# qn config set-provider
# ---------------------------------------------------------------------------


def test_config_set_provider_writes_yaml(initialized_org, qn_runner):
    """`qn config set-provider <name>` updates config/providers.yaml's default.

    NOTE: 'qn config set-provider' currently restricts choices to
    {claude_code, anthropic, openai} via a hardcoded click.Choice, even
    though 'qn org provider list' shows 4 providers (codex, gemini also).
    Tracked separately as a P3 surface-inconsistency bug. We use openai
    here because it's accepted by both surfaces.
    """
    config_path = initialized_org / "config" / "providers.yaml"
    assert config_path.exists(), f"providers.yaml missing: {config_path}"

    before = yaml.safe_load(config_path.read_text()) or {}
    original_default = before.get("default")

    target = "openai" if original_default != "openai" else "claude_code"

    # 'qn config set-provider' takes its own --org-path AFTER the subcommand
    # (it's a subcommand-level option, not the top-level qn one).
    result = qn_runner(
        ["config", "set-provider", target, "--org-path", str(initialized_org)],
    )
    assert result.returncode == 0, f"set-provider failed: {result.stderr}"

    after = yaml.safe_load(config_path.read_text()) or {}
    assert after.get("default") == target, (
        f"providers.yaml 'default' should be {target!r} after set-provider, "
        f"got {after.get('default')!r}"
    )


def test_config_set_provider_unknown_fails_cleanly(initialized_org, qn_runner):
    """Unknown provider name returns non-zero, no traceback."""
    result = qn_runner(
        [
            "--org-path", str(initialized_org),
            "config", "set-provider",
            "totally-not-a-real-provider",
        ],
    )
    assert result.returncode != 0, "expected non-zero for unknown provider"
    assert "Traceback" not in result.stderr, result.stderr
    assert "Traceback" not in result.stdout, result.stdout


# ---------------------------------------------------------------------------
# qn config validate
# ---------------------------------------------------------------------------


def test_config_validate_on_initialized_org(initialized_org, qn_runner):
    """`qn config validate` runs cleanly against a freshly-initialized org."""
    result = qn_runner(
        ["--org-path", str(initialized_org), "config", "validate"],
    )
    # Validate may return 0 or non-zero depending on whether the dev env has
    # API keys set (env_hygiene strips them, so it'll likely warn/fail). We
    # only require: no Python traceback. The command must exit cleanly.
    assert "Traceback" not in result.stderr, result.stderr
    assert "Traceback" not in result.stdout, result.stdout
