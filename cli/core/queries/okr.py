"""OKR (Objectives and Key Results) queries."""

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from ..db import Database
from .common import generate_id, parse_date, get_row_value

@dataclass
class KeyResult:
    """A single measurable key result."""
    metric: str  # e.g., "lighthouse_score", "test_coverage"
    target: float  # target value
    current: float  # current value
    unit: str  # e.g., "%", "count", "seconds"

    def progress(self) -> float:
        """Calculate progress as percentage (0-100)."""
        if self.target == 0:
            return 100.0 if self.current >= 0 else 0.0
        return min(100.0, (self.current / self.target) * 100)

    def is_met(self) -> bool:
        """Check if target is met."""
        return self.current >= self.target


@dataclass
class OKR:
    """Objective and Key Result definition."""
    id: str
    title: str
    description: Optional[str]
    owner_worker_id: str
    parent_okr_id: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime
    key_results: list[KeyResult] = field(default_factory=list)
    due_date: Optional[date] = None

    def progress(self) -> float:
        """Calculate overall progress across all key results."""
        if not self.key_results:
            return 0.0
        return sum(kr.progress() for kr in self.key_results) / len(self.key_results)

    def all_key_results_met(self) -> bool:
        """Check if all key results are met."""
        return all(kr.is_met() for kr in self.key_results) if self.key_results else False


@dataclass
class WorkOKRLink:
    """Link between a work item and an OKR."""
    work_id: str
    okr_id: str
    link_type: str
    created_at: datetime



def create_okr(
    db: Database,
    title: str,
    owner_id: str,
    parent_id: Optional[str] = None,
    description: Optional[str] = None,
    status: str = "active",
    okr_id: Optional[str] = None,
    key_results: Optional[list[KeyResult]] = None,
    due_date: Optional[date] = None,
) -> OKR:
    """Create a new OKR.

    OKRs cascade: Board -> CEO -> Directors -> Managers -> Workers.
    Each OKR can have a parent OKR to form the hierarchy.

    Args:
        db: Database instance
        title: OKR title
        owner_id: Worker ID who owns this OKR
        parent_id: Optional parent OKR ID for cascade
        description: Optional description
        status: OKR status ('draft', 'active', 'completed', 'cancelled')
        okr_id: Optional custom ID (generated if not provided)
        key_results: Optional list of measurable key results
        due_date: Optional due date for the OKR

    Returns:
        Created OKR
    """
    if okr_id is None:
        okr_id = generate_id("okr")

    now = datetime.now()
    kr_json = None
    if key_results:
        kr_json = json.dumps([
            {"metric": kr.metric, "target": kr.target, "current": kr.current, "unit": kr.unit}
            for kr in key_results
        ])

    db.execute(
        """INSERT INTO okrs
           (id, title, description, owner_worker_id, parent_okr_id, status, key_results, due_date, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (okr_id, title, description, owner_id, parent_id, status, kr_json, due_date, now, now)
    )
    db.connection.commit()

    return OKR(
        id=okr_id,
        title=title,
        description=description,
        owner_worker_id=owner_id,
        parent_okr_id=parent_id,
        status=status,
        created_at=now,
        updated_at=now,
        key_results=key_results or [],
        due_date=due_date,
    )


def _parse_key_results(kr_json: Optional[str]) -> list[KeyResult]:
    """Parse key results from JSON string."""
    if not kr_json:
        return []
    try:
        data = json.loads(kr_json)
        return [
            KeyResult(
                metric=kr["metric"],
                target=kr["target"],
                current=kr.get("current", 0),
                unit=kr.get("unit", "count"),
            )
            for kr in data
        ]
    except (json.JSONDecodeError, KeyError):
        return []


def _parse_date(date_str: Optional[str]) -> Optional[date]:
    """Parse date from string."""
    if not date_str:
        return None
    try:
        return date.fromisoformat(date_str) if isinstance(date_str, str) else date_str
    except ValueError:
        return None


def _get_row_value(row: dict, key: str, default=None):
    """Safely get value from sqlite3.Row or dict."""
    try:
        return row[key]
    except (KeyError, IndexError):
        return default


def get_okr(db: Database, okr_id: str) -> Optional[OKR]:
    """Get an OKR by ID.

    Args:
        db: Database instance
        okr_id: OKR ID

    Returns:
        OKR or None
    """
    row = db.fetchone("SELECT * FROM okrs WHERE id = ?", (okr_id,))
    if not row:
        return None

    return OKR(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        owner_worker_id=row["owner_worker_id"],
        parent_okr_id=row["parent_okr_id"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        key_results=_parse_key_results(_get_row_value(row, "key_results")),
        due_date=_parse_date(_get_row_value(row, "due_date")),
    )


def update_okr_status(db: Database, okr_id: str, status: str) -> None:
    """Update OKR status.

    Args:
        db: Database instance
        okr_id: OKR ID
        status: New status ('draft', 'active', 'completed', 'cancelled')
    """
    now = datetime.now()
    db.execute(
        "UPDATE okrs SET status = ?, updated_at = ? WHERE id = ?",
        (status, now, okr_id)
    )
    db.connection.commit()


def get_okrs_by_owner(db: Database, owner_id: str) -> list[OKR]:
    """Get all OKRs owned by a worker.

    Args:
        db: Database instance
        owner_id: Worker ID

    Returns:
        List of OKRs owned by the worker
    """
    rows = db.fetchall(
        "SELECT * FROM okrs WHERE owner_worker_id = ? ORDER BY created_at DESC",
        (owner_id,)
    )
    return [
        OKR(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            owner_worker_id=row["owner_worker_id"],
            parent_okr_id=row["parent_okr_id"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            key_results=_parse_key_results(_get_row_value(row, "key_results")),
            due_date=_parse_date(_get_row_value(row, "due_date")),
        )
        for row in rows
    ]


def list_okrs(
    db: Database,
    status: Optional[str] = None,
    owner_id: Optional[str] = None,
    include_closed: bool = False,
) -> list[OKR]:
    """List all OKRs with optional filtering.

    Args:
        db: Database instance
        status: Optional status filter ('draft', 'active', 'completed', 'cancelled')
        owner_id: Optional owner worker ID filter
        include_closed: If True, include completed/cancelled OKRs

    Returns:
        List of OKRs
    """
    query = "SELECT * FROM okrs WHERE 1=1"
    params: list = []

    if status:
        query += " AND status = ?"
        params.append(status)
    elif not include_closed:
        # Default: exclude closed statuses
        query += " AND status NOT IN ('completed', 'cancelled')"

    if owner_id:
        query += " AND owner_worker_id = ?"
        params.append(owner_id)

    query += " ORDER BY created_at DESC"

    rows = db.fetchall(query, tuple(params))
    return [
        OKR(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            owner_worker_id=row["owner_worker_id"],
            parent_okr_id=row["parent_okr_id"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            key_results=_parse_key_results(_get_row_value(row, "key_results")),
            due_date=_parse_date(_get_row_value(row, "due_date")),
        )
        for row in rows
    ]


def get_child_okrs(db: Database, parent_id: str) -> list[OKR]:
    """Get OKRs that have the given OKR as their parent.

    Args:
        db: Database instance
        parent_id: Parent OKR ID

    Returns:
        List of child OKRs
    """
    rows = db.fetchall(
        "SELECT * FROM okrs WHERE parent_okr_id = ? ORDER BY created_at",
        (parent_id,)
    )
    return [
        OKR(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            owner_worker_id=row["owner_worker_id"],
            parent_okr_id=row["parent_okr_id"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            key_results=_parse_key_results(_get_row_value(row, "key_results")),
            due_date=_parse_date(_get_row_value(row, "due_date")),
        )
        for row in rows
    ]


def update_okr_key_result(
    db: Database,
    okr_id: str,
    metric: str,
    current: float,
) -> Optional[OKR]:
    """Update a key result's current value.

    Args:
        db: Database instance
        okr_id: OKR ID
        metric: Key result metric name to update
        current: New current value

    Returns:
        Updated OKR, or None if not found or metric doesn't exist
    """
    okr = get_okr(db, okr_id)
    if not okr:
        return None

    # Find and update the key result
    updated = False
    for kr in okr.key_results:
        if kr.metric == metric:
            kr.current = current
            updated = True
            break

    if not updated:
        return None

    # Save back to database
    kr_json = json.dumps([
        {"metric": kr.metric, "target": kr.target, "current": kr.current, "unit": kr.unit}
        for kr in okr.key_results
    ])
    now = datetime.now()
    db.execute(
        "UPDATE okrs SET key_results = ?, updated_at = ? WHERE id = ?",
        (kr_json, now, okr_id)
    )
    db.connection.commit()

    okr.updated_at = now
    return okr


def add_okr_key_result(
    db: Database,
    okr_id: str,
    metric: str,
    target: float,
    unit: str,
    current: float = 0.0,
) -> Optional[OKR]:
    """Add a new key result to an OKR.

    Args:
        db: Database instance
        okr_id: OKR ID
        metric: Key result metric name
        target: Target value
        unit: Unit of measurement
        current: Initial current value (default 0)

    Returns:
        Updated OKR, or None if OKR not found
    """
    okr = get_okr(db, okr_id)
    if not okr:
        return None

    # Check if metric already exists
    for kr in okr.key_results:
        if kr.metric == metric:
            return None  # Duplicate metric

    # Add new key result
    okr.key_results.append(KeyResult(metric=metric, target=target, current=current, unit=unit))

    # Save back to database
    kr_json = json.dumps([
        {"metric": kr.metric, "target": kr.target, "current": kr.current, "unit": kr.unit}
        for kr in okr.key_results
    ])
    now = datetime.now()
    db.execute(
        "UPDATE okrs SET key_results = ?, updated_at = ? WHERE id = ?",
        (kr_json, now, okr_id)
    )
    db.connection.commit()

    okr.updated_at = now
    return okr


@dataclass
class OKRTreeNode:
    """Node in an OKR hierarchy tree."""
    okr: OKR
    children: list["OKRTreeNode"]


def get_okr_hierarchy(db: Database, root_okr_id: str) -> Optional[OKRTreeNode]:
    """Get the full OKR hierarchy starting from a root OKR.

    Recursively builds the tree of OKRs cascading down from the root.

    Args:
        db: Database instance
        root_okr_id: The root OKR ID to start from

    Returns:
        OKRTreeNode representing the hierarchy, or None if root not found
    """
    root = get_okr(db, root_okr_id)
    if not root:
        return None

    def build_tree(okr: OKR) -> OKRTreeNode:
        children = get_child_okrs(db, okr.id)
        return OKRTreeNode(
            okr=okr,
            children=[build_tree(child) for child in children],
        )

    return build_tree(root)


def get_okr_ancestors(db: Database, okr_id: str) -> list[OKR]:
    """Get all ancestor OKRs (parent, grandparent, etc.) up to the root.

    Args:
        db: Database instance
        okr_id: OKR ID to start from

    Returns:
        List of ancestor OKRs, from immediate parent to root
    """
    ancestors = []
    current_okr = get_okr(db, okr_id)

    while current_okr and current_okr.parent_okr_id:
        parent = get_okr(db, current_okr.parent_okr_id)
        if parent:
            ancestors.append(parent)
            current_okr = parent
        else:
            break

    return ancestors



def link_work_to_okr(
    db: Database,
    work_id: str,
    okr_id: str,
    link_type: str = "contributes",
) -> WorkOKRLink:
    """Link a work item to an OKR.

    Every work item should link to an objective for strategic alignment.

    Args:
        db: Database instance
        work_id: Work item ID (e.g., bead ID)
        okr_id: OKR ID to link to
        link_type: Type of link ('contributes', 'blocks', 'depends_on')

    Returns:
        Created WorkOKRLink
    """
    now = datetime.now()
    db.execute(
        """INSERT OR REPLACE INTO work_okr_links
           (work_id, okr_id, link_type, created_at)
           VALUES (?, ?, ?, ?)""",
        (work_id, okr_id, link_type, now)
    )
    db.connection.commit()

    return WorkOKRLink(
        work_id=work_id,
        okr_id=okr_id,
        link_type=link_type,
        created_at=now,
    )


def unlink_work_from_okr(db: Database, work_id: str, okr_id: str) -> bool:
    """Remove link between work item and OKR.

    Args:
        db: Database instance
        work_id: Work item ID
        okr_id: OKR ID

    Returns:
        True if link was removed, False if not found
    """
    cursor = db.execute(
        "DELETE FROM work_okr_links WHERE work_id = ? AND okr_id = ?",
        (work_id, okr_id)
    )
    db.connection.commit()
    return cursor.rowcount > 0


def get_work_okr_link(
    db: Database,
    work_id: str,
    okr_id: str,
) -> Optional[WorkOKRLink]:
    """Get a specific work-OKR link.

    Args:
        db: Database instance
        work_id: Work item ID
        okr_id: OKR ID

    Returns:
        WorkOKRLink or None
    """
    row = db.fetchone(
        "SELECT * FROM work_okr_links WHERE work_id = ? AND okr_id = ?",
        (work_id, okr_id)
    )
    if not row:
        return None

    return WorkOKRLink(
        work_id=row["work_id"],
        okr_id=row["okr_id"],
        link_type=row["link_type"],
        created_at=row["created_at"],
    )


def get_work_for_okr(db: Database, okr_id: str) -> list[WorkOKRLink]:
    """Get all work items linked to an OKR.

    Args:
        db: Database instance
        okr_id: OKR ID

    Returns:
        List of WorkOKRLink records
    """
    rows = db.fetchall(
        "SELECT * FROM work_okr_links WHERE okr_id = ? ORDER BY created_at",
        (okr_id,)
    )
    return [
        WorkOKRLink(
            work_id=row["work_id"],
            okr_id=row["okr_id"],
            link_type=row["link_type"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def get_okrs_for_work(db: Database, work_id: str) -> list[WorkOKRLink]:
    """Get all OKRs linked to a work item.

    Args:
        db: Database instance
        work_id: Work item ID

    Returns:
        List of WorkOKRLink records
    """
    rows = db.fetchall(
        "SELECT * FROM work_okr_links WHERE work_id = ? ORDER BY created_at",
        (work_id,)
    )
    return [
        WorkOKRLink(
            work_id=row["work_id"],
            okr_id=row["okr_id"],
            link_type=row["link_type"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def get_work_for_okr_hierarchy(db: Database, root_okr_id: str) -> list[WorkOKRLink]:
    """Get all work items linked to an OKR and all its descendants.

    This is useful for seeing all work contributing to a high-level objective.

    Args:
        db: Database instance
        root_okr_id: Root OKR ID

    Returns:
        List of all WorkOKRLink records for the hierarchy
    """
    all_links = []

    def collect_links(okr_id: str) -> None:
        # Get links for this OKR
        links = get_work_for_okr(db, okr_id)
        all_links.extend(links)

        # Recurse into children
        children = get_child_okrs(db, okr_id)
        for child in children:
            collect_links(child.id)

    collect_links(root_okr_id)
    return all_links

__all__ = [
    "KeyResult",
    "OKR",
    "OKRTreeNode",
    "WorkOKRLink",
    "_get_row_value",
    "_parse_date",
    "_parse_key_results",
    "add_okr_key_result",
    "all_key_results_met",
    "build_tree",
    "collect_links",
    "create_okr",
    "get_child_okrs",
    "get_okr",
    "get_okr_ancestors",
    "get_okr_hierarchy",
    "get_okrs_by_owner",
    "get_okrs_for_work",
    "get_work_for_okr",
    "get_work_for_okr_hierarchy",
    "get_work_okr_link",
    "is_met",
    "link_work_to_okr",
    "list_okrs",
    "progress",
    "progress",
    "unlink_work_from_okr",
    "update_okr_key_result",
    "update_okr_status",
]
