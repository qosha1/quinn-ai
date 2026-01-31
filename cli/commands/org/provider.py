"""
qn org provider command - manage CLI provider configuration.

Provides commands for:
- Listing available providers and their capabilities
- Getting/setting the org default provider
- Setting per-worker provider preferences
"""

from typing import Optional

import click

from commands.context import pass_context, Context
from core.db import open_database, get_org_db_path
from core.queries import get_worker, get_worker_by_name, update_worker_preferred_provider
from core.sessions.registry import get_default_registry
from core.worker import Worker


@click.group()
def provider_cmd():
    """Manage CLI provider configuration.

    \b
    Commands:
      list         List available providers and their capabilities
      default      Get or set the org default provider
      set-worker   Set a worker's preferred provider
      show-worker  Show a worker's provider configuration
    """
    pass


@provider_cmd.command("list")
@pass_context
def list_providers(ctx: Context):
    """List available CLI providers and their capabilities.

    Shows all registered session adapters that can be used to spawn
    worker sessions (e.g., claude_code, codex, gemini, cursor).
    """
    registry = get_default_registry()
    providers = registry.list_adapters()
    all_names = registry.list_all()

    if not providers:
        click.echo("No providers registered.")
        return

    click.echo("Available CLI Providers:")
    click.echo("")

    for name in sorted(providers):
        # Get aliases for this provider
        aliases = [a for a in all_names if a not in providers and registry.get_canonical_name(a) == name]

        click.echo(f"  {name}")
        if aliases:
            click.echo(f"    Aliases: {', '.join(sorted(aliases))}")

        # Show capabilities (from adapter class if available)
        adapter_class = registry.get(name)
        if hasattr(adapter_class, "CAPABILITIES"):
            caps = adapter_class.CAPABILITIES
            click.echo(f"    Capabilities: {', '.join(caps)}")

    click.echo("")
    click.echo(f"Total: {len(providers)} provider(s)")


@provider_cmd.command("default")
@click.argument("provider_name", required=False)
@pass_context
def set_default(ctx: Context, provider_name: Optional[str]):
    """Get or set the org default provider.

    \b
    Without arguments, shows the current default.
    With PROVIDER_NAME, sets it as the new default.

    \b
    Examples:
      qn org provider default           # Show current default
      qn org provider default claude_code  # Set default to claude_code
    """
    org_path = ctx.org_path
    config_path = org_path / "config" / "providers.yaml"

    if not config_path.exists():
        raise click.ClickException(
            f"Provider config not found: {config_path}\n"
            "Run 'qn org init' first."
        )

    import yaml

    # Load current config
    with open(config_path) as f:
        config = yaml.safe_load(f) or {}

    if provider_name is None:
        # Show current default
        current = config.get("default", "(not set)")
        click.echo(f"Default provider: {current}")
        return

    # Validate provider exists in registry
    registry = get_default_registry()
    if not registry.has(provider_name):
        available = registry.list_adapters()
        raise click.ClickException(
            f"Unknown provider '{provider_name}'.\n"
            f"Available: {', '.join(sorted(available))}"
        )

    # Update config
    config["default"] = provider_name

    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)

    click.echo(f"Default provider set to: {provider_name}")


@provider_cmd.command("set-worker")
@click.argument("worker")
@click.argument("provider_name")
@pass_context
def set_worker_provider(ctx: Context, worker: str, provider_name: str):
    """Set a worker's preferred CLI provider.

    WORKER can be a worker name or ID.
    PROVIDER_NAME is the CLI provider to use (e.g., claude_code, cursor).

    Use '--' as provider name to clear the preference (use org default).

    \b
    Examples:
      qn org provider set-worker alice claude_code
      qn org provider set-worker ceo cursor
      qn org provider set-worker alice --   # Clear preference
    """
    org_path = ctx.org_path
    db_path = get_org_db_path(org_path)

    if not db_path.exists():
        raise click.ClickException(
            f"Organization not initialized at {org_path}\n"
            "Run 'qn org init' first."
        )

    # Validate provider (unless clearing)
    if provider_name != "--":
        registry = get_default_registry()
        if not registry.has(provider_name):
            available = registry.list_adapters()
            raise click.ClickException(
                f"Unknown provider '{provider_name}'.\n"
                f"Available: {', '.join(sorted(available))}"
            )

    db = open_database(db_path)
    try:
        # Find worker
        worker_data = get_worker_by_name(db, worker)
        if not worker_data:
            worker_data = get_worker(db, worker)

        if not worker_data:
            raise click.ClickException(
                f"Worker '{worker}' not found.\n"
                "Use 'qn org status' to see available workers."
            )

        # Set or clear preference
        if provider_name == "--":
            update_worker_preferred_provider(db, worker_data.id, None)
            click.echo(f"Cleared provider preference for {worker_data.name}")
            click.echo("  Will use org default provider.")
        else:
            update_worker_preferred_provider(db, worker_data.id, provider_name)
            click.echo(f"Set preferred provider for {worker_data.name}: {provider_name}")

    finally:
        db.close()


@provider_cmd.command("show-worker")
@click.argument("worker")
@pass_context
def show_worker_provider(ctx: Context, worker: str):
    """Show a worker's provider configuration.

    WORKER can be a worker name or ID.

    Shows the worker's preferred provider and the effective provider
    that would be used (considering org default).

    \b
    Examples:
      qn org provider show-worker alice
      qn org provider show-worker ceo
    """
    org_path = ctx.org_path
    db_path = get_org_db_path(org_path)

    if not db_path.exists():
        raise click.ClickException(
            f"Organization not initialized at {org_path}\n"
            "Run 'qn org init' first."
        )

    # Load org config for default
    config_path = org_path / "config" / "providers.yaml"
    org_default = None
    if config_path.exists():
        import yaml
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
        org_default = config.get("default")

    db = open_database(db_path)
    try:
        # Find worker
        worker_data = get_worker_by_name(db, worker)
        if not worker_data:
            worker_data = get_worker(db, worker)

        if not worker_data:
            raise click.ClickException(
                f"Worker '{worker}' not found.\n"
                "Use 'qn org status' to see available workers."
            )

        # Create Worker wrapper to get preferred_provider
        worker_obj = Worker(db, worker_data.id, org_path=org_path)

        click.echo(f"Provider configuration for {worker_obj.name}:")
        click.echo("")
        click.echo(f"  Preferred provider: {worker_obj.preferred_provider or '(not set)'}")
        click.echo(f"  Org default:        {org_default or '(not set)'}")

        # Determine effective provider
        effective = worker_obj.preferred_provider or org_default or "claude_code"
        click.echo(f"  Effective provider: {effective}")

    finally:
        db.close()


@provider_cmd.command("validate")
@pass_context
def validate_providers(ctx: Context):
    """Validate provider configuration.

    Checks that:
    - The org default provider is registered
    - All authorized providers are registered
    - Workers' preferred providers are valid
    """
    org_path = ctx.org_path
    config_path = org_path / "config" / "providers.yaml"

    if not config_path.exists():
        raise click.ClickException(
            f"Provider config not found: {config_path}\n"
            "Run 'qn org init' first."
        )

    import yaml

    with open(config_path) as f:
        config = yaml.safe_load(f) or {}

    registry = get_default_registry()
    available = set(registry.list_all())
    errors = []
    warnings = []

    # Check default provider
    default = config.get("default")
    if default:
        if default not in available:
            errors.append(f"Default provider '{default}' is not registered")
    else:
        warnings.append("No default provider set")

    # Check authorized providers
    authorized = config.get("authorized_providers", [])
    for name in authorized:
        if name not in available:
            errors.append(f"Authorized provider '{name}' is not registered")

    # Check worker preferences
    db_path = get_org_db_path(org_path)
    if db_path.exists():
        db = open_database(db_path)
        try:
            rows = db.fetchall(
                "SELECT id, name, preferred_provider FROM workers WHERE preferred_provider IS NOT NULL"
            )
            for row in rows:
                provider = row["preferred_provider"]
                if provider not in available:
                    errors.append(
                        f"Worker '{row['name']}' has invalid preferred_provider: '{provider}'"
                    )
        finally:
            db.close()

    # Report results
    if errors:
        click.echo("Validation FAILED:")
        for error in errors:
            click.echo(f"  ERROR: {error}")
        for warning in warnings:
            click.echo(f"  WARNING: {warning}")
        raise click.ClickException("Provider configuration has errors")
    elif warnings:
        click.echo("Validation passed with warnings:")
        for warning in warnings:
            click.echo(f"  WARNING: {warning}")
    else:
        click.echo("Validation passed - all providers are valid")
