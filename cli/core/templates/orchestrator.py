"""TemplateOrchestrator — atomic hire-team operation with rollback.

Per quinn-ai-iabn §C.3 + §D, quinn-ai-cutg §2, quinn-ai-u0h2 §3.

The orchestrator runs the 14-step sequence:
1-4. Validation (template, parent reference, manager exists, channel collision).
5.   Reserve team_id.
6.   Begin transaction.
7.   Create team record.
8.   Create channel (if specified).
9.   Hire each member (manager first, then others) + add to team.
10.  Update team's lead_id to the in-template manager.
11.  Subscribe channel members.
12.  File initial OKRs.
13.  Set template_type, ttl_hours, ttl_started_at on the team row.
14.  Commit.

On any exception at step 7+, iterate the rollback stack in reverse:
fire workers, drop channel, delete team, close OKRs. If rollback itself fails,
raise HireTeamRollbackFailed for operator intervention.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from cli.core.queries.channel import create_channel
from cli.core.queries.common import generate_id
from cli.core.queries.team import add_team_member, create_team
from cli.core.queries.worker import get_worker
from cli.core.templates import _helpers
from cli.core.templates.composition import validate_parent_reference
from cli.core.templates.types import (
    HireTeamResult,
    Template,
    TemplateMember,
    TemplateRegistry,
)
from shared.exceptions import (
    ChannelNameCollision,
    HireTeamRollbackFailed,
    TemplateError,
    TemplateNotFound,
)

_logger = logging.getLogger(__name__)


class TemplateOrchestrator:
    """Atomic hire-team operation per iabn §D."""

    def __init__(self, ctx: Any, db: Any, registry: TemplateRegistry) -> None:
        self.ctx = ctx
        self.db = db
        self.registry = registry

    # --------------------------------------------------------------- public

    def hire_team(
        self,
        template_name: str,
        team_name: str,
        manager_id: str,
        *,
        parent_team_name: Optional[str] = None,
        size_overrides: Optional[dict[str, int]] = None,
        cost_overrides: Optional[dict[str, int]] = None,
        worker_names: Optional[dict[str, list[str]]] = None,
        dry_run: bool = False,
    ) -> HireTeamResult:
        size_overrides = size_overrides or {}
        cost_overrides = cost_overrides or {}
        worker_names = worker_names or {}

        # 1. Load + validate template.
        try:
            template = self.registry.get(template_name)
        except TemplateNotFound:
            raise

        # 2. Validate parent reference (raises if invalid).
        parent_lead_id = validate_parent_reference(
            template, parent_team_name, self.db
        )

        # 3. Validate manager exists.
        if get_worker(self.db, manager_id) is None:
            raise TemplateError(f"manager_id {manager_id!r} does not resolve to a known worker")

        # 4. Pre-validate channel collision.
        derived_channel_name = self._derive_channel_name(template, team_name)
        if derived_channel_name and self._channel_exists(derived_channel_name):
            raise ChannelNameCollision(derived_channel_name)

        # Dry-run: bail out before any DB writes.
        if dry_run:
            return HireTeamResult(
                team_id=f"dry:{template_name}",
                channel_id=f"dry:channel:{derived_channel_name}" if derived_channel_name else None,
                worker_ids=tuple(
                    f"dry:{m.role}-{i}"
                    for m in self._expand_members(template, size_overrides)
                    for i in range(1, m.count + 1)
                ),
                okr_ids=tuple(f"dry:okr:{i}" for i in range(len(template.initial_okrs))),
                rolled_back=False,
            )

        # 5-14. Real run with rollback.
        return self._run_with_rollback(
            template=template,
            team_name=team_name,
            manager_id=manager_id,
            parent_team_name=parent_team_name,
            size_overrides=size_overrides,
            cost_overrides=cost_overrides,
            worker_names=worker_names,
            derived_channel_name=derived_channel_name,
        )

    # --------------------------------------------------------------- private

    def _run_with_rollback(
        self,
        *,
        template: Template,
        team_name: str,
        manager_id: str,
        parent_team_name: Optional[str],
        size_overrides: dict[str, int],
        cost_overrides: dict[str, int],
        worker_names: dict[str, list[str]],
        derived_channel_name: Optional[str],
    ) -> HireTeamResult:
        rollback_stack: list[Callable[[], None]] = []
        worker_ids: list[str] = []
        okr_ids: list[str] = []
        team_id: Optional[str] = None
        channel_id: Optional[str] = None
        team_manager_worker_id: Optional[str] = None

        try:
            # 7. Create team.
            parent_team_id = self._lookup_team_id(parent_team_name) if parent_team_name else None
            team = create_team(
                self.db,
                name=team_name,
                parent_team_id=parent_team_id,
                lead_id=None,
                auto_create_channel=False,
            )
            team_id = team.id
            rollback_stack.append(lambda tid=team_id: self.db.execute("DELETE FROM teams WHERE id = ?", (tid,)))

            # 8. Create channel.
            if derived_channel_name:
                channel = create_channel(
                    self.db,
                    name=derived_channel_name,
                    channel_type="team",
                    team_id=team_id,
                )
                channel_id = channel.id
                rollback_stack.append(
                    lambda cid=channel_id: self.db.execute("DELETE FROM channels WHERE id = ?", (cid,))
                )
                self.db.execute(
                    "UPDATE teams SET channel_id = ? WHERE id = ?", (channel_id, team_id)
                )
                self.db.connection.commit()

            # 9. Hire members (manager first per iabn §D step 9).
            expanded = self._expand_members(template, size_overrides)
            ordered = sorted(expanded, key=lambda m: 0 if m.is_manager else 1)
            for member in ordered:
                effective_cost = cost_overrides.get(member.role, member.cost)
                names_for_role = worker_names.get(member.role, [])
                for i in range(member.count):
                    worker_name = (
                        names_for_role[i]
                        if i < len(names_for_role)
                        else f"{member.role}-{team_name}-{i + 1}"
                    )
                    new_worker = _helpers.hire_worker(
                        self.db,
                        self.ctx,
                        name=worker_name,
                        role=member.role,
                        manager_id=manager_id,
                        cost=effective_cost,
                    )
                    worker_id = self._extract_id(new_worker)
                    worker_ids.append(worker_id)
                    rollback_stack.append(
                        lambda wid=worker_id: self._rollback_worker(wid)
                    )
                    # team_members.role is membership type ("member" | "lead" | "admin"),
                    # NOT the worker's role identity (engineer, pm, etc.).
                    membership_role = "lead" if member.is_manager else "member"
                    add_team_member(self.db, team_id, worker_id, membership_role)
                    if member.is_manager:
                        team_manager_worker_id = worker_id

            # 10. Update team's lead_id to the in-template manager.
            if team_manager_worker_id is not None:
                self.db.execute(
                    "UPDATE teams SET lead_id = ? WHERE id = ?",
                    (team_manager_worker_id, team_id),
                )
                self.db.connection.commit()

            # 11. Subscribe channel members (best-effort; no-op if subscription
            # mechanism isn't backed by tables in this org schema).
            self._subscribe_channel_members(channel_id, [manager_id] + worker_ids)

            # 12. File initial OKRs.
            for okr_spec in template.initial_okrs:
                substituted_title = okr_spec.title.format(team_name=team_name, ttl_hours=template.ttl_hours)
                substituted_desc = okr_spec.description.format(team_name=team_name, ttl_hours=template.ttl_hours)
                okr_id = _helpers.create_okr(
                    self.db,
                    self.ctx,
                    title=substituted_title,
                    description=substituted_desc,
                    owner_id=team_manager_worker_id or manager_id,
                    key_results=okr_spec.key_results,
                )
                okr_ids.append(okr_id)
                rollback_stack.append(
                    lambda oid=okr_id: _helpers.close_okr(
                        self.db, self.ctx, okr_id=oid, status="cancelled", reason="hire-team rollback"
                    )
                )

            # 13. Set template_type, ttl_hours, ttl_started_at.
            now = datetime.now(timezone.utc)
            ttl_started_at = now.isoformat() if template.ttl_hours else None
            self.db.execute(
                """UPDATE teams SET template_type = ?, ttl_hours = ?, ttl_started_at = ?
                   WHERE id = ?""",
                (template.name, template.ttl_hours, ttl_started_at, team_id),
            )

            # 14. Commit.
            self.db.connection.commit()
            return HireTeamResult(
                team_id=team_id,
                channel_id=channel_id,
                worker_ids=tuple(worker_ids),
                okr_ids=tuple(okr_ids),
                rolled_back=False,
            )

        except Exception as orig_exc:
            _logger.warning("hire_team failed: %s; running rollback", orig_exc)
            rollback_errors: list[Exception] = []
            for fn in reversed(rollback_stack):
                try:
                    fn()
                except Exception as re:
                    rollback_errors.append(re)
            try:
                self.db.connection.commit()
            except Exception as ce:
                rollback_errors.append(ce)

            if rollback_errors:
                raise HireTeamRollbackFailed(
                    original=orig_exc, rollback_errors=rollback_errors
                ) from orig_exc

            return HireTeamResult(
                team_id=team_id or "",
                channel_id=channel_id,
                worker_ids=tuple(worker_ids),
                okr_ids=tuple(okr_ids),
                rolled_back=True,
                failure_reason=str(orig_exc),
            )

    # ----------------------------------------------------------- helpers

    @staticmethod
    def _derive_channel_name(template: Template, team_name: str) -> Optional[str]:
        if template.channel is None or not template.channel.auto_create:
            return None
        return template.channel.name_template.format(team_name=team_name)

    def _channel_exists(self, name: str) -> bool:
        row = self.db.fetchone("SELECT 1 FROM channels WHERE name = ?", (name,))
        return row is not None

    def _lookup_team_id(self, team_name: str) -> Optional[str]:
        row = self.db.fetchone("SELECT id FROM teams WHERE name = ?", (team_name,))
        return row["id"] if row else None

    @staticmethod
    def _expand_members(
        template: Template, size_overrides: dict[str, int]
    ) -> list[TemplateMember]:
        expanded: list[TemplateMember] = []
        for m in template.members:
            new_count = size_overrides.get(m.role, m.count)
            expanded.append(
                TemplateMember(
                    role=m.role, count=new_count, cost=m.cost, is_manager=m.is_manager
                )
            )
        return expanded

    @staticmethod
    def _extract_id(worker_obj: Any) -> str:
        # Worker dataclass has .id; tests' fakes may return MagicMock-like objects.
        if hasattr(worker_obj, "id"):
            return worker_obj.id
        if isinstance(worker_obj, dict):
            return worker_obj["id"]
        return str(worker_obj)

    def _rollback_worker(self, worker_id: str) -> None:
        """Roll back a single worker created by this hire-team.

        Calls _helpers.fire_worker for the business-level signal (audit, hooks,
        etc.) AND directly deletes the row + team_members rows for transactional
        cleanup. The two layers are independent: fakes can stub fire_worker
        without losing the cleanup guarantee.
        """
        try:
            _helpers.fire_worker(
                self.db, self.ctx, worker_id=worker_id, reason="hire-team rollback"
            )
        except Exception as exc:
            _logger.debug("fire_worker raised during rollback (continuing): %s", exc)
        self.db.execute("DELETE FROM team_members WHERE worker_id = ?", (worker_id,))
        self.db.execute("DELETE FROM workers WHERE id = ?", (worker_id,))

    def _subscribe_channel_members(self, channel_id: Optional[str], worker_ids: list[str]) -> None:
        if channel_id is None or not worker_ids:
            return
        # Subscribe via channel_subscriptions table if it exists; best-effort.
        try:
            for wid in worker_ids:
                self.db.execute(
                    """INSERT OR IGNORE INTO channel_subscriptions (channel_id, worker_id)
                       VALUES (?, ?)""",
                    (channel_id, wid),
                )
            self.db.connection.commit()
        except Exception as exc:
            _logger.debug("channel subscription skipped: %s", exc)
