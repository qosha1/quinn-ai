"""
Unit tests for budget tracking operations.
"""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from cli.core.db import Database, init_database
from cli.core.queries import (
    # Workers and teams (for setup)
    create_team,
    create_worker,
    # Budget Pools
    create_budget_pool,
    get_budget_pool,
    get_all_budget_pools,
    update_budget_pool,
    delete_budget_pool,
    # Budget Allocations
    create_budget_allocation,
    get_budget_allocation,
    get_worker_allocations,
    get_current_allocation,
    get_allocations_by_pool,
    update_allocation_spend,
    delete_budget_allocation,
    # Budget Transactions
    create_budget_transaction,
    get_budget_transaction,
    get_transactions_by_allocation,
    get_transactions_by_worker,
    # Budget Balances
    create_budget_balance,
    get_budget_balance,
    get_worker_balance,
    get_all_worker_balances,
    delete_budget_balance,
    get_pool_allocated_total,
    is_worker_manager,
)


@pytest.fixture
def db_path():
    """Create a temporary database path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "live" / "quinn.db"


@pytest.fixture
def db(db_path):
    """Create and initialize a test database."""
    database = init_database(db_path)
    yield database
    database.close()


@pytest.fixture
def period():
    """Create a test budget period."""
    now = datetime.now()
    return {
        "start": now - timedelta(days=15),
        "end": now + timedelta(days=15),
    }


@pytest.fixture
def team(db):
    """Create a test team."""
    return create_team(db, "Engineering")


@pytest.fixture
def ceo(db, team):
    """Create a CEO worker."""
    return create_worker(db, "Alice CEO", "CEO", team.id, 90)


@pytest.fixture
def manager(db, team, ceo):
    """Create a manager worker under CEO."""
    return create_worker(db, "Bob Manager", "Manager", team.id, 70, manager_id=ceo.id)


@pytest.fixture
def developer(db, team, manager):
    """Create a developer worker under manager."""
    return create_worker(db, "Charlie Dev", "Developer", team.id, 50, manager_id=manager.id)


@pytest.fixture
def pool(db, period):
    """Create a test budget pool."""
    return create_budget_pool(
        db,
        name="Q1 2026 Budget",
        total_credits=1000000.0,
        period_start=period["start"],
        period_end=period["end"],
    )


class TestBudgetPoolQueries:
    """Test budget pool CRUD operations."""

    def test_create_budget_pool(self, db, period):
        """Should create a new budget pool."""
        pool = create_budget_pool(
            db,
            name="January 2026",
            total_credits=500000.0,
            period_start=period["start"],
            period_end=period["end"],
        )
        assert pool.name == "January 2026"
        assert pool.total_credits == 500000.0
        assert pool.id.startswith("pool-")

    def test_get_budget_pool(self, db, pool):
        """Should get budget pool by ID."""
        fetched = get_budget_pool(db, pool.id)
        assert fetched is not None
        assert fetched.name == pool.name
        assert fetched.total_credits == pool.total_credits

    def test_get_budget_pool_not_found(self, db):
        """Should return None for missing pool."""
        result = get_budget_pool(db, "nonexistent")
        assert result is None

    def test_get_all_budget_pools(self, db, period):
        """Should get all budget pools."""
        create_budget_pool(db, "Pool 1", 100000.0, period["start"], period["end"])
        create_budget_pool(db, "Pool 2", 200000.0, period["start"], period["end"])
        pools = get_all_budget_pools(db)
        assert len(pools) == 2

    def test_update_budget_pool(self, db, pool):
        """Should update budget pool."""
        update_budget_pool(db, pool.id, total_credits=750000.0, name="Updated Pool")
        fetched = get_budget_pool(db, pool.id)
        assert fetched.total_credits == 750000.0
        assert fetched.name == "Updated Pool"

    def test_delete_budget_pool(self, db, pool):
        """Should delete budget pool."""
        delete_budget_pool(db, pool.id)
        result = get_budget_pool(db, pool.id)
        assert result is None


class TestBudgetAllocationQueries:
    """Test budget allocation CRUD operations."""

    def test_create_allocation_from_pool(self, db, pool, ceo):
        """Should create allocation from pool."""
        allocation = create_budget_allocation(
            db,
            worker_id=ceo.id,
            allocated_credits=500000.0,
            period_start=pool.period_start,
            period_end=pool.period_end,
            pool_id=pool.id,
            can_delegate=True,
            delegation_limit=100000.0,
        )
        assert allocation.worker_id == ceo.id
        assert allocation.pool_id == pool.id
        assert allocation.source_worker_id is None
        assert allocation.allocated_credits == 500000.0
        assert allocation.can_delegate is True

    def test_create_allocation_from_manager(self, db, pool, ceo, manager):
        """Should create allocation from manager delegation."""
        # First create CEO allocation
        ceo_alloc = create_budget_allocation(
            db,
            worker_id=ceo.id,
            allocated_credits=500000.0,
            period_start=pool.period_start,
            period_end=pool.period_end,
            pool_id=pool.id,
            can_delegate=True,
        )

        # Manager allocation from CEO
        mgr_alloc = create_budget_allocation(
            db,
            worker_id=manager.id,
            allocated_credits=100000.0,
            period_start=pool.period_start,
            period_end=pool.period_end,
            source_worker_id=ceo.id,
            can_delegate=True,
        )
        assert mgr_alloc.source_worker_id == ceo.id
        assert mgr_alloc.pool_id is None
        assert mgr_alloc.allocated_credits == 100000.0

    def test_get_budget_allocation(self, db, pool, ceo):
        """Should get allocation by ID."""
        created = create_budget_allocation(
            db,
            worker_id=ceo.id,
            allocated_credits=500000.0,
            period_start=pool.period_start,
            period_end=pool.period_end,
            pool_id=pool.id,
        )
        fetched = get_budget_allocation(db, created.id)
        assert fetched is not None
        assert fetched.worker_id == ceo.id

    def test_get_worker_allocations(self, db, period, pool, ceo):
        """Should get all allocations for a worker."""
        # Create two allocations for different periods
        create_budget_allocation(
            db,
            worker_id=ceo.id,
            allocated_credits=500000.0,
            period_start=period["start"],
            period_end=period["end"],
            pool_id=pool.id,
        )

        allocations = get_worker_allocations(db, ceo.id)
        assert len(allocations) == 1
        assert allocations[0].worker_id == ceo.id

    def test_get_current_allocation(self, db, pool, ceo):
        """Should get current active allocation."""
        create_budget_allocation(
            db,
            worker_id=ceo.id,
            allocated_credits=500000.0,
            period_start=pool.period_start,
            period_end=pool.period_end,
            pool_id=pool.id,
        )

        current = get_current_allocation(db, ceo.id)
        assert current is not None
        assert current.worker_id == ceo.id

    def test_get_current_allocation_none_outside_period(self, db, team):
        """Should return None when no allocation in current period."""
        worker = create_worker(db, "Test Worker", "Dev", team.id, 50)
        past_start = datetime.now() - timedelta(days=60)
        past_end = datetime.now() - timedelta(days=30)

        pool = create_budget_pool(db, "Past Pool", 100000.0, past_start, past_end)
        create_budget_allocation(
            db,
            worker_id=worker.id,
            allocated_credits=10000.0,
            period_start=past_start,
            period_end=past_end,
            pool_id=pool.id,
        )

        current = get_current_allocation(db, worker.id)
        assert current is None

    def test_get_allocations_by_pool(self, db, pool, ceo, manager):
        """Should get all allocations from a pool."""
        create_budget_allocation(
            db,
            worker_id=ceo.id,
            allocated_credits=500000.0,
            period_start=pool.period_start,
            period_end=pool.period_end,
            pool_id=pool.id,
        )
        create_budget_allocation(
            db,
            worker_id=manager.id,
            allocated_credits=100000.0,
            period_start=pool.period_start,
            period_end=pool.period_end,
            pool_id=pool.id,
        )

        allocations = get_allocations_by_pool(db, pool.id)
        assert len(allocations) == 2

    def test_update_allocation_spend(self, db, pool, ceo):
        """Should update spend and reserve amounts."""
        allocation = create_budget_allocation(
            db,
            worker_id=ceo.id,
            allocated_credits=500000.0,
            period_start=pool.period_start,
            period_end=pool.period_end,
            pool_id=pool.id,
        )

        update_allocation_spend(db, allocation.id, spent_credits=10000.0, reserved_credits=5000.0)
        fetched = get_budget_allocation(db, allocation.id)
        assert fetched.spent_credits == 10000.0
        assert fetched.reserved_credits == 5000.0

    def test_delete_budget_allocation(self, db, pool, ceo):
        """Should delete allocation."""
        allocation = create_budget_allocation(
            db,
            worker_id=ceo.id,
            allocated_credits=500000.0,
            period_start=pool.period_start,
            period_end=pool.period_end,
            pool_id=pool.id,
        )
        delete_budget_allocation(db, allocation.id)
        result = get_budget_allocation(db, allocation.id)
        assert result is None


class TestBudgetTransactionQueries:
    """Test budget transaction CRUD operations."""

    @pytest.fixture
    def allocation(self, db, pool, ceo):
        """Create a test allocation."""
        return create_budget_allocation(
            db,
            worker_id=ceo.id,
            allocated_credits=500000.0,
            period_start=pool.period_start,
            period_end=pool.period_end,
            pool_id=pool.id,
        )

    def test_create_allocation_transaction(self, db, allocation, ceo):
        """Should create allocation transaction."""
        txn = create_budget_transaction(
            db,
            allocation_id=allocation.id,
            worker_id=ceo.id,
            transaction_type="allocation",
            amount=500000.0,
            description="Initial allocation from pool",
        )
        assert txn.type == "allocation"
        assert txn.amount == 500000.0
        assert txn.id.startswith("txn-")

    def test_create_spend_transaction(self, db, allocation, ceo):
        """Should create spend transaction with provider details."""
        txn = create_budget_transaction(
            db,
            allocation_id=allocation.id,
            worker_id=ceo.id,
            transaction_type="spend",
            amount=-1500.0,
            provider="anthropic",
            model="claude-3-5-sonnet",
            input_tokens=5000,
            output_tokens=2000,
            reference_type="task",
            reference_id="task-123",
            description="API call for task",
        )
        assert txn.type == "spend"
        assert txn.amount == -1500.0
        assert txn.provider == "anthropic"
        assert txn.model == "claude-3-5-sonnet"
        assert txn.input_tokens == 5000
        assert txn.output_tokens == 2000

    def test_create_reserve_release_transactions(self, db, allocation, ceo):
        """Should create reserve and release transactions."""
        reserve_txn = create_budget_transaction(
            db,
            allocation_id=allocation.id,
            worker_id=ceo.id,
            transaction_type="reserve",
            amount=2000.0,
            description="Reserved for API call",
        )
        assert reserve_txn.type == "reserve"

        release_txn = create_budget_transaction(
            db,
            allocation_id=allocation.id,
            worker_id=ceo.id,
            transaction_type="release",
            amount=-2000.0,
            description="Released reservation",
        )
        assert release_txn.type == "release"

    def test_get_budget_transaction(self, db, allocation, ceo):
        """Should get transaction by ID."""
        created = create_budget_transaction(
            db,
            allocation_id=allocation.id,
            worker_id=ceo.id,
            transaction_type="allocation",
            amount=500000.0,
        )
        fetched = get_budget_transaction(db, created.id)
        assert fetched is not None
        assert fetched.id == created.id

    def test_get_transactions_by_allocation(self, db, allocation, ceo):
        """Should get all transactions for an allocation."""
        create_budget_transaction(
            db, allocation.id, ceo.id, "allocation", 500000.0
        )
        create_budget_transaction(
            db, allocation.id, ceo.id, "spend", -1000.0
        )
        create_budget_transaction(
            db, allocation.id, ceo.id, "spend", -500.0
        )

        transactions = get_transactions_by_allocation(db, allocation.id)
        assert len(transactions) == 3

    def test_get_transactions_by_worker(self, db, allocation, ceo):
        """Should get transactions for a worker."""
        create_budget_transaction(
            db, allocation.id, ceo.id, "allocation", 500000.0
        )
        create_budget_transaction(
            db, allocation.id, ceo.id, "spend", -1000.0
        )

        transactions = get_transactions_by_worker(db, ceo.id)
        assert len(transactions) == 2

    def test_get_transactions_by_worker_filtered_by_type(self, db, allocation, ceo):
        """Should filter transactions by type."""
        create_budget_transaction(
            db, allocation.id, ceo.id, "allocation", 500000.0
        )
        create_budget_transaction(
            db, allocation.id, ceo.id, "spend", -1000.0
        )
        create_budget_transaction(
            db, allocation.id, ceo.id, "spend", -500.0
        )

        spend_txns = get_transactions_by_worker(db, ceo.id, transaction_type="spend")
        assert len(spend_txns) == 2

    def test_get_transactions_by_worker_filtered_by_time(self, db, allocation, ceo):
        """Should filter transactions by time."""
        create_budget_transaction(
            db, allocation.id, ceo.id, "allocation", 500000.0
        )
        create_budget_transaction(
            db, allocation.id, ceo.id, "spend", -1000.0
        )

        # Get transactions since 1 hour ago
        since = datetime.now() - timedelta(hours=1)
        transactions = get_transactions_by_worker(db, ceo.id, since=since)
        assert len(transactions) == 2


class TestBudgetBalanceQueries:
    """Test budget balance CRUD operations."""

    @pytest.fixture
    def allocation(self, db, pool, ceo):
        """Create a test allocation."""
        return create_budget_allocation(
            db,
            worker_id=ceo.id,
            allocated_credits=500000.0,
            period_start=pool.period_start,
            period_end=pool.period_end,
            pool_id=pool.id,
        )

    def test_create_budget_balance(self, db, allocation, ceo, pool):
        """Should create budget balance."""
        balance = create_budget_balance(
            db,
            allocation_id=allocation.id,
            worker_id=ceo.id,
            allocated=500000.0,
            period_start=pool.period_start,
            period_end=pool.period_end,
        )
        assert balance.allocation_id == allocation.id
        assert balance.allocated == 500000.0
        assert balance.available == 500000.0
        assert balance.spent == 0.0
        assert balance.reserved == 0.0
        assert balance.delegated == 0.0

    def test_get_budget_balance(self, db, allocation, ceo, pool):
        """Should get balance by allocation ID."""
        create_budget_balance(
            db, allocation.id, ceo.id, 500000.0, pool.period_start, pool.period_end
        )
        balance = get_budget_balance(db, allocation.id)
        assert balance is not None
        assert balance.allocated == 500000.0

    def test_get_worker_balance(self, db, allocation, ceo, pool):
        """Should get current balance for worker."""
        create_budget_balance(
            db, allocation.id, ceo.id, 500000.0, pool.period_start, pool.period_end
        )
        balance = get_worker_balance(db, ceo.id)
        assert balance is not None
        assert balance.worker_id == ceo.id

    def test_get_all_worker_balances(self, db, pool, ceo, manager):
        """Should get all current balances."""
        alloc1 = create_budget_allocation(
            db, ceo.id, 500000.0, pool.period_start, pool.period_end, pool_id=pool.id
        )
        alloc2 = create_budget_allocation(
            db, manager.id, 100000.0, pool.period_start, pool.period_end, pool_id=pool.id
        )
        create_budget_balance(
            db, alloc1.id, ceo.id, 500000.0, pool.period_start, pool.period_end
        )
        create_budget_balance(
            db, alloc2.id, manager.id, 100000.0, pool.period_start, pool.period_end
        )

        balances = get_all_worker_balances(db)
        assert len(balances) == 2

    def test_delete_budget_balance(self, db, allocation, ceo, pool):
        """Should delete balance."""
        create_budget_balance(
            db, allocation.id, ceo.id, 500000.0, pool.period_start, pool.period_end
        )
        delete_budget_balance(db, allocation.id)
        result = get_budget_balance(db, allocation.id)
        assert result is None

    def test_balance_trigger_on_spend(self, db, allocation, ceo, pool):
        """Should update balance via trigger when spend transaction inserted."""
        balance = create_budget_balance(
            db, allocation.id, ceo.id, 500000.0, pool.period_start, pool.period_end
        )

        # Create spend transaction - trigger should update balance
        create_budget_transaction(
            db, allocation.id, ceo.id, "spend", -1000.0
        )

        updated_balance = get_budget_balance(db, allocation.id)
        assert updated_balance.spent == 1000.0
        assert updated_balance.available == 499000.0

    def test_balance_trigger_on_reserve_release(self, db, allocation, ceo, pool):
        """Should update balance via trigger for reserve/release."""
        create_budget_balance(
            db, allocation.id, ceo.id, 500000.0, pool.period_start, pool.period_end
        )

        # Reserve credits
        create_budget_transaction(
            db, allocation.id, ceo.id, "reserve", 2000.0
        )

        balance = get_budget_balance(db, allocation.id)
        assert balance.reserved == 2000.0
        assert balance.available == 498000.0

        # Release credits
        create_budget_transaction(
            db, allocation.id, ceo.id, "release", -2000.0
        )

        balance = get_budget_balance(db, allocation.id)
        assert balance.reserved == 0.0
        assert balance.available == 500000.0

    def test_balance_trigger_on_transfer_out(self, db, allocation, ceo, pool):
        """Should update balance via trigger for delegation."""
        create_budget_balance(
            db, allocation.id, ceo.id, 500000.0, pool.period_start, pool.period_end
        )

        # Transfer out (delegation)
        create_budget_transaction(
            db, allocation.id, ceo.id, "transfer_out", 100000.0
        )

        balance = get_budget_balance(db, allocation.id)
        assert balance.delegated == 100000.0
        assert balance.available == 400000.0


class TestBudgetHelperQueries:
    """Test budget helper queries."""

    def test_get_pool_allocated_total(self, db, pool, ceo, manager):
        """Should sum total allocated from pool."""
        create_budget_allocation(
            db, ceo.id, 500000.0, pool.period_start, pool.period_end, pool_id=pool.id
        )
        create_budget_allocation(
            db, manager.id, 100000.0, pool.period_start, pool.period_end, pool_id=pool.id
        )

        total = get_pool_allocated_total(db, pool.id)
        assert total == 600000.0

    def test_get_pool_allocated_total_empty(self, db, pool):
        """Should return 0 for pool with no allocations."""
        total = get_pool_allocated_total(db, pool.id)
        assert total == 0.0

    def test_is_worker_manager_true(self, db, team, ceo, manager):
        """Should return True for worker with direct reports."""
        assert is_worker_manager(db, ceo.id) is True

    def test_is_worker_manager_false(self, db, team, developer):
        """Should return False for worker without direct reports."""
        assert is_worker_manager(db, developer.id) is False


class TestBudgetAllocationConstraints:
    """Test budget allocation constraints."""

    def test_allocation_requires_source_or_pool(self, db, period, ceo):
        """Should enforce that either pool_id or source_worker_id is set."""
        # This should fail due to CHECK constraint - both are None
        # The constraint: (source_worker_id IS NULL AND pool_id IS NOT NULL) OR
        #                 (source_worker_id IS NOT NULL AND pool_id IS NULL)
        with pytest.raises(Exception):  # IntegrityError from SQLite
            db.execute(
                """INSERT INTO budget_allocations
                   (id, worker_id, allocated_credits, period_start, period_end)
                   VALUES (?, ?, ?, ?, ?)""",
                ("test-alloc", ceo.id, 10000.0, period["start"], period["end"])
            )
            db.connection.commit()

    def test_allocation_cannot_have_both_source_and_pool(self, db, pool, period, ceo, manager):
        """Should enforce mutual exclusivity of pool_id and source_worker_id."""
        with pytest.raises(Exception):  # IntegrityError from SQLite
            db.execute(
                """INSERT INTO budget_allocations
                   (id, worker_id, source_worker_id, pool_id, allocated_credits,
                    period_start, period_end)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                ("test-alloc", manager.id, ceo.id, pool.id, 10000.0,
                 period["start"], period["end"])
            )
            db.connection.commit()


# ============================================================================
# Budget Enforcement Tests
# ============================================================================


class TestBudgetEnforcementFunctions:
    """Test budget enforcement functions from budget.py."""

    @pytest.fixture
    def allocation_with_balance(self, db, pool, developer):
        """Create allocation with balance for testing."""
        allocation = create_budget_allocation(
            db,
            worker_id=developer.id,
            allocated_credits=1000.0,  # $1000 budget
            period_start=pool.period_start,
            period_end=pool.period_end,
            pool_id=pool.id,
        )
        from cli.core.queries import create_budget_balance
        create_budget_balance(
            db,
            allocation_id=allocation.id,
            worker_id=developer.id,
            allocated=1000.0,
            period_start=pool.period_start,
            period_end=pool.period_end,
        )
        return allocation

    def test_estimate_cost_budget_tier(self):
        """Should estimate cost for budget tier models."""
        from cli.core.budget import estimate_cost

        # Budget tier: ~$0.00025/1K input, ~$0.00125/1K output
        cost = estimate_cost("budget", input_tokens=1000, output_tokens=1000)

        # Should be around $0.00025 + $0.00125 = $0.0015
        assert cost == pytest.approx(0.0015, rel=0.01)

    def test_estimate_cost_standard_tier(self):
        """Should estimate cost for standard tier models."""
        from cli.core.budget import estimate_cost

        # Standard tier: ~$0.003/1K input, ~$0.015/1K output
        cost = estimate_cost("standard", input_tokens=1000, output_tokens=1000)

        # Should be around $0.003 + $0.015 = $0.018
        assert cost == pytest.approx(0.018, rel=0.01)

    def test_estimate_cost_premium_tier(self):
        """Should estimate cost for premium tier models."""
        from cli.core.budget import estimate_cost

        # Premium tier: ~$0.015/1K input, ~$0.075/1K output
        cost = estimate_cost("premium", input_tokens=1000, output_tokens=1000)

        # Should be around $0.015 + $0.075 = $0.09
        assert cost == pytest.approx(0.09, rel=0.01)

    def test_estimate_cost_with_budget_config(self):
        """Should use BudgetConfig when provided."""
        from cli.core.budget import estimate_cost
        from cli.core.config import BudgetConfig, TierTokenCosts

        # Create custom config with different rates
        config = BudgetConfig(
            tier_costs={
                "budget": TierTokenCosts(input=0.001, output=0.002),
            }
        )

        # With config: $0.001/1K input + $0.002/1K output = $0.003
        cost = estimate_cost(
            "budget",
            input_tokens=1000,
            output_tokens=1000,
            budget_config=config,
        )
        assert cost == pytest.approx(0.003, rel=0.01)

        # Without config: uses default ($0.00025 + $0.00125 = $0.0015)
        cost_default = estimate_cost(
            "budget",
            input_tokens=1000,
            output_tokens=1000,
        )
        assert cost_default == pytest.approx(0.0015, rel=0.01)

    def test_check_budget_sufficient(self, db, allocation_with_balance, developer):
        """Should approve when budget is sufficient."""
        from cli.core.budget import check_budget

        result = check_budget(db, developer.id, required_amount=100.0)

        assert result.allowed is True
        assert result.worker_id == developer.id
        assert result.available == 1000.0
        assert result.required == 100.0
        assert result.remaining_after == 900.0
        assert "approved" in result.message.lower()

    def test_check_budget_insufficient(self, db, allocation_with_balance, developer):
        """Should reject when budget is insufficient."""
        from cli.core.budget import check_budget

        result = check_budget(db, developer.id, required_amount=1500.0)

        assert result.allowed is False
        assert result.available == 1000.0
        assert result.required == 1500.0
        assert result.remaining_after == 0.0
        assert "insufficient" in result.message.lower()

    def test_check_budget_no_allocation(self, db, team):
        """Should raise when worker has no allocation."""
        from cli.core.budget import check_budget, NoBudgetAllocationError

        worker = create_worker(db, "No Budget Worker", "Dev", team.id, 50)

        with pytest.raises(NoBudgetAllocationError) as exc_info:
            check_budget(db, worker.id, required_amount=1.0)

        assert worker.id in str(exc_info.value)
        assert "no budget allocation" in str(exc_info.value).lower()

    def test_enforce_budget_sufficient(self, db, allocation_with_balance, developer):
        """Should return result when budget is sufficient."""
        from cli.core.budget import enforce_budget

        result = enforce_budget(db, developer.id, required_amount=100.0)

        assert result.allowed is True

    def test_enforce_budget_insufficient_raises(self, db, allocation_with_balance, developer):
        """Should raise BudgetExhaustedError when insufficient."""
        from cli.core.budget import enforce_budget, BudgetExhaustedError

        with pytest.raises(BudgetExhaustedError) as exc_info:
            enforce_budget(db, developer.id, required_amount=1500.0)

        assert exc_info.value.worker_id == developer.id
        assert exc_info.value.required == 1500.0
        assert exc_info.value.available == 1000.0

    def test_record_spend(self, db, allocation_with_balance, developer):
        """Should record spend transaction."""
        from cli.core.budget import record_spend

        txn = record_spend(
            db=db,
            worker_id=developer.id,
            allocation_id=allocation_with_balance.id,
            amount=5.0,
            provider="anthropic",
            model="claude-3-5-sonnet",
            input_tokens=1000,
            output_tokens=500,
            reference_type="task",
            reference_id="task-123",
        )

        assert txn.amount == -5.0  # Negative for spend
        assert txn.provider == "anthropic"
        assert txn.model == "claude-3-5-sonnet"
        assert txn.input_tokens == 1000
        assert txn.output_tokens == 500

    def test_get_remaining_budget(self, db, allocation_with_balance, developer):
        """Should return remaining budget."""
        from cli.core.budget import get_remaining_budget

        remaining = get_remaining_budget(db, developer.id)
        assert remaining == 1000.0

    def test_get_remaining_budget_no_allocation(self, db, team):
        """Should return 0 for worker without allocation."""
        from cli.core.budget import get_remaining_budget

        worker = create_worker(db, "No Budget Worker", "Dev", team.id, 50)
        remaining = get_remaining_budget(db, worker.id)

        assert remaining == 0.0


class TestBudgetEnforcer:
    """Test BudgetEnforcer context manager."""

    @pytest.fixture
    def allocation_with_balance(self, db, pool, developer):
        """Create allocation with balance for testing."""
        allocation = create_budget_allocation(
            db,
            worker_id=developer.id,
            allocated_credits=1000.0,
            period_start=pool.period_start,
            period_end=pool.period_end,
            pool_id=pool.id,
        )
        from cli.core.queries import create_budget_balance
        create_budget_balance(
            db,
            allocation_id=allocation.id,
            worker_id=developer.id,
            allocated=1000.0,
            period_start=pool.period_start,
            period_end=pool.period_end,
        )
        return allocation

    def test_enforcer_context_manager_allows_when_sufficient(
        self, db, allocation_with_balance, developer
    ):
        """Should allow operation when budget is sufficient."""
        from cli.core.budget import BudgetEnforcer

        with BudgetEnforcer(db, developer.id, estimated_cost=10.0) as enforcer:
            # Simulate successful provider call
            enforcer.record(
                actual_cost=10.0,
                provider="anthropic",
                model="claude-3-5-sonnet",
                input_tokens=1000,
                output_tokens=500,
            )

        # Should have recorded transaction
        txns = get_transactions_by_worker(db, developer.id)
        assert len(txns) == 1
        assert txns[0].amount == -10.0

    def test_enforcer_raises_when_insufficient(
        self, db, allocation_with_balance, developer
    ):
        """Should raise before entering context when budget insufficient."""
        from cli.core.budget import BudgetEnforcer, BudgetExhaustedError

        with pytest.raises(BudgetExhaustedError):
            with BudgetEnforcer(db, developer.id, estimated_cost=2000.0):
                pass  # Should not reach here

    def test_enforcer_allocation_id_property(
        self, db, allocation_with_balance, developer
    ):
        """Should expose allocation_id from check result."""
        from cli.core.budget import BudgetEnforcer

        with BudgetEnforcer(db, developer.id, estimated_cost=10.0) as enforcer:
            assert enforcer.allocation_id == allocation_with_balance.id
            enforcer.record(
                actual_cost=10.0,
                provider="anthropic",
                model="claude-3-5-sonnet",
                input_tokens=1000,
                output_tokens=500,
            )

    def test_enforcer_warns_if_not_recorded(
        self, db, allocation_with_balance, developer
    ):
        """Should warn if context exits without recording spend."""
        from cli.core.budget import BudgetEnforcer
        import warnings

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            with BudgetEnforcer(db, developer.id, estimated_cost=10.0):
                pass  # Don't call record()

            # Should have emitted warning
            assert len(w) == 1
            assert "without recording spend" in str(w[0].message)

    def test_enforcer_no_warning_on_exception(
        self, db, allocation_with_balance, developer
    ):
        """Should not warn if context exits due to exception."""
        from cli.core.budget import BudgetEnforcer
        import warnings

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            with pytest.raises(ValueError):
                with BudgetEnforcer(db, developer.id, estimated_cost=10.0):
                    raise ValueError("Simulated failure")

            # Should NOT have emitted warning (exception occurred)
            assert len(w) == 0

    def test_enforcer_with_reference(self, db, allocation_with_balance, developer):
        """Should record reference type and ID."""
        from cli.core.budget import BudgetEnforcer

        with BudgetEnforcer(db, developer.id, estimated_cost=10.0) as enforcer:
            enforcer.record(
                actual_cost=10.0,
                provider="anthropic",
                model="claude-3-5-sonnet",
                input_tokens=1000,
                output_tokens=500,
                reference_type="task",
                reference_id="task-abc-123",
                description="Processing customer request",
            )

        txns = get_transactions_by_worker(db, developer.id)
        assert txns[0].reference_type == "task"
        assert txns[0].reference_id == "task-abc-123"


class TestBudgetServiceDelegation:
    """Test BudgetService.delegate_budget validation."""

    @pytest.fixture
    def ceo_with_allocation(self, db, pool, ceo):
        """Create CEO with budget allocation and balance."""
        allocation = create_budget_allocation(
            db,
            worker_id=ceo.id,
            allocated_credits=100000.0,
            period_start=pool.period_start,
            period_end=pool.period_end,
            pool_id=pool.id,
            can_delegate=True,
            delegation_limit=50000.0,
        )
        create_budget_balance(
            db,
            allocation_id=allocation.id,
            worker_id=ceo.id,
            allocated=100000.0,
            period_start=pool.period_start,
            period_end=pool.period_end,
        )
        return allocation

    @pytest.fixture
    def manager_allocation(self, db, pool, ceo, manager):
        """Create manager allocation with can_delegate=True."""
        allocation = create_budget_allocation(
            db,
            worker_id=manager.id,
            allocated_credits=50000.0,
            period_start=pool.period_start,
            period_end=pool.period_end,
            source_worker_id=ceo.id,
            can_delegate=True,
            delegation_limit=10000.0,
        )
        create_budget_balance(
            db,
            allocation_id=allocation.id,
            worker_id=manager.id,
            allocated=50000.0,
            period_start=pool.period_start,
            period_end=pool.period_end,
        )
        return allocation

    def test_delegate_budget_success(self, db, pool, ceo_with_allocation, manager):
        """Should successfully delegate budget to subordinate."""
        from cli.core.budget import BudgetService

        service = BudgetService(db)
        allocation_id = service.delegate_budget(
            source_worker_id=ceo_with_allocation.worker_id,
            target_worker_id=manager.id,
            amount=10000.0,
        )

        assert allocation_id is not None
        # Target should have allocation
        target_balance = service.get_balance(manager.id)
        assert target_balance is not None
        assert target_balance.allocated == 10000.0

    def test_delegate_budget_negative_amount(self, db, ceo_with_allocation, manager):
        """Should reject negative delegation amount."""
        from cli.core.budget import BudgetService, BudgetAllocationError

        service = BudgetService(db)
        with pytest.raises(BudgetAllocationError) as exc_info:
            service.delegate_budget(
                source_worker_id=ceo_with_allocation.worker_id,
                target_worker_id=manager.id,
                amount=-100.0,
            )
        assert "must be positive" in str(exc_info.value)

    def test_delegate_budget_zero_amount(self, db, ceo_with_allocation, manager):
        """Should reject zero delegation amount."""
        from cli.core.budget import BudgetService, BudgetAllocationError

        service = BudgetService(db)
        with pytest.raises(BudgetAllocationError) as exc_info:
            service.delegate_budget(
                source_worker_id=ceo_with_allocation.worker_id,
                target_worker_id=manager.id,
                amount=0.0,
            )
        assert "must be positive" in str(exc_info.value)

    def test_delegate_budget_source_cannot_delegate(self, db, pool, ceo, manager, developer):
        """Should reject when source has can_delegate=False."""
        from cli.core.budget import BudgetService, BudgetAllocationError

        # Create allocation WITHOUT delegation permission
        allocation = create_budget_allocation(
            db,
            worker_id=manager.id,
            allocated_credits=50000.0,
            period_start=pool.period_start,
            period_end=pool.period_end,
            source_worker_id=ceo.id,
            can_delegate=False,  # Cannot delegate
        )
        create_budget_balance(
            db,
            allocation_id=allocation.id,
            worker_id=manager.id,
            allocated=50000.0,
            period_start=pool.period_start,
            period_end=pool.period_end,
        )

        service = BudgetService(db)
        with pytest.raises(BudgetAllocationError) as exc_info:
            service.delegate_budget(
                source_worker_id=manager.id,
                target_worker_id=developer.id,
                amount=1000.0,
            )
        assert "cannot delegate" in str(exc_info.value).lower()

    def test_delegate_budget_not_manager_of_target(self, db, pool, team, ceo_with_allocation, manager):
        """Should reject when source is not target's manager."""
        from cli.core.budget import BudgetService, BudgetAllocationError

        # Create another worker NOT under CEO
        other_worker = create_worker(db, "Other Worker", "Dev", team.id, 50, manager_id=manager.id)

        service = BudgetService(db)
        with pytest.raises(BudgetAllocationError) as exc_info:
            service.delegate_budget(
                source_worker_id=ceo_with_allocation.worker_id,
                target_worker_id=other_worker.id,  # Reports to manager, not CEO
                amount=1000.0,
            )
        assert "does not report to" in str(exc_info.value)

    def test_delegate_budget_exceeds_available_balance(self, db, pool, team, manager):
        """Should reject when amount exceeds available balance."""
        from cli.core.budget import BudgetService, BudgetAllocationError

        # Create CEO with no delegation limit but limited balance
        ceo = create_worker(db, "Test CEO", "CEO", team.id, 90)
        allocation = create_budget_allocation(
            db,
            worker_id=ceo.id,
            allocated_credits=10000.0,  # Only 10000 available
            period_start=pool.period_start,
            period_end=pool.period_end,
            pool_id=pool.id,
            can_delegate=True,
            delegation_limit=None,  # No delegation limit
        )
        create_budget_balance(
            db,
            allocation_id=allocation.id,
            worker_id=ceo.id,
            allocated=10000.0,
            period_start=pool.period_start,
            period_end=pool.period_end,
        )
        # Update manager to report to this CEO
        db.execute("UPDATE workers SET manager_id = ? WHERE id = ?", (ceo.id, manager.id))
        db.connection.commit()

        service = BudgetService(db)
        with pytest.raises(BudgetAllocationError) as exc_info:
            service.delegate_budget(
                source_worker_id=ceo.id,
                target_worker_id=manager.id,
                amount=50000.0,  # More than 10000 available
            )
        assert "insufficient" in str(exc_info.value).lower()

    def test_delegate_budget_exceeds_delegation_limit(self, db, ceo_with_allocation, manager):
        """Should reject when amount exceeds delegation limit."""
        from cli.core.budget import BudgetService, BudgetAllocationError

        service = BudgetService(db)
        with pytest.raises(BudgetAllocationError) as exc_info:
            service.delegate_budget(
                source_worker_id=ceo_with_allocation.worker_id,
                target_worker_id=manager.id,
                amount=60000.0,  # delegation_limit is 50000
            )
        assert "delegation limit" in str(exc_info.value).lower()

    def test_delegate_budget_target_not_found(self, db, ceo_with_allocation):
        """Should reject when target worker doesn't exist."""
        from cli.core.budget import BudgetService, BudgetAllocationError

        service = BudgetService(db)
        with pytest.raises(BudgetAllocationError) as exc_info:
            service.delegate_budget(
                source_worker_id=ceo_with_allocation.worker_id,
                target_worker_id="nonexistent-worker",
                amount=1000.0,
            )
        assert "not found" in str(exc_info.value).lower()

    def test_delegate_budget_source_no_allocation(self, db, team, ceo, manager):
        """Should reject when source has no budget allocation."""
        from cli.core.budget import BudgetService, BudgetAllocationError

        service = BudgetService(db)
        with pytest.raises(BudgetAllocationError) as exc_info:
            service.delegate_budget(
                source_worker_id=ceo.id,  # No allocation created
                target_worker_id=manager.id,
                amount=1000.0,
            )
        assert "no budget allocation" in str(exc_info.value).lower()


class TestBudgetAmountValidation:
    """Test validation of negative amounts in budget operations."""

    def test_create_budget_pool_negative_credits(self, db, period):
        """Should reject negative total_credits in create_budget_pool."""
        with pytest.raises(ValueError) as exc_info:
            create_budget_pool(
                db,
                name="Invalid Pool",
                total_credits=-1000.0,
                period_start=period["start"],
                period_end=period["end"],
            )
        assert "must be positive" in str(exc_info.value)

    def test_create_budget_pool_zero_credits(self, db, period):
        """Should reject zero total_credits in create_budget_pool."""
        with pytest.raises(ValueError) as exc_info:
            create_budget_pool(
                db,
                name="Invalid Pool",
                total_credits=0.0,
                period_start=period["start"],
                period_end=period["end"],
            )
        assert "must be positive" in str(exc_info.value)

    def test_create_budget_allocation_negative_credits(self, db, pool, ceo):
        """Should reject negative allocated_credits in create_budget_allocation."""
        with pytest.raises(ValueError) as exc_info:
            create_budget_allocation(
                db,
                worker_id=ceo.id,
                allocated_credits=-5000.0,
                period_start=pool.period_start,
                period_end=pool.period_end,
                pool_id=pool.id,
            )
        assert "must be positive" in str(exc_info.value)

    def test_create_budget_allocation_zero_credits(self, db, pool, ceo):
        """Should reject zero allocated_credits in create_budget_allocation."""
        with pytest.raises(ValueError) as exc_info:
            create_budget_allocation(
                db,
                worker_id=ceo.id,
                allocated_credits=0.0,
                period_start=pool.period_start,
                period_end=pool.period_end,
                pool_id=pool.id,
            )
        assert "must be positive" in str(exc_info.value)

    def test_create_budget_allocation_negative_delegation_limit(self, db, pool, ceo):
        """Should reject negative delegation_limit in create_budget_allocation."""
        with pytest.raises(ValueError) as exc_info:
            create_budget_allocation(
                db,
                worker_id=ceo.id,
                allocated_credits=10000.0,
                period_start=pool.period_start,
                period_end=pool.period_end,
                pool_id=pool.id,
                can_delegate=True,
                delegation_limit=-1000.0,
            )
        assert "must be positive" in str(exc_info.value)

    def test_record_spend_negative_amount(self, db, pool, developer):
        """Should reject negative amount in record_spend."""
        from cli.core.budget import record_spend

        allocation = create_budget_allocation(
            db,
            worker_id=developer.id,
            allocated_credits=1000.0,
            period_start=pool.period_start,
            period_end=pool.period_end,
            pool_id=pool.id,
        )
        create_budget_balance(
            db,
            allocation_id=allocation.id,
            worker_id=developer.id,
            allocated=1000.0,
            period_start=pool.period_start,
            period_end=pool.period_end,
        )

        with pytest.raises(ValueError) as exc_info:
            record_spend(
                db=db,
                worker_id=developer.id,
                allocation_id=allocation.id,
                amount=-50.0,
                provider="anthropic",
                model="claude-3-5-sonnet",
                input_tokens=1000,
                output_tokens=500,
            )
        assert "must be positive" in str(exc_info.value)

    def test_record_spend_zero_amount(self, db, pool, developer):
        """Should reject zero amount in record_spend."""
        from cli.core.budget import record_spend

        allocation = create_budget_allocation(
            db,
            worker_id=developer.id,
            allocated_credits=1000.0,
            period_start=pool.period_start,
            period_end=pool.period_end,
            pool_id=pool.id,
        )
        create_budget_balance(
            db,
            allocation_id=allocation.id,
            worker_id=developer.id,
            allocated=1000.0,
            period_start=pool.period_start,
            period_end=pool.period_end,
        )

        with pytest.raises(ValueError) as exc_info:
            record_spend(
                db=db,
                worker_id=developer.id,
                allocation_id=allocation.id,
                amount=0.0,
                provider="anthropic",
                model="claude-3-5-sonnet",
                input_tokens=1000,
                output_tokens=500,
            )
        assert "must be positive" in str(exc_info.value)

    def test_allocate_from_pool_negative_amount(self, db, pool, ceo, period):
        """Should reject negative amount in allocate_from_pool."""
        from cli.core.budget import BudgetService, BudgetAllocationError

        service = BudgetService(db)
        with pytest.raises(BudgetAllocationError) as exc_info:
            service.allocate_from_pool(
                pool_id=pool.id,
                worker_id=ceo.id,
                amount=-1000.0,
                period_start=period["start"],
                period_end=period["end"],
            )
        assert "must be positive" in str(exc_info.value)

    def test_allocate_from_pool_zero_amount(self, db, pool, ceo, period):
        """Should reject zero amount in allocate_from_pool."""
        from cli.core.budget import BudgetService, BudgetAllocationError

        service = BudgetService(db)
        with pytest.raises(BudgetAllocationError) as exc_info:
            service.allocate_from_pool(
                pool_id=pool.id,
                worker_id=ceo.id,
                amount=0.0,
                period_start=period["start"],
                period_end=period["end"],
            )
        assert "must be positive" in str(exc_info.value)
