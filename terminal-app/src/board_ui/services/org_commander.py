"""
Mutation and intervention operations for QuinnAI org state.

OrgCommander is a facade composing per-domain commanders (lifecycle,
interventions, sessions, messages, briefing, providers, cursors). Each
commander lives in services/commanders/ and owns one slice of state-changing
behavior.

QuinnAIOrgConnection treats OrgCommander as a single delegate, so its public
API is unaffected by this split.
"""

from pathlib import Path
from typing import Any, Callable, Optional

from .commanders import (
    BriefingCommander,
    CursorsCommander,
    InterventionsCommander,
    LifecycleCommander,
    MessagesCommander,
    OrgContext,
    ProvidersCommander,
    SessionsCommander,
)


class OrgCommander:
    """Facade composing the per-domain commanders.

    Args:
        db: Database wrapper with fetchone/fetchall/execute/connection
        org_path: Resolved path to the org directory
        board_channel: Name of the board channel
        escalations_channel: Fallback channel name for backward compatibility
        get_ceo_fn: Callable returning the current CEO WorkerInfo (or None)
        get_board_channel_id_fn: Callable returning the board channel ID (or None)
        get_org_info_fn: Callable returning OrgInfo
        mark_message_read_fn: Callable(message_id) -> bool to mark a message read
    """

    def __init__(
        self,
        db: Any,
        org_path: Path,
        board_channel: str,
        escalations_channel: str,
        get_ceo_fn: Callable,
        get_board_channel_id_fn: Callable,
        get_org_info_fn: Callable,
        mark_message_read_fn: Callable,
    ) -> None:
        # Held on the facade so external callers (and tests) can identify
        # which db handle this commander binds — see test_org_commander_direct_calls.
        self._db = db
        self._org_path = org_path

        ctx = OrgContext(
            db=db,
            org_path=org_path,
            board_channel=board_channel,
            escalations_channel=escalations_channel,
            get_ceo=get_ceo_fn,
            get_board_channel_id=get_board_channel_id_fn,
            get_org_info=get_org_info_fn,
            mark_message_read=mark_message_read_fn,
        )
        self._lifecycle = LifecycleCommander(ctx)
        self._sessions = SessionsCommander(ctx)
        self._interventions = InterventionsCommander(ctx)
        self._messages = MessagesCommander(ctx)
        self._briefing = BriefingCommander(ctx)
        self._providers = ProvidersCommander(ctx)
        self._cursors = CursorsCommander(ctx)

    # ---- org lifecycle ----
    def start_org(self) -> bool:
        return self._lifecycle.start_org()

    def stop_org(self) -> bool:
        return self._lifecycle.stop_org()

    def restart_org(self) -> tuple[bool, str]:
        return self._lifecycle.restart_org()

    # ---- worker sessions ----
    def restart_worker_session(
        self,
        worker_id: str,
        force: bool = True,
    ) -> tuple[bool, Optional[str]]:
        return self._sessions.restart_worker_session(worker_id, force=force)

    def cleanup_stale_session(
        self,
        worker_id: str,
        tmux_session_name: Optional[str],
    ) -> bool:
        return self._sessions.cleanup_stale_session(worker_id, tmux_session_name)

    # ---- board interventions ----
    def pause_worker(self, worker_id: str, reason: Optional[str] = None) -> bool:
        return self._interventions.pause_worker(worker_id, reason=reason)

    def resume_worker(self, worker_id: str) -> bool:
        return self._interventions.resume_worker(worker_id)

    def fire_worker(self, worker_id: str, reason: Optional[str] = None) -> bool:
        return self._interventions.fire_worker(worker_id, reason=reason)

    # ---- board responses ----
    def send_board_response(self, message_id: str, response: str) -> bool:
        return self._messages.send_board_response(message_id, response)

    # ---- CEO briefing ----
    def send_ceo_briefing(self, briefing_content: str) -> bool:
        return self._briefing.send_ceo_briefing(briefing_content)

    def update_briefing(self, briefing_content: str) -> bool:
        return self._briefing.update_briefing(briefing_content)

    # ---- providers ----
    def set_default_provider(self, provider_name: str) -> tuple[bool, str]:
        return self._providers.set_default_provider(provider_name)

    def validate_provider_config(self) -> tuple[bool, list[str]]:
        return self._providers.validate_provider_config()

    # ---- cursor polling ----
    def update_poll_cursor(self, client_id: str, last_change_id: int) -> None:
        return self._cursors.update_poll_cursor(client_id, last_change_id)
