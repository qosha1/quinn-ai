"""Read OKRs and the CEO briefing file."""

import json
from pathlib import Path
from typing import Any, Optional

# Imported lazily inside _fetch_beads_okrs to keep the import graph
# cheap and to make the reference patchable from tests.
try:  # pragma: no cover — exercised via patch in tests
    from cli.core.bd_wrapper import run_bd  # type: ignore
except Exception:  # pragma: no cover — defensive: keep panel usable
    run_bd = None  # type: ignore[assignment]

from ...interfaces.org_connection import OKRInfo
from ...logging_config import get_board_logger
from ._helpers import parse_datetime

logger = get_board_logger(__name__)


# Time budget for the bd-fallback query (seconds). Keep small — the panel
# has to stay responsive on init.
_BD_OKR_FALLBACK_TIMEOUT = 5.0


class OKRReader:
    """Read OKRs (with their key results) and the CEO briefing file.

    OKRs are stored canonically in beads (as epics with the 'okr' label).
    The SQLite `okrs` table is a denormalized mirror that adds key-result
    progress data. For dolt-mode orgs, the mirror is often empty even
    when bd has live OKRs (see quinn-ai-176s, quinn-ai-k9ff). When the
    mirror is missing rows, we merge in bd-side OKR metadata so the
    panel still renders something useful.
    """

    def __init__(self, db: Any, org_path: Path) -> None:
        self._db = db
        self._org_path = org_path

    def get_okrs(self, owner_id: Optional[str] = None) -> list[OKRInfo]:
        """Get OKRs, optionally filtered by owner.

        Strategy:
        1. Read all rows from the SQLite mirror (LEFT JOIN workers so
           orgs with FK-orphan owner ids still surface their rows).
        2. Query bd for OKR-labeled epics. For each bd OKR not present
           in the mirror, synthesize an OKRInfo from bd metadata.
        3. Optionally filter by owner_id.
        """
        rows = self._db.fetchall(
            """SELECT o.*, w.name as owner_name
               FROM okrs o
               LEFT JOIN workers w ON o.owner_worker_id = w.id
               ORDER BY o.parent_okr_id NULLS FIRST, o.created_at"""
        )

        mirror_okrs: dict[str, OKRInfo] = {}
        for row in rows:
            okr = OKRInfo(
                id=row["id"],
                title=row["title"],
                description=row["description"],
                owner_name=row["owner_name"] or row["owner_worker_id"] or "",
                owner_id=row["owner_worker_id"] or "",
                status=row["status"],
                parent_id=row["parent_okr_id"],
                key_results=self._parse_key_results(row["key_results"]),
                due_date=parse_datetime(row["due_date"]),
                children_count=self._count_child_okrs(row["id"]),
            )
            mirror_okrs[okr.id] = okr

        # Layer in bd-only OKRs for dolt-mode orgs whose mirror is stale.
        beads_okrs = self._fetch_beads_okrs()
        for beads_okr in beads_okrs:
            okr_id = beads_okr.get("id")
            if not okr_id or okr_id in mirror_okrs:
                continue  # mirror wins when present
            mirror_okrs[okr_id] = self._beads_okr_to_info(beads_okr)

        result = list(mirror_okrs.values())
        if owner_id:
            result = [o for o in result if o.owner_id == owner_id]
        return result

    def _fetch_beads_okrs(self) -> list[dict[str, Any]]:
        """Query bd for OKR-labeled epics. Returns [] on any error.

        We swallow errors aggressively — bd unavailability must not break
        the panel. The SQLite mirror is the primary source; bd is a
        best-effort fallback.
        """
        if run_bd is None:
            return []
        try:
            result = run_bd(
                ["list", "--label=okr", "--all", "--json"],
                org_path=self._org_path,
                capture_output=True,
                skip_permission_check=True,
                skip_lifecycle_check=True,
                skip_okr_check=True,
                timeout=_BD_OKR_FALLBACK_TIMEOUT,
            )
        except Exception as e:  # subprocess timeout, missing bd, etc.
            logger.debug(f"bd OKR fallback failed (non-fatal): {e}")
            return []

        if result.returncode != 0:
            logger.debug(
                f"bd OKR fallback returned {result.returncode}: "
                f"{(result.stderr or '').strip()[:200]}"
            )
            return []

        stdout = (result.stdout or "").strip()
        if not stdout:
            return []
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            logger.debug("bd OKR fallback returned non-JSON output")
            return []
        return data if isinstance(data, list) else []

    def _beads_okr_to_info(self, beads_okr: dict[str, Any]) -> OKRInfo:
        """Build OKRInfo from a beads `bd list --json` row.

        Bd doesn't carry key-result data — that's mirror-only. Dates
        translate as best-effort; status comes through verbatim.
        """
        owner_id = beads_okr.get("assignee") or ""
        owner_name = self._resolve_worker_name(owner_id) if owner_id else ""

        return OKRInfo(
            id=beads_okr.get("id", ""),
            title=beads_okr.get("title") or "(untitled)",
            description=beads_okr.get("description") or "",
            owner_name=owner_name or owner_id,
            owner_id=owner_id,
            status=beads_okr.get("status", "open"),
            parent_id=None,
            key_results=[],
            due_date=parse_datetime(beads_okr.get("due_date")),
            children_count=0,
        )

    def _resolve_worker_name(self, worker_id: str) -> Optional[str]:
        """Look up a worker's display name from the SQLite workers table."""
        if not worker_id:
            return None
        row = self._db.fetchone(
            "SELECT name FROM workers WHERE id = ?", (worker_id,)
        )
        return row["name"] if row else None

    def get_current_briefing(self) -> Optional[str]:
        """Get current CEO briefing from config file."""
        briefing_path = self._org_path / "config" / "ceo_briefing.md"
        if briefing_path.exists():
            return briefing_path.read_text()
        return None

    def _parse_key_results(self, kr_json: Optional[str]) -> list[dict[str, Any]]:
        if not kr_json:
            return []
        try:
            return json.loads(kr_json)
        except (json.JSONDecodeError, TypeError):
            return []

    def _count_child_okrs(self, okr_id: str) -> int:
        row = self._db.fetchone(
            "SELECT COUNT(*) as count FROM okrs WHERE parent_okr_id = ?",
            (okr_id,),
        )
        return row["count"] if row else 0
