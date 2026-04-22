"""
Read-only operations for QuinnAI org state.

OrgReader handles all data retrieval from the org's SQLite database.
Intended to be used as a delegate from QuinnAIOrgConnection.
"""

import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from ..logging_config import get_board_logger
from ..interfaces.org_connection import (
    OrgInfo,
    OrgStatus,
    WorkerInfo,
    WorkerStatus,
    SessionState,
    BudgetSummary,
    Message,
    OKRInfo,
)

logger = get_board_logger(__name__)

_DEFAULT_ORG_ID = "default"


class OrgReader:
    """All read operations for a QuinnAI org.

    Takes a database wrapper and org path. All methods are stateless reads —
    no mutations to the database.

    Args:
        db: A database wrapper with fetchone/fetchall/execute/connection interface
        org_path: Resolved path to the org directory
        board_channel: Name of the board channel (for message reads)
        escalations_channel: Fallback channel name for backward compatibility
    """

    def __init__(
        self,
        db: Any,
        org_path: Path,
        board_channel: str,
        escalations_channel: str,
    ) -> None:
        self._db = db
        self._org_path = org_path
        self._board_channel = board_channel
        self._escalations_channel = escalations_channel

    # ==================
    # ORG STATE
    # ==================

    def get_org_info(self) -> OrgInfo:
        """Get current org information."""
        row = self._db.fetchone("SELECT * FROM org_state WHERE id = ?", (_DEFAULT_ORG_ID,))

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

        status_str = row["status"]
        try:
            status = OrgStatus(status_str)
        except ValueError:
            status = OrgStatus.UNINITIALIZED

        started_at = self._parse_datetime(row["started_at"])
        stopped_at = self._parse_datetime(row["stopped_at"])

        return OrgInfo(
            path=self._org_path,
            name=self._org_path.name,
            status=status,
            ceo_worker_id=row["ceo_worker_id"],
            worker_count=worker_count,
            active_session_count=active_session_count,
            started_at=started_at,
            stopped_at=stopped_at,
        )

    def _get_worker_count(self) -> int:
        """Get total worker count."""
        row = self._db.fetchone("SELECT COUNT(*) as count FROM workers")
        return row["count"] if row else 0

    def _get_active_session_count(self) -> int:
        """Get count of active sessions."""
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
        period_start = self._parse_datetime(pool_row["period_start"]) or now
        period_end = self._parse_datetime(pool_row["period_end"]) or (
            now + timedelta(days=30)
        )

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
            total_allocated = 0.0
            total_spent = 0.0
            total_available = 0.0
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

    def get_health_status(self):
        """Get organization health status."""
        from ..interfaces.org_connection import HealthStatus, HealthIssue

        issues = []
        workers_with_issues_set = set()

        workers = self._db.fetchall(
            """SELECT id, name, status FROM workers
               WHERE status = 'active'"""
        )

        for worker in workers:
            worker_id = worker["id"]
            worker_name = worker["name"]

            okr_count = self._db.fetchone(
                """SELECT COUNT(*) as count FROM okrs
                   WHERE owner_worker_id = ? AND status = 'active'""",
                (worker_id,)
            )["count"]

            if okr_count == 0:
                issues.append(HealthIssue(
                    worker_id=worker_id,
                    worker_name=worker_name,
                    issue_type="no_okrs",
                    severity="warning",
                    message=f"{worker_name} has no active OKRs assigned"
                ))
                workers_with_issues_set.add(worker_id)

            try:
                result = subprocess.run(
                    ["bd", "list", "--assignee", worker_id, "--status=open,in_progress", "--json"],
                    cwd=self._org_path,
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                if result.returncode == 0:
                    import json as json_lib
                    beads = json_lib.loads(result.stdout)
                    if len(beads) == 0:
                        issues.append(HealthIssue(
                            worker_id=worker_id,
                            worker_name=worker_name,
                            issue_type="no_tasks",
                            severity="info",
                            message=f"{worker_name} has no open tasks assigned"
                        ))
                        workers_with_issues_set.add(worker_id)
            except (subprocess.TimeoutExpired, Exception) as e:
                logger.debug(f"Skipping task check for {worker_name}: {e}")

            session = self._db.fetchone(
                """SELECT state FROM sessions
                   WHERE worker_id = ? AND state != 'stopped'
                   ORDER BY created_at DESC LIMIT 1""",
                (worker_id,)
            )
            if session and session["state"] == "crashed":
                issues.append(HealthIssue(
                    worker_id=worker_id,
                    worker_name=worker_name,
                    issue_type="crashed_session",
                    severity="error",
                    message=f"{worker_name} has a crashed session"
                ))
                workers_with_issues_set.add(worker_id)

        total_workers = len(workers)
        workers_with_issues = len(workers_with_issues_set)

        if total_workers == 0:
            overall_score = "healthy"
        else:
            critical_count = sum(1 for issue in issues if issue.severity == "critical")
            warning_count = sum(1 for issue in issues if issue.severity == "warning")

            if critical_count > 0:
                overall_score = "critical"
            elif warning_count > 0:
                overall_score = "warning"
            else:
                overall_score = "healthy"

        return HealthStatus(
            overall_score=overall_score,
            issues=issues,
            workers_with_issues=workers_with_issues,
            total_workers=total_workers,
            last_checked=datetime.now()
        )

    # ==================
    # WORKERS
    # ==================

    def get_workers(self) -> list[WorkerInfo]:
        """Get all workers in the org."""
        rows = self._db.fetchall(
            """SELECT w.*, t.name as team_name
               FROM workers w
               JOIN teams t ON w.team_id = t.id
               ORDER BY w.manager_id NULLS FIRST, w.created_at"""
        )

        session_states = self._get_worker_session_states()

        org_row = self._db.fetchone(
            "SELECT ceo_worker_id FROM org_state WHERE id = ?", (_DEFAULT_ORG_ID,)
        )
        ceo_id = org_row["ceo_worker_id"] if org_row else None

        workers = []
        for row in rows:
            worker_id = row["id"]
            session_info = session_states.get(worker_id, {})
            is_ceo = (worker_id == ceo_id)
            role = row["role"]
            manager_id = row["manager_id"]

            is_manager = (manager_id is None) and not is_ceo
            session_mode = "autonomous" if (is_ceo or is_manager) else "interactive"

            workers.append(
                WorkerInfo(
                    id=worker_id,
                    name=row["name"],
                    role=role,
                    team_name=row["team_name"],
                    status=self._parse_worker_status(row["status"]),
                    session_state=self._parse_session_state(
                        session_info.get("state")
                    ),
                    tmux_session_name=session_info.get("tmux_session_name"),
                    manager_id=manager_id,
                    current_task=session_info.get("current_task_id"),
                    is_ceo=is_ceo,
                    session_mode=session_mode,
                )
            )

        return workers

    def get_worker(self, worker_id: str) -> Optional[WorkerInfo]:
        """Get a specific worker by ID."""
        row = self._db.fetchone(
            """SELECT w.*, t.name as team_name
               FROM workers w
               JOIN teams t ON w.team_id = t.id
               WHERE w.id = ?""",
            (worker_id,),
        )

        if not row:
            return None

        session_info = self._get_worker_session_state(worker_id)

        org_row = self._db.fetchone(
            "SELECT ceo_worker_id FROM org_state WHERE id = ?", (_DEFAULT_ORG_ID,)
        )
        ceo_id = org_row["ceo_worker_id"] if org_row else None
        is_ceo = (worker_id == ceo_id)
        manager_id = row["manager_id"]

        is_manager = (manager_id is None) and not is_ceo
        session_mode = "autonomous" if (is_ceo or is_manager) else "interactive"

        return WorkerInfo(
            id=worker_id,
            name=row["name"],
            role=row["role"],
            team_name=row["team_name"],
            status=self._parse_worker_status(row["status"]),
            session_state=self._parse_session_state(session_info.get("state")),
            tmux_session_name=session_info.get("tmux_session_name"),
            manager_id=manager_id,
            current_task=session_info.get("current_task_id"),
            is_ceo=is_ceo,
            session_mode=session_mode,
        )

    def get_ceo(self) -> Optional[WorkerInfo]:
        """Get the CEO worker."""
        org_row = self._db.fetchone(
            "SELECT ceo_worker_id FROM org_state WHERE id = ?", (_DEFAULT_ORG_ID,)
        )

        if not org_row or not org_row["ceo_worker_id"]:
            return None

        return self.get_worker(org_row["ceo_worker_id"])

    def get_recent_activity(
        self,
        minutes: int = 30,
        limit: int = 50,
    ) -> list[dict]:
        """Get recent activity from all workers."""
        activity_dir = self._org_path / "live" / "logs" / "activity"
        if not activity_dir.exists():
            return []

        cutoff = datetime.now() - timedelta(minutes=minutes)
        all_activities = []

        for activity_file in activity_dir.glob("*.jsonl"):
            try:
                with open(activity_file, "r") as f:
                    for line in f:
                        try:
                            activity = json.loads(line)
                            activity_time = datetime.fromisoformat(activity["timestamp"])
                            if activity_time >= cutoff:
                                all_activities.append(activity)
                        except (json.JSONDecodeError, KeyError, ValueError):
                            continue
            except Exception as e:
                logger.warning(f"Failed to read activity file {activity_file}: {e}")
                continue

        all_activities.sort(key=lambda x: x["timestamp"], reverse=True)
        return all_activities[:limit]

    def _get_worker_session_states(self) -> dict[str, dict]:
        """Get session states for all workers."""
        rows = self._db.fetchall(
            """SELECT worker_id, state, tmux_session_name
               FROM sessions"""
        )

        result = {}
        for row in rows:
            result[row["worker_id"]] = {
                "state": row["state"],
                "tmux_session_name": row["tmux_session_name"],
            }

        state_rows = self._db.fetchall(
            """SELECT worker_id, current_task_id, runtime_status
               FROM worker_state"""
        )

        for row in state_rows:
            worker_id = row["worker_id"]
            if worker_id not in result:
                result[worker_id] = {"state": row["runtime_status"]}
            result[worker_id]["current_task_id"] = row["current_task_id"]

        return result

    def _get_worker_session_state(self, worker_id: str) -> dict:
        """Get session state for a specific worker."""
        row = self._db.fetchone(
            """SELECT state, tmux_session_name
               FROM sessions WHERE worker_id = ?""",
            (worker_id,),
        )

        if row:
            result = {
                "state": row["state"],
                "tmux_session_name": row["tmux_session_name"],
            }
        else:
            result = {}

        state_row = self._db.fetchone(
            """SELECT current_task_id, runtime_status
               FROM worker_state WHERE worker_id = ?""",
            (worker_id,),
        )

        if state_row:
            if "state" not in result:
                result["state"] = state_row["runtime_status"]
            result["current_task_id"] = state_row["current_task_id"]

        return result

    # ==================
    # MESSAGES
    # ==================

    def _get_board_channel_id(self) -> Optional[str]:
        """Get board channel ID, trying board-channel first, then escalations."""
        channel = self._db.fetchone(
            "SELECT id FROM channels WHERE name = ?",
            (self._board_channel,),
        )
        if channel:
            return channel["id"]

        channel = self._db.fetchone(
            "SELECT id FROM channels WHERE name = ?",
            (self._escalations_channel,),
        )
        return channel["id"] if channel else None

    def get_all_channels(self) -> list[dict[str, Any]]:
        """Get all channels in the org."""
        rows = self._db.fetchall(
            """SELECT c.id, c.name, c.type, c.team_id
               FROM channels c
               ORDER BY c.name"""
        )

        channels = []
        for row in rows:
            channel_id = row["id"]
            unread_row = self._db.fetchone(
                """SELECT COUNT(DISTINCT m.id) as count
                   FROM messages m
                   JOIN notification_beads nb ON nb.message_id = m.id
                   WHERE m.channel_id = ? AND nb.status = 'pending'""",
                (channel_id,),
            )
            unread_count = unread_row["count"] if unread_row else 0

            channels.append({
                "id": channel_id,
                "name": row["name"],
                "type": row["type"],
                "team_id": row["team_id"],
                "unread_count": unread_count,
            })

        return channels

    def get_channel_messages(
        self,
        channel_id: str,
        unread_only: bool = False,
        limit: int = 100,
    ) -> list[Message]:
        """Get messages from a specific channel."""
        if unread_only:
            rows = self._db.fetchall(
                """SELECT DISTINCT m.*,
                          COALESCE(w.name, m.from_worker_id) as from_worker_name,
                          c.name as channel_name
                   FROM messages m
                   LEFT JOIN workers w ON m.from_worker_id = w.id
                   JOIN channels c ON m.channel_id = c.id
                   JOIN notification_beads nb ON nb.message_id = m.id
                   WHERE m.channel_id = ? AND nb.status = 'pending'
                   ORDER BY m.priority DESC, m.created_at DESC
                   LIMIT ?""",
                (channel_id, limit),
            )
        else:
            rows = self._db.fetchall(
                """SELECT m.*,
                          COALESCE(w.name, m.from_worker_id) as from_worker_name,
                          c.name as channel_name
                   FROM messages m
                   LEFT JOIN workers w ON m.from_worker_id = w.id
                   JOIN channels c ON m.channel_id = c.id
                   WHERE m.channel_id = ?
                   ORDER BY m.priority DESC, m.created_at DESC
                   LIMIT ?""",
                (channel_id, limit),
            )

        messages = []
        for row in rows:
            is_read = self._is_message_read(row["id"])

            messages.append(
                Message(
                    id=row["id"],
                    from_worker_id=row["from_worker_id"],
                    from_worker_name=row["from_worker_name"],
                    channel_name=row["channel_name"],
                    content=row["content"],
                    priority=row["priority"],
                    created_at=self._parse_datetime(row["created_at"]) or datetime.now(),
                    is_read=is_read,
                    requires_response=row["priority"] >= 3,
                )
            )

        return messages

    def get_board_messages(self, unread_only: bool = False) -> list[Message]:
        """Get messages escalated to the board."""
        channel_id = self._get_board_channel_id()

        if not channel_id:
            return []

        if unread_only:
            rows = self._db.fetchall(
                """SELECT DISTINCT m.*,
                          COALESCE(w.name, m.from_worker_id) as from_worker_name,
                          c.name as channel_name
                   FROM messages m
                   LEFT JOIN workers w ON m.from_worker_id = w.id
                   JOIN channels c ON m.channel_id = c.id
                   JOIN notification_beads nb ON nb.message_id = m.id
                   WHERE m.channel_id = ? AND nb.status = 'pending'
                   ORDER BY m.priority DESC, m.created_at DESC""",
                (channel_id,),
            )
        else:
            rows = self._db.fetchall(
                """SELECT m.*,
                          COALESCE(w.name, m.from_worker_id) as from_worker_name,
                          c.name as channel_name
                   FROM messages m
                   LEFT JOIN workers w ON m.from_worker_id = w.id
                   JOIN channels c ON m.channel_id = c.id
                   WHERE m.channel_id = ?
                   ORDER BY m.priority DESC, m.created_at DESC""",
                (channel_id,),
            )

        messages = []
        for row in rows:
            is_read = self._is_message_read(row["id"])

            messages.append(
                Message(
                    id=row["id"],
                    from_worker_id=row["from_worker_id"],
                    from_worker_name=row["from_worker_name"],
                    channel_name=row["channel_name"],
                    content=row["content"],
                    priority=row["priority"],
                    created_at=self._parse_datetime(row["created_at"]) or datetime.now(),
                    is_read=is_read,
                    requires_response=row["priority"] >= 3,
                )
            )

        return messages

    def get_unread_count(self) -> int:
        """Get count of unread board messages."""
        channel_id = self._get_board_channel_id()

        if not channel_id:
            return 0

        count_row = self._db.fetchone(
            """SELECT COUNT(DISTINCT m.id) as count
               FROM messages m
               JOIN notification_beads nb ON nb.message_id = m.id
               WHERE m.channel_id = ? AND nb.status = 'pending'""",
            (channel_id,),
        )

        return count_row["count"] if count_row else 0

    def mark_message_read(self, message_id: str) -> bool:
        """Mark a message as read by closing all pending notification beads."""
        try:
            now = datetime.now()
            self._db.execute(
                """UPDATE notification_beads
                   SET status = 'read', read_at = ?
                   WHERE message_id = ? AND status = 'pending'""",
                (now, message_id),
            )
            self._db.connection.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to mark message {message_id} as read: {e}")
            return False

    def _is_message_read(self, message_id: str) -> bool:
        """Check if a message has been read (no pending notification beads)."""
        row = self._db.fetchone(
            """SELECT COUNT(*) as count FROM notification_beads
               WHERE message_id = ? AND status = 'pending'""",
            (message_id,),
        )
        return row["count"] == 0 if row else True

    # ==================
    # OKRS
    # ==================

    def get_okrs(self, owner_id: Optional[str] = None) -> list[OKRInfo]:
        """Get OKRs, optionally filtered by owner."""
        if owner_id:
            rows = self._db.fetchall(
                """SELECT o.*, w.name as owner_name
                   FROM okrs o
                   JOIN workers w ON o.owner_worker_id = w.id
                   WHERE o.owner_worker_id = ?
                   ORDER BY o.parent_okr_id NULLS FIRST, o.created_at""",
                (owner_id,),
            )
        else:
            rows = self._db.fetchall(
                """SELECT o.*, w.name as owner_name
                   FROM okrs o
                   JOIN workers w ON o.owner_worker_id = w.id
                   ORDER BY o.parent_okr_id NULLS FIRST, o.created_at"""
            )

        okrs = []
        for row in rows:
            key_results = self._parse_key_results(row["key_results"])
            children_count = self._count_child_okrs(row["id"])

            okrs.append(
                OKRInfo(
                    id=row["id"],
                    title=row["title"],
                    description=row["description"],
                    owner_name=row["owner_name"],
                    owner_id=row["owner_worker_id"],
                    status=row["status"],
                    parent_id=row["parent_okr_id"],
                    key_results=key_results,
                    due_date=self._parse_datetime(row["due_date"]),
                    children_count=children_count,
                )
            )

        return okrs

    def _parse_key_results(self, kr_json: Optional[str]) -> list[dict[str, Any]]:
        """Parse key results from JSON string."""
        if not kr_json:
            return []
        try:
            return json.loads(kr_json)
        except (json.JSONDecodeError, TypeError):
            return []

    def _count_child_okrs(self, okr_id: str) -> int:
        """Count OKRs that have this OKR as parent."""
        row = self._db.fetchone(
            "SELECT COUNT(*) as count FROM okrs WHERE parent_okr_id = ?",
            (okr_id,),
        )
        return row["count"] if row else 0

    def get_current_briefing(self) -> Optional[str]:
        """Get current CEO briefing from config file."""
        briefing_path = self._org_path / "config" / "ceo_briefing.md"
        if briefing_path.exists():
            return briefing_path.read_text()
        return None

    # ==================
    # CURSOR-BASED STATUS POLLING
    # ==================

    def get_status_changes_since_cursor(self, cursor_id: int) -> list[dict]:
        """Get status changes since a given cursor position."""
        try:
            rows = self._db.fetchall(
                """SELECT id, entity_type, entity_id, old_status, new_status, changed_at
                   FROM status_changes
                   WHERE id > ?
                   ORDER BY id ASC""",
                (cursor_id,)
            )

            return [
                {
                    "id": row["id"],
                    "entity_type": row["entity_type"],
                    "entity_id": row["entity_id"],
                    "old_status": row["old_status"],
                    "new_status": row["new_status"],
                    "changed_at": row["changed_at"],
                }
                for row in rows
            ]
        except Exception as e:
            logger.debug(f"Error fetching status changes: {e}")
            return []

    def get_last_status_change_id(self) -> int:
        """Get the latest status change ID."""
        try:
            row = self._db.fetchone(
                "SELECT MAX(id) as max_id FROM status_changes"
            )
            if row and row["max_id"] is not None:
                return int(row["max_id"])
            return 0
        except Exception as e:
            logger.debug(f"Error fetching last status change ID: {e}")
            return 0

    def has_pending_changes(self, cursor_id: int) -> bool:
        """Check if there are pending status changes since cursor."""
        try:
            row = self._db.fetchone(
                "SELECT 1 FROM status_changes WHERE id > ? LIMIT 1",
                (cursor_id,)
            )
            return row is not None
        except Exception as e:
            logger.debug(f"Error checking for pending changes: {e}")
            return False

    # ==================
    # PROVIDER CONFIGURATION
    # ==================

    def get_provider_config(self) -> dict:
        """Get provider configuration for the org."""
        try:
            import yaml

            config_path = self._org_path / "config" / "providers.yaml"
            if not config_path.exists():
                return {"default": "claude_code", "providers": {}}

            with open(config_path) as f:
                config = yaml.safe_load(f) or {}

            default_provider = config.get("default", "claude_code")

            result = subprocess.run(
                ["qn", "--org-path", str(self._org_path), "org", "provider", "list"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            providers = {}
            if result.returncode == 0:
                providers = self._parse_provider_list(result.stdout)

            return {
                "default": default_provider,
                "providers": providers,
            }

        except Exception as e:
            logger.error(f"Failed to get provider config: {e}")
            return {"default": "claude_code", "providers": {}}

    def _parse_provider_list(self, output: str) -> dict[str, dict]:
        """Parse output from 'qn org provider list' command."""
        providers = {}
        current_provider = None

        for line in output.split("\n"):
            line = line.strip()
            if not line or line.startswith("Available") or line.startswith("Total"):
                continue

            if line and not line.startswith(" "):
                current_provider = line
                providers[current_provider] = {
                    "enabled": True,
                    "capabilities": [],
                    "aliases": [],
                }
            elif current_provider and line.startswith(" "):
                if "Aliases:" in line:
                    aliases_str = line.split("Aliases:", 1)[1].strip()
                    providers[current_provider]["aliases"] = [
                        a.strip() for a in aliases_str.split(",")
                    ]
                elif "Capabilities:" in line:
                    caps_str = line.split("Capabilities:", 1)[1].strip()
                    providers[current_provider]["capabilities"] = [
                        c.strip() for c in caps_str.split(",")
                    ]

        return providers

    # ==================
    # HELPERS
    # ==================

    def _parse_datetime(self, value: Any) -> Optional[datetime]:
        """Parse datetime from various formats."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return None

    def _parse_worker_status(self, status_str: str) -> WorkerStatus:
        """Parse worker status string to enum."""
        try:
            return WorkerStatus(status_str)
        except ValueError:
            return WorkerStatus.PENDING

    def _parse_session_state(self, state_str: Optional[str]) -> Optional[SessionState]:
        """Parse session state string to enum."""
        if not state_str:
            return None
        try:
            return SessionState(state_str)
        except ValueError:
            return None
