"""
Read-only operations for QuinnAI org state.

OrgReader is a facade composing per-domain readers (org state, workers,
messages, OKRs, activity, providers, change cursors). Each reader lives in
services/readers/ and owns one slice of the schema.

QuinnAIOrgConnection treats OrgReader as a single delegate, so its public
API is unaffected by this split.
"""

from pathlib import Path
from typing import Any, Optional

from ..interfaces.org_connection import (
    BudgetSummary,
    Message,
    OKRInfo,
    OrgInfo,
    WorkerInfo,
)
from .readers import (
    ActivityReader,
    ChangeCursorReader,
    HealthReader,
    MessageReader,
    OKRReader,
    OrgStateReader,
    ProviderReader,
    WorkerReader,
)


class OrgReader:
    """Facade over the per-domain readers for one org's database.

    Args:
        db: A database wrapper with fetchone/fetchall/execute/connection
        org_path: Resolved path to the org directory
        board_channel: Name of the board channel
        escalations_channel: Fallback channel name for backward compatibility
    """

    def __init__(
        self,
        db: Any,
        org_path: Path,
        board_channel: str,
        escalations_channel: str,
    ) -> None:
        self._org = OrgStateReader(db, org_path)
        self._workers = WorkerReader(db, org_path)
        self._messages = MessageReader(db, org_path, board_channel, escalations_channel)
        self._okrs = OKRReader(db, org_path)
        self._activity = ActivityReader(db, org_path)
        self._providers = ProviderReader(db, org_path)
        self._cursors = ChangeCursorReader(db)
        self._health = HealthReader(db, org_path)

    # ---- org state ----
    def get_org_info(self) -> OrgInfo:
        return self._org.get_org_info()

    def get_budget_summary(self) -> BudgetSummary:
        return self._org.get_budget_summary()

    def get_health_status(self):
        return self._health.get_health_status()

    # ---- workers ----
    def get_workers(self) -> list[WorkerInfo]:
        return self._workers.get_workers()

    def get_worker(self, worker_id: str) -> Optional[WorkerInfo]:
        return self._workers.get_worker(worker_id)

    def get_ceo(self) -> Optional[WorkerInfo]:
        return self._workers.get_ceo()

    # ---- activity ----
    def get_recent_activity(self, minutes: int = 30, limit: int = 50) -> list[dict]:
        return self._activity.get_recent_activity(minutes=minutes, limit=limit)

    # ---- messages ----
    def get_all_channels(self) -> list[dict[str, Any]]:
        return self._messages.get_all_channels()

    def get_channel_messages(
        self,
        channel_id: str,
        unread_only: bool = False,
        limit: int = 100,
    ) -> list[Message]:
        return self._messages.get_channel_messages(
            channel_id=channel_id, unread_only=unread_only, limit=limit
        )

    def get_board_messages(self, unread_only: bool = False) -> list[Message]:
        return self._messages.get_board_messages(unread_only=unread_only)

    def get_unread_count(self) -> int:
        return self._messages.get_unread_count()

    def mark_message_read(self, message_id: str) -> bool:
        return self._messages.mark_message_read(message_id)

    def _get_board_channel_id(self) -> Optional[str]:
        # OrgCommander reaches in here via callable injection.
        return self._messages.get_board_channel_id()

    # ---- OKRs / briefing ----
    def get_okrs(self, owner_id: Optional[str] = None) -> list[OKRInfo]:
        return self._okrs.get_okrs(owner_id=owner_id)

    def get_current_briefing(self) -> Optional[str]:
        return self._okrs.get_current_briefing()

    # ---- providers ----
    def get_provider_config(self) -> dict:
        return self._providers.get_provider_config()

    # ---- cursor-based polling ----
    def get_status_changes_since_cursor(self, cursor_id: int) -> list[dict]:
        return self._cursors.get_status_changes_since_cursor(cursor_id)

    def get_last_status_change_id(self) -> int:
        return self._cursors.get_last_status_change_id()

    def has_pending_changes(self, cursor_id: int) -> bool:
        return self._cursors.has_pending_changes(cursor_id)
