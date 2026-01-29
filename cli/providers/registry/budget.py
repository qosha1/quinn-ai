"""
Budget enforcement and session creation for providers.

This module integrates provider selection with budget tracking
and session creation.
"""

import os
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cli.core.session import SessionInterface
    from cli.providers.registry.registry import ProviderRegistry


def create_session_for_worker(
    registry: "ProviderRegistry",
    worker_id: str,
    worker_cost: int,
    worker_skills: dict[str, int],
    working_directory: Optional[Path] = None,
    preferred_provider: Optional[str] = None,
    org_authorized_providers: Optional[list[str]] = None,
) -> "SessionInterface":
    """Create an appropriate session for a worker based on their profile.

    Uses provider selection to determine the right provider and model,
    then uses the SessionRegistry to create the appropriate session type.

    Args:
        registry: Initialized ProviderRegistry
        worker_id: Worker ID for session binding
        worker_cost: Worker cost score (0-100)
        worker_skills: Worker skills dict
        working_directory: Working directory for session
        preferred_provider: Optional provider preference
        org_authorized_providers: List of authorized provider names (None = all)

    Returns:
        Configured SessionInterface instance (not yet started)

    Raises:
        ProviderSelectionError: If no provider can satisfy requirements
        AdapterNotFoundError: If no session adapter for the provider
    """
    # Import here to avoid circular imports
    from cli.core.session import SessionConfig
    from cli.core.sessions.registry import get_default_registry
    from cli.providers.registry.selection import select_provider_for_worker

    # Select provider
    selection = select_provider_for_worker(
        registry=registry,
        worker_cost=worker_cost,
        worker_skills=worker_skills,
        preferred_provider=preferred_provider,
        org_authorized_providers=org_authorized_providers,
    )

    # Get CLI command from provider (no string dispatch)
    command = selection.provider.cli_command

    # Build session config
    config = SessionConfig(
        worker_id=worker_id,
        provider=selection.provider.name,
        command=command,
        args=["--dangerously-skip-permissions"],
        working_directory=working_directory,
        env_vars={
            "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY", ""),
        },
    )

    # Use SessionRegistry to create appropriate session type (no hardcoding)
    session_registry = get_default_registry()
    return session_registry.create(selection.provider.name, config)


def complete_with_budget(
    registry: "ProviderRegistry",
    db: "Database",
    worker_id: str,
    worker_cost: int,
    worker_skills: dict[str, int],
    messages: list[dict],
    max_tokens: int = 4096,
    preferred_provider: Optional[str] = None,
    reference_type: Optional[str] = None,
    reference_id: Optional[str] = None,
) -> dict:
    """Execute a completion request with budget enforcement.

    This is the main entry point for budget-controlled LLM calls.
    It:
    1. Selects the appropriate provider/model for the worker
    2. Estimates the cost and checks budget
    3. Makes the API call
    4. Records actual spend

    Args:
        registry: Initialized ProviderRegistry
        db: Database instance for budget operations
        worker_id: Worker making the request
        worker_cost: Worker cost score (0-100)
        worker_skills: Worker skills dict
        messages: List of message dicts for the completion
        max_tokens: Maximum output tokens
        preferred_provider: Optional provider preference
        reference_type: Optional reference type for transaction (e.g., 'task', 'message')
        reference_id: Optional reference ID for transaction

    Returns:
        Dict with completion result including:
        - content: The completion text
        - model: Model used
        - input_tokens: Actual input tokens
        - output_tokens: Actual output tokens
        - cost: Actual cost in credits
        - budget_remaining: Remaining budget after this call

    Raises:
        BudgetExhaustedError: If insufficient budget
        NoBudgetAllocationError: If no budget allocation exists
        ProviderSelectionError: If no provider can satisfy requirements
        AuthenticationError: If provider authentication fails
        RateLimitError: If provider rate limit is exceeded
        ProviderTimeoutError: If provider request times out
        ProviderConnectionError: If connection to provider fails
        ProviderError: For other provider errors (wraps unexpected exceptions)
    """
    # Import here to avoid circular imports
    from cli.core.budget import (
        BudgetEnforcer,
        estimate_cost,
        get_remaining_budget,
    )
    from cli.core.db import Database
    from cli.providers.base import (
        AuthenticationError,
        RateLimitError,
        ProviderTimeoutError,
        ProviderConnectionError,
        ProviderError,
    )
    from cli.providers.registry.selection import select_provider_for_worker

    # Step 1: Select provider and model
    selection = select_provider_for_worker(
        registry=registry,
        worker_cost=worker_cost,
        worker_skills=worker_skills,
        preferred_provider=preferred_provider,
    )

    # Step 2: Estimate input tokens (rough approximation)
    # Count characters and estimate ~4 chars per token
    total_chars = sum(len(str(m.get("content", ""))) for m in messages)
    estimated_input_tokens = total_chars // 4

    # Step 3: Estimate cost
    model_tier = selection.tier.value  # budget, standard, advanced, premium
    estimated_cost = estimate_cost(
        model_tier=model_tier,
        input_tokens=estimated_input_tokens,
        output_tokens=max_tokens,
    )

    # Step 4: Enforce budget and make completion
    with BudgetEnforcer(db, worker_id, estimated_cost) as enforcer:
        # Make the actual provider call with proper exception handling
        try:
            result = selection.provider.complete(
                messages=messages,
                model=selection.model.id,
                max_tokens=max_tokens,
            )
        except AuthenticationError:
            # Re-raise auth errors as-is - caller should handle credential issues
            raise
        except RateLimitError:
            # Re-raise rate limit errors - caller can implement retry logic
            raise
        except ProviderTimeoutError:
            # Re-raise timeout errors - caller can retry with longer timeout
            raise
        except ProviderConnectionError:
            # Re-raise connection errors - caller can retry after delay
            raise
        except ProviderError:
            # Re-raise other provider errors (APIError, ModelNotAvailableError, etc.)
            raise
        except Exception as e:
            # Wrap unexpected exceptions in ProviderError for consistent handling
            # This prevents raw exceptions from leaking through and ensures
            # the caller always gets a domain-specific exception
            raise ProviderError(
                message=f"Unexpected error during completion: {e}",
                provider=selection.provider.name,
                cause=e,
            ) from e

        # Get actual token counts from result
        actual_input = result.get("usage", {}).get("input_tokens", estimated_input_tokens)
        actual_output = result.get("usage", {}).get("output_tokens", 0)

        # Calculate actual cost
        actual_cost = estimate_cost(
            model_tier=model_tier,
            input_tokens=actual_input,
            output_tokens=actual_output,
        )

        # Record the spend
        enforcer.record(
            actual_cost=actual_cost,
            provider=selection.provider.name,
            model=selection.model.id,
            input_tokens=actual_input,
            output_tokens=actual_output,
            reference_type=reference_type,
            reference_id=reference_id,
            description=f"Completion via {selection.provider.name}/{selection.model.id}",
        )

    # Return enhanced result
    return {
        "content": result.get("content", ""),
        "model": selection.model.id,
        "provider": selection.provider.name,
        "input_tokens": actual_input,
        "output_tokens": actual_output,
        "cost": actual_cost,
        "budget_remaining": get_remaining_budget(db, worker_id),
    }
