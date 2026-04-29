"""Audit logger for the board-rules engine.

Per quinn-ai-t2zb §E + zm8a §7: synchronous append, one JSONL line per evaluation,
including no-match cases. No batching. File rotation is operator-managed.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cli.core.rules.types import DecisionKind


class AuditLogger:
    """Append-only JSONL writer for rule-evaluation audit records."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        *,
        worker_id: str | None,
        action: str,
        rule_id: str | None,
        decision: DecisionKind,
        justify_bead: str | None = None,
        override_bead: str | None = None,
        context_summary: dict[str, Any] | None = None,
        kill_switch_used: bool = False,
    ) -> None:
        """Write one JSONL audit record. Synchronous; no batching."""
        record_dict = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "worker_id": worker_id,
            "action": action,
            "rule_id": rule_id,
            "decision": decision.value if isinstance(decision, DecisionKind) else decision,
            "justify_bead": justify_bead,
            "override_bead": override_bead,
            "context_summary": context_summary or {},
            "kill_switch_used": kill_switch_used,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record_dict) + "\n")
