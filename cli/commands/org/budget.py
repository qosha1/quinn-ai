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
                raise click.ClickException(f"Worker not found: {worker_id}")
        else:
            root = org.ceo
            if not root:
                raise click.ClickException("No CEO found. Initialize org first.")

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
        from cli.core.queries import get_worker_by_name
        target = get_worker_by_name(db, worker_name)
        if not target:
            raise click.ClickException(f"Worker not found: {worker_name}")

        # Determine source worker
        if from_worker:
            source = get_worker_by_name(db, from_worker)
            if not source:
                raise click.ClickException(f"Source worker not found: {from_worker}")
        else:
            source = org.ceo
            if not source:
                raise click.ClickException("No CEO found. Initialize org first.")

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
            raise click.ClickException(str(e))

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
            from cli.core.queries import get_worker_by_name
            worker = get_worker_by_name(db, worker_name)
            if not worker:
                raise click.ClickException(f"Worker not found: {worker_name}")
        else:
            worker = org.ceo
            if not worker:
                raise click.ClickException("No CEO found. Initialize org first.")

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
