"""Shared context object passed to every commander.

Bundles the database handle, org path, channel names, and the four
reader-side callbacks the commanders need to consult before mutating.
Replaces the 4-callable kwarg smell that OrgCommander used to carry.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from ...interfaces.org_connection import OrgInfo, WorkerInfo


@dataclass
class OrgContext:
    db: Any
    org_path: Path
    board_channel: str
    escalations_channel: str
    get_ceo: Callable[[], Optional[WorkerInfo]]
    get_board_channel_id: Callable[[], Optional[str]]
    get_org_info: Callable[[], OrgInfo]
    mark_message_read: Callable[[str], bool]
