"""
qn config commands for configuration validation.

Provides startup checks for required environment variables and API access.
"""

import os
from pathlib import Path
from typing import Optional

import click

from commands.context import pass_context, Context
from core.config import (
    ProvidersConfig,
    ProviderSettings,
    load_providers_config,
    get_org_config_path,
    validate_providers_config,
    mask_secret,
    check_plaintext_api_keys,
)
from providers.base import ProviderConfig, AuthenticationError, ProviderConnectionError


# Required environment variables for each provider
PROVIDER_ENV_VARS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}


def check_env_vars() -> dict[str, tuple[bool, str]]:
    """Check if required environment variables are set.

    Returns:
        Dict mapping provider name to (is_set, env_var_name) tuple
    """
    results = {}
    for provider, env_var in PROVIDER_ENV_VARS.items():
        value = os.environ.get(env_var, "")
        results[provider] = (bool(value), env_var)
    return results


def check_provider_connection(provider_name: str, api_key: str) -> tuple[bool, str]:
    """Test API connectivity for a provider.

    Args:
        provider_name: Name of the provider (anthropic, openai)
        api_key: API key to test

    Returns:
        Tuple of (success, message)
    """
    if not api_key:
        return False, "No API key configured"

    try:
        config = ProviderConfig(api_key=api_key, timeout=10)

        if provider_name == "anthropic":
            from providers import get_anthropic_provider
            provider_class = get_anthropic_provider()
            provider = provider_class(config)
            # Make a minimal API call to test authentication
            from shared.core import Message
            result = provider.complete(
                messages=[Message(role="user", content="Hi")],
                max_tokens=5,
            )
            return True, f"Connected successfully (model: {result.model})"

        elif provider_name == "openai":
            from providers import get_openai_provider
            provider_class = get_openai_provider()
            provider = provider_class(config)
            from shared.core import Message
            result = provider.complete(
                messages=[Message(role="user", content="Hi")],
                model="gpt-4o-mini",
                max_tokens=5,
            )
            return True, f"Connected successfully (model: {result.model})"

        else:
            return False, f"Unknown provider: {provider_name}"

    except AuthenticationError as e:
        return False, f"Authentication failed: {e}"
    except ProviderConnectionError as e:
        return False, f"Connection failed: {e}"
    except ImportError as e:
        return False, f"SDK not installed: {e}"
    except Exception as e:
        return False, f"Error: {e}"


@click.group()
def config():
    """Configuration management commands."""
    pass


@config.command("set-provider")
@click.argument("provider", type=click.Choice(["claude_code", "anthropic", "openai"]))
@click.option(
    "--org-path",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to org folder",
)
def set_provider_cmd(provider: str, org_path: Path):
    """Set the default AI provider for an organization.

    Changes the default provider in config/providers.yaml.
    This determines which AI service the org uses for worker sessions.

    \b
    Examples:
        qn config set-provider claude_code --org-path ~/orgs/acme
        qn config set-provider anthropic --org-path ./my-org
    """
    import yaml

    config_path = get_org_config_path(org_path)
    providers_path = config_path / "providers.yaml"

    if not providers_path.exists():
        click.echo(click.style(
            f"Error: providers.yaml not found at {providers_path}",
            fg="red"
        ))
        raise SystemExit(1)

    # Read current config
    try:
        with open(providers_path) as f:
            config_data = yaml.safe_load(f)
    except Exception as e:
        click.echo(click.style(f"Error reading config: {e}", fg="red"))
        raise SystemExit(1)

    # Verify provider exists in config
    if provider not in config_data.get("providers", {}):
        click.echo(click.style(
            f"Error: Provider '{provider}' not found in providers.yaml",
            fg="red"
        ))
        click.echo(f"Available providers: {', '.join(config_data.get('providers', {}).keys())}")
        raise SystemExit(1)

    # Update default
    old_default = config_data.get("default", "unknown")
    config_data["default"] = provider

    # Write back
    try:
        with open(providers_path, "w") as f:
            yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)

        click.echo(click.style("✓", fg="green") + f" Default provider updated")
        click.echo(f"  {old_default} → {click.style(provider, fg='green')}")
        click.echo(f"  Config: {providers_path}")

    except Exception as e:
        click.echo(click.style(f"Error writing config: {e}", fg="red"))
        raise SystemExit(1)


@config.command("validate")
@click.option(
    "--test-connection",
    is_flag=True,
    default=False,
    help="Test actual API connectivity (makes API calls)",
)
@click.option(
    "--org-path",
    type=click.Path(exists=True, path_type=Path),
    help="Path to org folder to validate providers.yaml",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Show detailed output",
)
def validate_cmd(test_connection: bool, org_path: Optional[Path], verbose: bool):
    """Validate configuration and environment setup.

    Checks if required environment variables are set and optionally
    tests API connectivity. Use this before running org commands to
    catch configuration issues early.

    \b
    Examples:
        qn config validate                    # Basic env var check
        qn config validate --test-connection  # Test actual API access
        qn config validate --org-path ./my-org  # Validate providers.yaml
    """
    has_errors = False

    # Check environment variables
    click.echo("Environment Variables:")
    click.echo("-" * 40)

    env_results = check_env_vars()
    any_key_set = False

    for provider, (is_set, env_var) in env_results.items():
        if is_set:
            any_key_set = True
            value = os.environ.get(env_var, "")
            masked = mask_secret(value)
            click.echo(f"  {env_var}: {click.style('SET', fg='green')} ({masked})")
        else:
            click.echo(f"  {env_var}: {click.style('NOT SET', fg='yellow')}")

    if not any_key_set:
        has_errors = True
        click.echo("")
        click.echo(click.style(
            "Warning: No API keys found in environment.",
            fg="yellow"
        ))
        click.echo("Set at least one of: ANTHROPIC_API_KEY, OPENAI_API_KEY")
        click.echo("")
        click.echo("To load environment variables, run:")
        click.echo("  set -a && source .envs/.local/.django && set +a")

    click.echo("")

    # Validate providers.yaml if org-path provided
    if org_path:
        click.echo("Providers Configuration:")
        click.echo("-" * 40)

        config_path = get_org_config_path(org_path)
        providers_path = config_path / "providers.yaml"

        if not providers_path.exists():
            has_errors = True
            click.echo(click.style(
                f"  providers.yaml not found at {providers_path}",
                fg="red"
            ))
        else:
            try:
                providers_config = load_providers_config(providers_path)

                # Check for plaintext API keys
                plaintext_keys = check_plaintext_api_keys(providers_path)
                if plaintext_keys:
                    click.echo(click.style(
                        "  Warning: Plaintext API keys detected!",
                        fg="yellow"
                    ))
                    for provider_name, field in plaintext_keys:
                        click.echo(f"    - {provider_name}.{field}")
                    click.echo("  Use environment variable references instead: ${ENV_VAR}")
                    click.echo("")

                # Validate configuration
                errors = validate_providers_config(providers_config)

                if errors:
                    has_errors = True
                    click.echo(click.style("  Configuration errors:", fg="red"))
                    for err in errors:
                        click.echo(f"    - {err}")
                else:
                    click.echo(click.style("  Configuration valid", fg="green"))

                # Show provider details
                if verbose:
                    click.echo("")
                    click.echo("  Providers:")
                    for name, settings in providers_config.providers.items():
                        status = "enabled" if settings.enabled else "disabled"
                        status_color = "green" if settings.enabled else "white"
                        has_key = "key set" if settings.api_key else "no key"
                        key_color = "green" if settings.api_key else "yellow"
                        click.echo(
                            f"    {name}: "
                            f"{click.style(status, fg=status_color)}, "
                            f"{click.style(has_key, fg=key_color)}"
                        )

                    click.echo(f"  Default provider: {providers_config.default}")

            except FileNotFoundError as e:
                has_errors = True
                click.echo(click.style(f"  Error: {e}", fg="red"))
            except ValueError as e:
                has_errors = True
                click.echo(click.style(f"  Invalid config: {e}", fg="red"))

        click.echo("")

    # Test API connectivity if requested
    if test_connection:
        click.echo("API Connectivity Tests:")
        click.echo("-" * 40)

        for provider, (is_set, env_var) in env_results.items():
            if not is_set:
                click.echo(f"  {provider}: {click.style('SKIPPED', fg='white')} (no key)")
                continue

            api_key = os.environ.get(env_var, "")
            click.echo(f"  {provider}: Testing...", nl=False)

            success, message = check_provider_connection(provider, api_key)

            if success:
                click.echo(f"\r  {provider}: {click.style('OK', fg='green')} - {message}")
            else:
                has_errors = True
                click.echo(f"\r  {provider}: {click.style('FAILED', fg='red')} - {message}")

        click.echo("")

    # Summary
    if has_errors:
        click.echo(click.style("Validation completed with warnings/errors.", fg="yellow"))
        raise SystemExit(1)
    else:
        click.echo(click.style("Validation passed.", fg="green"))
