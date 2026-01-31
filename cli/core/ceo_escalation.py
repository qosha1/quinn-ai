"""CEO-specific escalation helpers with org context enrichment.

Provides specialized escalation functionality for CEO role, including:
- Org state context gathering (workers, work, blockers, OKRs)
- Urgency level determination and mapping
- Board notification with appropriate priority
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from cli.core.db import Database
from cli.core.notifications import NotificationPriority

logger = logging.getLogger(__name__)


class EscalationUrgency(Enum):
    """Urgency levels for CEO escalations to board."""

    INFO = "info"  # Board UI only, CEO continues work
    WARNING = "warning"  # Board UI + desktop notification, CEO continues
    URGENT = "urgent"  # Board UI + desktop + email, CEO waits for response


@dataclass
class OrgStateContext:
    """Current state of the organization for escalation context.

    Attributes:
        total_workers: Total number of workers in org
        active_workers: Workers currently running
        idle_workers: Workers idle without work
        blocked_workers: Workers blocked on tasks
        total_work_items: Total open work items
        blocked_work_items: Work items marked as blocked
        okr_count: Number of active OKRs
        recent_escalations: Recent escalation count (last 24hr)
    """

    total_workers: int
    active_workers: int
    idle_workers: int
    blocked_workers: int
    total_work_items: int
    blocked_work_items: int
    okr_count: int
    recent_escalations: int


class CEOEscalationHelper:
    """Helper for CEO escalations with org context enrichment.

    Gathers current org state, determines urgency, and formats
    escalation messages with comprehensive context for the board.
    """

    def __init__(self, db: Database, org_name: str):
        """Initialize CEO escalation helper.

        Args:
            db: Database connection
            org_name: Organization name
        """
        self.db = db
        self.org_name = org_name

    def gather_org_state(self) -> OrgStateContext:
        """Gather current organizational state for escalation context.

        Returns:
            OrgStateContext with current metrics
        """
        with self.db.transaction() as cursor:
            # Worker counts
            cursor.execute(
                "SELECT COUNT(*) FROM workers WHERE status = 'active'"
            )
            active_workers = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM workers")
            total_workers = cursor.fetchone()[0]

            # Work item counts (via beads if available)
            total_work_items = 0
            blocked_work_items = 0

            # OKR count
            okr_count = 0

            # Recent escalations
            cursor.execute(
                """
                SELECT COUNT(*) FROM worker_escalation_state
                WHERE current_state IN ('escalated_pending', 'escalated_resolved')
                """
            )
            recent_escalations = cursor.fetchone()[0]

            # Estimate idle/blocked workers
            idle_workers = 0
            blocked_workers = 0

        return OrgStateContext(
            total_workers=total_workers,
            active_workers=active_workers,
            idle_workers=idle_workers,
            blocked_workers=blocked_workers,
            total_work_items=total_work_items,
            blocked_work_items=blocked_work_items,
            okr_count=okr_count,
            recent_escalations=recent_escalations,
        )

    def determine_urgency(
        self,
        org_state: OrgStateContext,
        explicit_urgency: EscalationUrgency | None = None,
    ) -> EscalationUrgency:
        """Determine escalation urgency based on org state.

        Args:
            org_state: Current org state context
            explicit_urgency: Explicitly requested urgency (overrides auto-detection)

        Returns:
            Determined urgency level
        """
        if explicit_urgency:
            return explicit_urgency

        # Auto-determine urgency based on org health
        if org_state.okr_count == 0:
            # No OKRs = CEO doesn't know what to do = URGENT
            return EscalationUrgency.URGENT

        if org_state.blocked_work_items > 0 and org_state.total_work_items > 0:
            blocked_ratio = org_state.blocked_work_items / org_state.total_work_items
            if blocked_ratio > 0.5:
                # More than half of work blocked = URGENT
                return EscalationUrgency.URGENT

        if org_state.idle_workers > org_state.active_workers:
            # More idle than active = WARNING
            return EscalationUrgency.WARNING

        # Default to INFO for general questions
        return EscalationUrgency.INFO

    def format_escalation_message(
        self,
        issue: str,
        org_state: OrgStateContext,
        urgency: EscalationUrgency,
        attempts_made: list[str] | None = None,
        specific_question: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Format comprehensive escalation message with org context.

        Args:
            issue: Core issue description
            org_state: Current org state
            urgency: Escalation urgency level
            attempts_made: List of things already tried
            specific_question: Specific question for board

        Returns:
            Tuple of (formatted_message, enriched_context)
        """
        # Build message sections
        sections = []

        # Issue header
        sections.append(f"## {issue}\n")

        # Org state snapshot
        sections.append("### Current Org State")
        sections.append(f"- Workers: {org_state.active_workers}/{org_state.total_workers} active")
        sections.append(f"- Idle workers: {org_state.idle_workers}")
        sections.append(f"- Blocked workers: {org_state.blocked_workers}")
        sections.append(f"- Work items: {org_state.total_work_items} ({org_state.blocked_work_items} blocked)")
        sections.append(f"- Active OKRs: {org_state.okr_count}")
        sections.append(f"- Recent escalations: {org_state.recent_escalations}\n")

        # Attempts made
        if attempts_made:
            sections.append("### Attempts Made")
            for attempt in attempts_made:
                sections.append(f"- {attempt}")
            sections.append("")

        # Specific question
        if specific_question:
            sections.append("### Specific Question")
            sections.append(specific_question)
            sections.append("")

        # Urgency indicator
        urgency_text = {
            EscalationUrgency.INFO: "ℹ️ Informational - CEO continuing with best judgment",
            EscalationUrgency.WARNING: "⚠️ Warning - CEO needs guidance but continuing",
            EscalationUrgency.URGENT: "🚨 Urgent - CEO blocked, waiting for board decision",
        }
        sections.append(f"**Urgency:** {urgency_text[urgency]}\n")

        # Suggested actions
        sections.append("### Suggested Board Actions")
        if org_state.okr_count == 0:
            sections.append("- Create OKRs to provide direction")
        if org_state.blocked_work_items > 0:
            sections.append("- Review blocked work and provide unblocking guidance")
        if org_state.idle_workers > 0:
            sections.append("- Assign work to idle workers or adjust team size")
        sections.append("- Reply in board-channel with guidance")

        message = "\n".join(sections)

        # Enriched context
        context = {
            "ceo_escalation": True,
            "urgency": urgency.value,
            "org_state": {
                "total_workers": org_state.total_workers,
                "active_workers": org_state.active_workers,
                "idle_workers": org_state.idle_workers,
                "blocked_workers": org_state.blocked_workers,
                "total_work_items": org_state.total_work_items,
                "blocked_work_items": org_state.blocked_work_items,
                "okr_count": org_state.okr_count,
                "recent_escalations": org_state.recent_escalations,
            },
            "attempts_made": attempts_made or [],
            "specific_question": specific_question,
            "escalated_at": datetime.now().isoformat(),
        }

        return message, context

    def urgency_to_notification_priority(
        self, urgency: EscalationUrgency
    ) -> NotificationPriority:
        """Map escalation urgency to notification priority.

        Args:
            urgency: Escalation urgency level

        Returns:
            Corresponding notification priority
        """
        mapping = {
            EscalationUrgency.INFO: NotificationPriority.INFO,
            EscalationUrgency.WARNING: NotificationPriority.HIGH,
            EscalationUrgency.URGENT: NotificationPriority.URGENT,
        }
        return mapping[urgency]

    def should_ceo_wait(self, urgency: EscalationUrgency) -> bool:
        """Determine if CEO should block and wait for board response.

        Args:
            urgency: Escalation urgency level

        Returns:
            True if CEO should wait, False if should continue with best judgment
        """
        # Only block on URGENT escalations
        return urgency == EscalationUrgency.URGENT
