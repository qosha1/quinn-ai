"""Data classes used by the org-stop sequence.

Extracted from cli/core/stop_controller.py so the orchestrator file can
focus on flow logic. Re-exported from stop_controller for backward
compatibility — existing
`from cli.core.stop_controller import OrgStopResult` style imports
keep working.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class WorkerStopState:
    """Tracks stop state for a single worker."""

    worker_id: str
    worker_name: str
    role: str
    timeout_seconds: int
    wrapup_sent_at: Optional[datetime] = None
    ack_received_at: Optional[datetime] = None
    ack_message: Optional[str] = None
    session_stopped: bool = False
    state_saved: bool = False
    error: Optional[str] = None


@dataclass
class StopPhaseResult:
    """Result of a single stop phase."""

    phase: int
    name: str
    success: bool
    duration_seconds: float
    message: str
    details: dict = field(default_factory=dict)


@dataclass
class OrgStopResult:
    """Complete result of an org stop operation."""

    success: bool
    phases: list[StopPhaseResult] = field(default_factory=list)
    workers_stopped: int = 0
    workers_acked: int = 0
    # Names of workers that didn't acknowledge the graceful-stop signal
    # before the timeout expired. Empty on a clean stop. Populated from
    # phase 3 details so the CLI summary can surface it as a warning.
    unacked_workers: list[str] = field(default_factory=list)
    sessions_terminated: int = 0
    states_saved: int = 0
    errors: list[str] = field(default_factory=list)
    total_duration_seconds: float = 0.0
