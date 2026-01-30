"""Health calculation service for org and worker health metrics.

Implements 5-factor health scoring algorithm:
- Active workers (35%) - % workers in running state
- OKR coverage (25%) - % workers with assigned OKRs  
- Idle duration (20%) - Inverse of avg idle time
- Escalation rate (10%) - Inverse of escalation frequency
- Communication (10%) - Message activity baseline
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

_logger = logging.getLogger(__name__)


# Health score thresholds
HEALTH_THRESHOLD_EXCELLENT = 90
HEALTH_THRESHOLD_GOOD = 70
HEALTH_THRESHOLD_FAIR = 50


@dataclass
class HealthFactorScore:
    """Score for a single health factor."""
    name: str
    score: float  # 0-100
    weight: float  # 0-1
    weighted_score: float
    status: str  # excellent, good, fair, poor
    details: str


@dataclass
class WorkerHealthInfo:
    """Health information for a single worker."""
    worker_id: str
    worker_name: str
    overall_score: float  # 0-100
    status: str  # excellent, good, fair, poor, critical
    issues: List[str]  # List of health issues
    is_idle: bool
    idle_duration_minutes: Optional[int]
    has_okrs: bool
    is_escalated: bool


@dataclass
class HealthMetrics:
    """Overall organization health metrics."""
    overall_score: float  # 0-100
    overall_status: str  # excellent, good, fair, poor, critical
    factors: List[HealthFactorScore]
    worker_health: List[WorkerHealthInfo]
    critical_issues: List[str]
    warnings: List[str]
    timestamp: datetime


class HealthCalculator:
    """Calculates org and worker health metrics."""

    # Factor weights (must sum to 1.0)
    FACTOR_WEIGHTS = {
        "active_workers": 0.35,
        "okr_coverage": 0.25,
        "idle_duration": 0.20,
        "escalation_rate": 0.10,
        "communication": 0.10,
    }

    def __init__(self, db):
        """Initialize health calculator.

        Args:
            db: Database instance
        """
        self.db = db

    def calculate_health(self) -> HealthMetrics:
        """Calculate complete health metrics for organization.

        Returns:
            HealthMetrics with all factor scores and worker health
        """
        # Calculate each factor
        factors = [
            self._calculate_active_workers(),
            self._calculate_okr_coverage(),
            self._calculate_idle_duration(),
            self._calculate_escalation_rate(),
            self._calculate_communication(),
        ]

        # Calculate overall score (weighted sum)
        overall_score = sum(f.weighted_score for f in factors)

        # Calculate per-worker health
        worker_health = self._calculate_worker_health()

        # Identify critical issues and warnings
        critical_issues = []
        warnings = []

        for factor in factors:
            if factor.score < 50:
                critical_issues.append(f"{factor.name}: {factor.details}")
            elif factor.score < 70:
                warnings.append(f"{factor.name}: {factor.details}")

        for worker in worker_health:
            if worker.status == "critical":
                critical_issues.append(f"Worker {worker.worker_name}: {', '.join(worker.issues)}")

        return HealthMetrics(
            overall_score=overall_score,
            overall_status=self._score_to_status(overall_score),
            factors=factors,
            worker_health=worker_health,
            critical_issues=critical_issues,
            warnings=warnings,
            timestamp=datetime.now(),
        )

    def _calculate_active_workers(self) -> HealthFactorScore:
        """Calculate active workers factor (35% weight)."""
        # Get total active/onboarding workers
        total_row = self.db.fetchone(
            "SELECT COUNT(*) as count FROM workers WHERE status IN ('active', 'onboarding')"
        )
        total = total_row["count"] if total_row else 0

        if total == 0:
            return HealthFactorScore(
                name="Active Workers",
                score=0.0,
                weight=self.FACTOR_WEIGHTS["active_workers"],
                weighted_score=0.0,
                status="poor",
                details="No active workers",
            )

        # Get workers with running sessions
        active_row = self.db.fetchone(
            """SELECT COUNT(DISTINCT w.id) as count
               FROM workers w
               JOIN sessions s ON s.worker_id = w.id
               WHERE w.status IN ('active', 'onboarding')
               AND s.state IN ('running', 'idle')"""
        )
        active = active_row["count"] if active_row else 0

        percentage = (active / total) * 100
        score = percentage  # 0-100

        weight = self.FACTOR_WEIGHTS["active_workers"]
        weighted = score * weight

        return HealthFactorScore(
            name="Active Workers",
            score=score,
            weight=weight,
            weighted_score=weighted,
            status=self._score_to_status(score),
            details=f"{active}/{total} workers running ({percentage:.0f}%)",
        )

    def _calculate_okr_coverage(self) -> HealthFactorScore:
        """Calculate OKR coverage factor (25% weight)."""
        # Get total workers
        total_row = self.db.fetchone(
            "SELECT COUNT(*) as count FROM workers WHERE status IN ('active', 'onboarding')"
        )
        total = total_row["count"] if total_row else 0

        if total == 0:
            return HealthFactorScore(
                name="OKR Coverage",
                score=0.0,
                weight=self.FACTOR_WEIGHTS["okr_coverage"],
                weighted_score=0.0,
                status="poor",
                details="No workers to assign OKRs",
            )

        # Get workers with OKRs
        with_okrs_row = self.db.fetchone(
            """SELECT COUNT(DISTINCT owner_worker_id) as count
               FROM okrs
               WHERE status = 'active'"""
        )
        with_okrs = with_okrs_row["count"] if with_okrs_row else 0

        percentage = (with_okrs / total) * 100
        score = percentage

        weight = self.FACTOR_WEIGHTS["okr_coverage"]
        weighted = score * weight

        return HealthFactorScore(
            name="OKR Coverage",
            score=score,
            weight=weight,
            weighted_score=weighted,
            status=self._score_to_status(score),
            details=f"{with_okrs}/{total} workers have OKRs ({percentage:.0f}%)",
        )

    def _calculate_idle_duration(self) -> HealthFactorScore:
        """Calculate idle duration factor (20% weight)."""
        # Get average idle duration for workers
        idle_row = self.db.fetchone(
            """SELECT AVG(
                   CAST((julianday('now') - julianday(last_activity_at)) * 1440 AS INTEGER)
               ) as avg_idle_minutes
               FROM worker_escalation_state
               WHERE current_state IN ('idle_warning', 'escalated_pending')"""
        )

        avg_idle = idle_row["avg_idle_minutes"] if idle_row and idle_row["avg_idle_minutes"] else 0

        # Score inversely proportional to idle time
        # 0 minutes = 100 score, 180+ minutes = 0 score
        if avg_idle == 0:
            score = 100.0
        elif avg_idle >= 180:
            score = 0.0
        else:
            score = 100 * (1 - (avg_idle / 180))

        weight = self.FACTOR_WEIGHTS["idle_duration"]
        weighted = score * weight

        return HealthFactorScore(
            name="Idle Duration",
            score=score,
            weight=weight,
            weighted_score=weighted,
            status=self._score_to_status(score),
            details=f"Average idle: {avg_idle:.0f} minutes",
        )

    def _calculate_escalation_rate(self) -> HealthFactorScore:
        """Calculate escalation rate factor (10% weight)."""
        # Get total workers
        total_row = self.db.fetchone(
            "SELECT COUNT(*) as count FROM workers WHERE status IN ('active', 'onboarding')"
        )
        total = total_row["count"] if total_row else 0

        if total == 0:
            score = 100.0
            details = "No workers"
        else:
            # Get escalated workers
            escalated_row = self.db.fetchone(
                """SELECT COUNT(*) as count
                   FROM worker_escalation_state
                   WHERE current_state = 'escalated_pending'"""
            )
            escalated = escalated_row["count"] if escalated_row else 0

            percentage = (escalated / total) * 100

            # Score inversely proportional to escalation rate
            # 0% escalated = 100 score, 50%+ escalated = 0 score
            if percentage == 0:
                score = 100.0
            elif percentage >= 50:
                score = 0.0
            else:
                score = 100 * (1 - (percentage / 50))

            details = f"{escalated}/{total} workers escalated ({percentage:.0f}%)"

        weight = self.FACTOR_WEIGHTS["escalation_rate"]
        weighted = score * weight

        return HealthFactorScore(
            name="Escalation Rate",
            score=score,
            weight=weight,
            weighted_score=weighted,
            status=self._score_to_status(score),
            details=details,
        )

    def _calculate_communication(self) -> HealthFactorScore:
        """Calculate communication factor (10% weight)."""
        # Get message activity in last 24 hours
        message_row = self.db.fetchone(
            """SELECT COUNT(*) as count
               FROM messages
               WHERE created_at > datetime('now', '-1 day')"""
        )
        message_count = message_row["count"] if message_row else 0

        # Get worker count for baseline
        worker_row = self.db.fetchone(
            "SELECT COUNT(*) as count FROM workers WHERE status IN ('active', 'onboarding')"
        )
        worker_count = worker_row["count"] if worker_row else 1

        # Expected baseline: 5 messages per worker per day
        expected = worker_count * 5
        percentage = (message_count / expected) * 100 if expected > 0 else 0

        # Cap at 100
        score = min(100.0, percentage)

        weight = self.FACTOR_WEIGHTS["communication"]
        weighted = score * weight

        return HealthFactorScore(
            name="Communication",
            score=score,
            weight=weight,
            weighted_score=weighted,
            status=self._score_to_status(score),
            details=f"{message_count} messages in 24h ({percentage:.0f}% of baseline)",
        )

    def _calculate_worker_health(self) -> List[WorkerHealthInfo]:
        """Calculate health for each worker."""
        workers_rows = self.db.fetchall(
            "SELECT id, name, role, status FROM workers WHERE status IN ('active', 'onboarding')"
        )

        worker_health = []

        for worker_row in workers_rows:
            worker_id = worker_row["id"]
            worker_name = worker_row["name"]

            # Check if worker has session
            session_row = self.db.fetchone(
                "SELECT state FROM sessions WHERE worker_id = ? AND state IN ('running', 'idle')",
                (worker_id,)
            )
            has_session = session_row is not None

            # Check if worker has OKRs
            okr_row = self.db.fetchone(
                "SELECT COUNT(*) as count FROM okrs WHERE owner_worker_id = ? AND status = 'active'",
                (worker_id,)
            )
            has_okrs = okr_row and okr_row["count"] > 0

            # Check escalation state
            escalation_row = self.db.fetchone(
                "SELECT current_state, idle_since FROM worker_escalation_state WHERE worker_id = ?",
                (worker_id,)
            )

            is_idle = False
            idle_minutes = None
            is_escalated = False

            if escalation_row:
                state = escalation_row["current_state"]
                is_idle = state in ("idle_warning", "escalated_pending")
                is_escalated = state == "escalated_pending"

                if is_idle and escalation_row["idle_since"]:
                    idle_since = datetime.fromisoformat(escalation_row["idle_since"])
                    idle_minutes = int((datetime.now() - idle_since).total_seconds() / 60)

            # Calculate worker score and identify issues
            issues = []
            score = 100.0

            if not has_session:
                score -= 40
                issues.append("No active session")

            if not has_okrs:
                score -= 30
                issues.append("No OKRs assigned")

            if is_escalated:
                score -= 20
                issues.append("Currently escalated")
            elif is_idle:
                score -= 10
                issues.append(f"Idle for {idle_minutes}m")

            score = max(0.0, score)

            worker_health.append(WorkerHealthInfo(
                worker_id=worker_id,
                worker_name=worker_name,
                overall_score=score,
                status=self._score_to_status(score),
                issues=issues,
                is_idle=is_idle,
                idle_duration_minutes=idle_minutes,
                has_okrs=has_okrs,
                is_escalated=is_escalated,
            ))

        return worker_health

    @staticmethod
    def _score_to_status(score: float) -> str:
        """Convert score to status string.

        Args:
            score: Health score (0-100)

        Returns:
            Status string
        """
        if score >= HEALTH_THRESHOLD_EXCELLENT:
            return "excellent"
        elif score >= HEALTH_THRESHOLD_GOOD:
            return "good"
        elif score >= HEALTH_THRESHOLD_FAIR:
            return "fair"
        else:
            return "poor"
