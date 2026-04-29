"""
qn org budget command group.

Provides budget management for the organization:
- qn org budget - Show org budget status
- qn org budget tree - Show budget cascade
- qn org budget allocate - Allocate budget to worker
- qn org budget transactions - Show spend history
"""

import click
from datetime import datetime, timedelta
from typing import Optional

from cli.commands.context import pass_context, Context
from cli.core.db import open_database, get_org_db_path
from cli.core.org import Org
from cli.core.rules import requires_rule_check
from cli.core.queries import (
    get_all_budget_pools,
    get_worker,
    get_workers_by_manager,
    get_worker_balance,
    get_worker_allocations,
    get_transactions_by_worker,
    BudgetBalance,
)
from cli.core.budget import (
    BudgetService,
    BudgetAllocationError,
)


@click.group()
def budget_cmd():
    """Manage organization budget.

    View budget status, allocate credits, and track spending.
    """
    pass


@budget_cmd.command("status")
@pass_context
def budget_status(ctx: Context):
    """Show organization budget status.

    Displays budget pools and top-level allocation summary.
    """
    org_path = ctx.org_path
    db_path = get_org_db_path(org_path)

    if not db_path.exists():
        raise click.ClickException(
            f"Organization not initialized at {org_path}\n"
            "Run 'qn org init' first."
        )

    db = open_database(db_path)

    try:
        org = Org.load(db)

        click.echo(f"Organization Budget: {org_path}")
        click.echo("")

        # Budget pools
        pools = get_all_budget_pools(db)
        if not pools:
            click.echo("No budget pools configured.")
            click.echo("Budget pools are created during org initialization.")
            return

        click.echo("Budget Pools:")
        for pool in pools:
            click.echo(f"  {pool.name}:")
            click.echo(f"    Total: {pool.total_credits:.2f} credits")
            # Handle both datetime objects and strings
            start_date = pool.period_start.date() if hasattr(pool.period_start, 'date') else pool.period_start[:10]
            end_date = pool.period_end.date() if hasattr(pool.period_end, 'date') else pool.period_end[:10]
            click.echo(f"    Period: {start_date} to {end_date}")

        # CEO budget if exists
        if org.ceo:
            balance = get_worker_balance(db, org.ceo.id)
            if balance:
                click.echo("")
                click.echo(f"CEO Budget ({org.ceo.name}):")
                click.echo(f"  Allocated: {balance.allocated:.2f}")
                click.echo(f"  Spent: {balance.spent:.2f}")
                click.echo(f"  Reserved: {balance.reserved:.2f}")
                click.echo(f"  Delegated: {balance.delegated:.2f}")
                click.echo(f"  Available: {balance.available:.2f}")

    finally:
        db.close()


@budget_cmd.command("tree")
@click.option("--worker-id", "-w", help="Show tree starting from this worker (default: CEO)")
@pass_context
def budget_tree(ctx: Context, worker_id: Optional[str]):
    """Show budget cascade tree.

    Displays how budget flows from CEO down through the hierarchy.
    """
    org_path = ctx.org_path
    db_path = get_org_db_path(org_path)

    if not db_path.exists():
        raise click.ClickException(
            f"Organization not initialized at {org_path}\n"
            "Run 'qn org init' first."
        )

    db = open_database(db_path)

    try:
        org = Org.load(db)

        # Determine root worker
        if worker_id:
            root = get_worker(db, worker_id)
            if not root:
                raise click.ClickException(
                    f"Worker '{worker_id}' not found.\n"
                    "Run 'qn org status' to see available workers."
                )
        else:
            root = org.ceo
            if not root:
                raise click.ClickException(
                    "No CEO found in organization.\n"
                    "Run 'qn org init' to initialize the organization with a CEO."
                )

        click.echo(f"Budget Tree (starting from {root.name}):")
        click.echo("")

        # Recursively print tree
        _print_budget_tree(db, root.id, root.name, indent=0)

    finally:
        db.close()


def _print_budget_tree(db, worker_id: str, worker_name: str, indent: int):
    """Recursively print budget tree."""
    prefix = "  " * indent

    balance = get_worker_balance(db, worker_id)
    if balance:
        click.echo(f"{prefix}{worker_name}:")
        click.echo(f"{prefix}  Allocated: {balance.allocated:.2f}, Spent: {balance.spent:.2f}, Available: {balance.available:.2f}")
    else:
        click.echo(f"{prefix}{worker_name}: (no budget)")

    # Get direct reports
    reports = get_workers_by_manager(db, worker_id)
    for report in reports:
        _print_budget_tree(db, report.id, report.name, indent + 1)


@budget_cmd.command("allocate")
@click.argument("worker_name")
@click.argument("amount", type=float)
@click.option("--from", "from_worker", help="Source worker (default: CEO)")
@requires_rule_check("qn-org.budget-allocate")
@pass_context
def budget_allocate(ctx: Context, worker_name: str, amount: float, from_worker: Optional[str]):
    """Allocate budget to a worker.

    WORKER_NAME: Name of worker to allocate budget to
    AMOUNT: Credits to allocate

    The source worker must be the target's manager and have can_delegate=True.
    """
    org_path = ctx.org_path
    db_path = get_org_db_path(org_path)

    if not db_path.exists():
        raise click.ClickException(
            f"Organization not initialized at {org_path}\n"
            "Run 'qn org init' first."
        )

    db = open_database(db_path)

    try:
        org = Org.load(db)
        budget_service = BudgetService(db)

        # Find target worker by name
        from cli.core.queries import resolve_worker
        target = resolve_worker(db, worker_name)
        if not target:
            raise click.ClickException(
                f"Worker '{worker_name}' not found.\n"
                "Run 'qn org status' to see available workers."
            )

        # Determine source worker
        if from_worker:
            source = resolve_worker(db, from_worker)
            if not source:
                raise click.ClickException(
                    f"Source worker '{from_worker}' not found.\n"
                    "Run 'qn org status' to see available workers."
                )
        else:
            source = org.ceo
            if not source:
                raise click.ClickException(
                    "No CEO found in organization.\n"
                    "Run 'qn org init' to initialize the organization with a CEO."
                )

        # Perform allocation
        try:
            allocation_id = budget_service.delegate_budget(
                source_worker_id=source.id,
                target_worker_id=target.id,
                amount=amount,
            )
            click.echo(f"Allocated {amount:.2f} credits to {worker_name}")
            click.echo(f"Allocation ID: {allocation_id}")

            # Show new balance
            balance = get_worker_balance(db, target.id)
            if balance:
                click.echo(f"New balance: {balance.available:.2f} available")

        except BudgetAllocationError as e:
            raise click.ClickException(
                f"Budget allocation failed: {e}\n"
                "Check available budget with 'qn org budget status'."
            )

        # quinn-ai-xdwo: auto-spawn the worker's session if it's been
        # stranded in 'starting' state since `qn org hire` (which couldn't
        # spawn because there was no budget yet). Without this an
        # autonomous CEO has to know to also run `qn org start --worker
        # <name>` after every allocation.
        _auto_spawn_if_pending(ctx, db, org, target)

    finally:
        db.close()


@budget_cmd.command("transactions")
@click.argument("worker_name", required=False)
@click.option("--type", "-t", "txn_type", help="Filter by type (spend, allocation, transfer_in, transfer_out)")
@click.option("--limit", "-n", default=20, help="Number of transactions to show (default: 20)")
@pass_context
def budget_transactions(ctx: Context, worker_name: Optional[str], txn_type: Optional[str], limit: int):
    """Show budget transactions.

    WORKER_NAME: Worker to show transactions for (default: CEO)

    Shows spending history and budget movements.
    """
    org_path = ctx.org_path
    db_path = get_org_db_path(org_path)

    if not db_path.exists():
        raise click.ClickException(
            f"Organization not initialized at {org_path}\n"
            "Run 'qn org init' first."
        )

    db = open_database(db_path)

    try:
        org = Org.load(db)

        # Determine worker
        if worker_name:
            from cli.core.queries import resolve_worker
            worker = resolve_worker(db, worker_name)
            if not worker:
                raise click.ClickException(
                    f"Worker '{worker_name}' not found.\n"
                    "Run 'qn org status' to see available workers."
                )
        else:
            worker = org.ceo
            if not worker:
                raise click.ClickException(
                    "No CEO found in organization.\n"
                    "Run 'qn org init' to initialize the organization with a CEO."
                )

        click.echo(f"Transactions for {worker.name}:")
        click.echo("")

        # Get transactions
        transactions = get_transactions_by_worker(
            db, worker.id,
            transaction_type=txn_type,
            limit=limit,
        )

        if not transactions:
            click.echo("No transactions found.")
            return

        # Format table
        click.echo(f"{'Type':<15} {'Amount':>12} {'Provider':<15} {'Model':<25} {'Time'}")
        click.echo("-" * 90)

        for txn in transactions:
            type_str = txn.type
            amount_str = f"{txn.amount:+.2f}"
            provider_str = txn.provider or "-"
            model_str = txn.model or "-"
            time_str = txn.created_at.strftime("%Y-%m-%d %H:%M") if txn.created_at else "-"

            click.echo(f"{type_str:<15} {amount_str:>12} {provider_str:<15} {model_str:<25} {time_str}")

        # Summary
        click.echo("")
        balance = get_worker_balance(db, worker.id)
        if balance:
            click.echo(f"Current Balance: {balance.available:.2f} available ({balance.spent:.2f} spent)")

    finally:
        db.close()


def _auto_spawn_if_pending(ctx, db, org, target_worker):
    """If the target's session is stuck pending, spawn it now (quinn-ai-xdwo).

    `qn org hire` swallows NoBudgetAllocationError and prints guidance to
    run `qn org budget allocate` + `qn org start --worker`. After this
    function runs at the end of `budget allocate`, the second step is no
    longer needed: we detect a worker that has no live session yet but is
    fully hired + just got budget, and bring them online.
    """
    try:
        from cli.core.worker import Worker
    except ImportError:
        return

    try:
        worker_obj = Worker.get(db, target_worker.id)
    except Exception:
        return

    # Only auto-spawn workers in lifecycle states that allow sessions and
    # don't already have one. Skips terminated/offboarding workers and
    # avoids stomping on a healthy live session.
    if worker_obj.lifecycle_status not in ("pending", "onboarding", "active"):
        return
    if worker_obj.is_session_active:
        return

    try:
        from cli.commands.org.session_utils import spawn_worker_session
        from cli.core.config import get_org_config_path
        from cli.core.config.loaders import load_providers_config
        from cli.core.onboarding import get_worker_env_vars, prepare_worker_onboarding
        from cli.core.storage import StorageManager
        from cli.providers.registry import load_providers_from_config
    except ImportError:
        return

    # Resolve provider the same way hire.py does — preferred_provider on the
    # worker first, then cost-based selection, then the org's session default.
    config_path = get_org_config_path(ctx.org_path) / "providers.yaml"
    try:
        registry = load_providers_from_config(config_path)
    except Exception:
        return

    provider_name = None
    cli_command = "claude"
    if worker_obj.preferred_provider:
        provider_name = worker_obj.preferred_provider
        if registry.has(provider_name):
            cli_command = registry.get(provider_name).cli_command
    if provider_name is None:
        try:
            provider = registry.select_for_worker(worker_obj.cost, worker_obj.skills)[0]
            provider_name = provider.name
            cli_command = provider.cli_command
        except ValueError:
            try:
                providers_cfg = load_providers_config(config_path)
                provider_name = providers_cfg.default or "claude_code"
            except Exception:
                provider_name = "claude_code"

    # Lifecycle nudge: hire flow leaves new workers in 'pending'; bring them
    # to 'active' before spawn the same way hire.py would.
    if worker_obj.lifecycle_status == "pending":
        try:
            worker_obj.start_onboarding()
            worker_obj.complete_onboarding()
        except Exception:
            pass  # don't block budget allocation on lifecycle quirks

    try:
        onboarding_ctx = prepare_worker_onboarding(db, worker_obj.id, ctx.org_path)
        storage = StorageManager(ctx.org_path, db)
        worker_dir = storage.get_worker_path(worker_obj.id)
        env_vars = get_worker_env_vars(onboarding_ctx, ctx.org_path, db)
        spawn_worker_session(
            worker=worker_obj,
            provider=provider_name,
            command=cli_command,
            args_str="--dangerously-skip-permissions",
            working_directory=worker_dir,
            env_vars=env_vars,
        )
        click.echo(f"Session started for {worker_obj.name}")
    except Exception as e:
        # Non-fatal — operator can run `qn org start --worker <name>` manually.
        click.echo(
            f"Note: Could not auto-spawn session for {worker_obj.name}: {e}\n"
            f"Run manually: qn org start --worker {worker_obj.name}"
        )
