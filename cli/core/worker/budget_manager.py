"""
Worker budget management.

Handles budget enforcement and spend recording for worker operations.
"""

from typing import TYPE_CHECKING

from ..budget import (
    enforce_budget,
    record_spend,
    estimate_cost,
    BudgetCheckResult,
)
from ..constants import (
    DEFAULT_SESSION_SPAWN_TOKENS_INPUT,
    DEFAULT_SESSION_SPAWN_TOKENS_OUTPUT,
    COST_TIER_BUDGET_MAX,
    COST_TIER_STANDARD_MAX,
    COST_TIER_ADVANCED_MAX,
)

if TYPE_CHECKING:
    from ..db import Database
    from ..session import SessionInterface


class WorkerBudgetManager:
    """Manages budget operations for a worker.

    Handles:
    - Budget allocation checking
    - Cost estimation
    - Spend recording
    - Cost tier calculation
    """

    def __init__(self, worker: "WorkerBase"):
        """Initialize budget manager.

        Args:
            worker: Parent Worker instance
        """
        self.worker = worker

    def get_cost_tier(self) -> str:
        """Get worker's cost tier based on cost score.

        Returns:
            Cost tier: 'budget', 'standard', 'advanced', or 'premium'
        """
        cost_score = self.worker.cost
        if cost_score <= COST_TIER_BUDGET_MAX:
            return "budget"
        elif cost_score <= COST_TIER_STANDARD_MAX:
            return "standard"
        elif cost_score <= COST_TIER_ADVANCED_MAX:
            return "advanced"
        else:
            return "premium"

    def estimate_spawn_cost(self) -> float:
        """Estimate the cost of spawning a session for this worker.

        Returns:
            Estimated cost in dollars
        """
        return estimate_cost(
            model_tier=self.get_cost_tier(),
            input_tokens=DEFAULT_SESSION_SPAWN_TOKENS_INPUT,
            output_tokens=DEFAULT_SESSION_SPAWN_TOKENS_OUTPUT,
        )

    def enforce_spawn_budget(self, session: "SessionInterface") -> BudgetCheckResult:
        """Estimate cost and enforce budget constraints for session spawn.

        Calculates the estimated cost of spawning this session based on
        the worker's cost tier, then verifies sufficient budget is available.

        Args:
            session: The session to be spawned (used for type consistency)

        Returns:
            BudgetCheckResult with allocation details for recording spend

        Raises:
            BudgetExhaustedError: If worker has insufficient budget
            NoBudgetAllocationError: If worker has no budget allocation
        """
        estimated_cost = self.estimate_spawn_cost()

        # Check budget before spawning - raises if insufficient
        budget_check = enforce_budget(
            db=self.worker.db,
            worker_id=self.worker.id,
            required_amount=estimated_cost,
        )

        return budget_check

    def record_spawn_spend(
        self,
        session: "SessionInterface",
        allocation_id: str,
    ) -> None:
        """Record spend after successful session spawn.

        Args:
            session: The spawned session
            allocation_id: Budget allocation ID to charge against
        """
        estimated_cost = self.estimate_spawn_cost()

        record_spend(
            db=self.worker.db,
            worker_id=self.worker.id,
            allocation_id=allocation_id,
            amount=estimated_cost,
            provider=session.provider_name,
            model=f"{self.get_cost_tier()}-tier",
            input_tokens=DEFAULT_SESSION_SPAWN_TOKENS_INPUT,
            output_tokens=DEFAULT_SESSION_SPAWN_TOKENS_OUTPUT,
            reference_type="session",
            reference_id=str(session.id),
            description=f"Session spawn for worker {self.worker.name}",
        )
