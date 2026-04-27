"""Read org-level state: org info and budget. Health lives in health.py."""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ...interfaces.org_connection import BudgetSummary, OrgInfo, OrgStatus
from ...logging_config import get_board_logger
from ._helpers import DEFAULT_ORG_ID, parse_datetime

logger = get_board_logger(__name__)


class OrgStateReader:
    """Read top-level org state (status, worker counts, budget)."""

    def __init__(self, db: Any, org_path: Path) -> None:
        self._db = db
        self._org_path = org_path

    def get_org_info(self) -> OrgInfo:
        """Get current org information."""
        row = self._db.fetchone(
            "SELECT * FROM org_state WHERE id = ?", (DEFAULT_ORG_ID,)
        )

        if not row:
            return OrgInfo(
                path=self._org_path,
                name=self._org_path.name,
                status=OrgStatus.UNINITIALIZED,
                ceo_worker_id=None,
                worker_count=0,
                active_session_count=0,
                started_at=None,
                stopped_at=None,
            )

        worker_count = self._get_worker_count()
        active_session_count = self._get_active_session_count()

        try:
            status = OrgStatus(row["status"])
        except ValueError:
            status = OrgStatus.UNINITIALIZED

        return OrgInfo(
            path=self._org_path,
            name=self._org_path.name,
            status=status,
            ceo_worker_id=row["ceo_worker_id"],
            worker_count=worker_count,
            active_session_count=active_session_count,
            started_at=parse_datetime(row["started_at"]),
            stopped_at=parse_datetime(row["stopped_at"]),
        )

    def _get_worker_count(self) -> int:
        row = self._db.fetchone("SELECT COUNT(*) as count FROM workers")
        return row["count"] if row else 0

    def _get_active_session_count(self) -> int:
        try:
            row = self._db.fetchone(
                """SELECT COUNT(*) as count FROM sessions
                   WHERE state IN ('starting', 'running', 'idle')"""
            )
            if row and row["count"] > 0:
                return row["count"]
        except Exception:
            pass

        try:
            row = self._db.fetchone(
                """SELECT COUNT(*) as count FROM worker_state
                   WHERE runtime_status IN ('starting', 'running', 'idle')"""
            )
            return row["count"] if row else 0
        except Exception as e:
            logger.warning(
                "Failed to query session tables, org database may have unexpected schema: %s",
                e,
            )
            return 0

    def get_budget_summary(self) -> BudgetSummary:
        """Get budget summary for the org."""
        now = datetime.now()
        pool_row = self._db.fetchone(
            """SELECT * FROM budget_pools
               WHERE period_start <= ? AND period_end >= ?
               ORDER BY created_at DESC LIMIT 1""",
            (now, now),
        )

        if not pool_row:
            return BudgetSummary(
                total_allocated=0.0,
                total_spent=0.0,
                total_available=0.0,
                period_start=now,
                period_end=now + timedelta(days=30),
                spend_today=0.0,
                spend_this_week=0.0,
            )

        pool_id = pool_row["id"]
        period_start = parse_datetime(pool_row["period_start"]) or now
        period_end = parse_datetime(pool_row["period_end"]) or (now + timedelta(days=30))

        totals_row = self._db.fetchone(
            """SELECT
                   SUM(allocated) as total_allocated,
                   SUM(spent) as total_spent,
                   SUM(available) as total_available
               FROM budget_balances bb
               JOIN budget_allocations ba ON bb.allocation_id = ba.id
               WHERE ba.pool_id = ?""",
            (pool_id,),
        )

        if totals_row["total_allocated"] is None:
            total_allocated = total_spent = total_available = 0.0
        else:
            total_allocated = float(totals_row["total_allocated"] or 0)
            total_spent = float(totals_row["total_spent"] or 0)
            total_available = float(totals_row["total_available"] or 0)

        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        spend_today_row = self._db.fetchone(
            """SELECT SUM(ABS(amount)) as total
               FROM budget_transactions
               WHERE type = 'spend' AND created_at >= ?""",
            (today_start,),
        )
        spend_today = float(spend_today_row["total"] or 0)

        week_start = today_start - timedelta(days=today_start.weekday())
        spend_week_row = self._db.fetchone(
            """SELECT SUM(ABS(amount)) as total
               FROM budget_transactions
               WHERE type = 'spend' AND created_at >= ?""",
            (week_start,),
        )
        spend_this_week = float(spend_week_row["total"] or 0)

        return BudgetSummary(
            total_allocated=total_allocated,
            total_spent=total_spent,
            total_available=total_available,
            period_start=period_start,
            period_end=period_end,
            spend_today=spend_today,
            spend_this_week=spend_this_week,
        )
