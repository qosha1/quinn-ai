"""Team and team membership queries."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from ..db import Database
from .common import generate_id

if TYPE_CHECKING:
    from .channel import Channel


@dataclass
class Team:
    """Team definition."""
    id: str
    name: str
    parent_team_id: Optional[str]
    lead_id: Optional[str]
    channel_id: Optional[str]
    created_at: datetime


@dataclass
class TeamMember:
    """Team membership record."""
    team_id: str
    worker_id: str
    role: str
    joined_at: datetime


def create_team(
    db: Database,
    name: str,
    parent_team_id: Optional[str] = None,
    lead_id: Optional[str] = None,
    team_id: Optional[str] = None,
    auto_create_channel: bool = True,
) -> Team:
    """Create a new team.

    Args:
        db: Database instance
        name: Team name
        parent_team_id: Optional parent team for hierarchy
        lead_id: Optional team lead worker ID
        team_id: Optional custom ID (generated if not provided)
        auto_create_channel: Create a team channel automatically (default True)

    Returns:
        Created Team
    """
    # Import here to avoid circular dependency
    from .channel import create_channel

    if team_id is None:
        team_id = generate_id("team")

    now = datetime.now()
    channel_id = None

    # Create the team first (before channel, due to foreign key constraint)
    db.execute(
        """INSERT INTO teams (id, name, parent_team_id, lead_id, channel_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (team_id, name, parent_team_id, lead_id, None, now)
    )
    db.connection.commit()

    # Then create a channel for the team and update the team
    if auto_create_channel:
        channel_name = name.lower().replace(" ", "-")
        channel = create_channel(
            db,
            name=channel_name,
            channel_type="team",
            team_id=team_id,
        )
        channel_id = channel.id
        # Update team with channel_id
        db.execute(
            "UPDATE teams SET channel_id = ? WHERE id = ?",
            (channel_id, team_id)
        )
        db.connection.commit()

    return Team(
        id=team_id,
        name=name,
        parent_team_id=parent_team_id,
        lead_id=lead_id,
        channel_id=channel_id,
        created_at=now,
    )


def get_team(db: Database, team_id: str) -> Optional[Team]:
    """Get a team by ID.

    Args:
        db: Database instance
        team_id: Team ID

    Returns:
        Team or None
    """
    row = db.fetchone("SELECT * FROM teams WHERE id = ?", (team_id,))
    if not row:
        return None

    return Team(
        id=row["id"],
        name=row["name"],
        parent_team_id=row["parent_team_id"],
        lead_id=row["lead_id"],
        channel_id=row["channel_id"],
        created_at=row["created_at"],
    )


def get_team_channel(db: Database, team_id: str) -> Optional["Channel"]:
    """Get the channel for a team.

    Args:
        db: Database instance
        team_id: Team ID

    Returns:
        Channel or None if no channel exists for team
    """
    from .channel import Channel

    row = db.fetchone(
        "SELECT * FROM channels WHERE team_id = ? AND type = 'team'",
        (team_id,)
    )
    if not row:
        return None

    return Channel(
        id=row["id"],
        name=row["name"],
        type=row["type"],
        team_id=row["team_id"],
        created_at=row["created_at"],
    )


def get_team_children(db: Database, team_id: str) -> list[Team]:
    """Get child teams of a team.

    Args:
        db: Database instance
        team_id: Parent team ID

    Returns:
        List of child teams
    """
    rows = db.fetchall(
        "SELECT * FROM teams WHERE parent_team_id = ?",
        (team_id,)
    )
    return [
        Team(
            id=row["id"],
            name=row["name"],
            parent_team_id=row["parent_team_id"],
            lead_id=row["lead_id"],
            channel_id=row["channel_id"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def get_all_teams(db: Database) -> list[Team]:
    """Get all teams.

    Args:
        db: Database instance

    Returns:
        List of all teams
    """
    rows = db.fetchall("SELECT * FROM teams ORDER BY created_at")
    return [
        Team(
            id=row["id"],
            name=row["name"],
            parent_team_id=row["parent_team_id"],
            lead_id=row["lead_id"],
            channel_id=row["channel_id"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def add_team_member(
    db: Database,
    team_id: str,
    worker_id: str,
    role: str = "member",
) -> TeamMember:
    """Add a worker to a team with a role.

    Args:
        db: Database instance
        team_id: Team ID
        worker_id: Worker ID
        role: Role in team ('member', 'lead', 'admin')

    Returns:
        Created TeamMember
    """
    now = datetime.now()
    db.execute(
        "INSERT INTO team_members (team_id, worker_id, role, joined_at) VALUES (?, ?, ?, ?)",
        (team_id, worker_id, role, now)
    )
    db.connection.commit()

    return TeamMember(
        team_id=team_id,
        worker_id=worker_id,
        role=role,
        joined_at=now,
    )


def get_team_member(db: Database, team_id: str, worker_id: str) -> Optional[TeamMember]:
    """Get a team membership record.

    Args:
        db: Database instance
        team_id: Team ID
        worker_id: Worker ID

    Returns:
        TeamMember or None
    """
    row = db.fetchone(
        "SELECT * FROM team_members WHERE team_id = ? AND worker_id = ?",
        (team_id, worker_id)
    )
    if not row:
        return None

    return TeamMember(
        team_id=row["team_id"],
        worker_id=row["worker_id"],
        role=row["role"],
        joined_at=row["joined_at"],
    )


def update_team_member_role(db: Database, team_id: str, worker_id: str, role: str) -> None:
    """Update a worker's role in a team.

    Args:
        db: Database instance
        team_id: Team ID
        worker_id: Worker ID
        role: New role
    """
    db.execute(
        "UPDATE team_members SET role = ? WHERE team_id = ? AND worker_id = ?",
        (role, team_id, worker_id)
    )
    db.connection.commit()


def remove_team_member(db: Database, team_id: str, worker_id: str) -> bool:
    """Remove a worker from a team.

    Args:
        db: Database instance
        team_id: Team ID
        worker_id: Worker ID

    Returns:
        True if removed, False if not found
    """
    cursor = db.execute(
        "DELETE FROM team_members WHERE team_id = ? AND worker_id = ?",
        (team_id, worker_id)
    )
    db.connection.commit()
    return cursor.rowcount > 0


def get_team_members_list(db: Database, team_id: str) -> list[TeamMember]:
    """Get all members of a team.

    Args:
        db: Database instance
        team_id: Team ID

    Returns:
        List of TeamMember records
    """
    rows = db.fetchall(
        "SELECT * FROM team_members WHERE team_id = ?",
        (team_id,)
    )
    return [
        TeamMember(
            team_id=row["team_id"],
            worker_id=row["worker_id"],
            role=row["role"],
            joined_at=row["joined_at"],
        )
        for row in rows
    ]


def get_worker_team_memberships(db: Database, worker_id: str) -> list[TeamMember]:
    """Get all team memberships for a worker.

    Args:
        db: Database instance
        worker_id: Worker ID

    Returns:
        List of TeamMember records
    """
    rows = db.fetchall(
        "SELECT * FROM team_members WHERE worker_id = ?",
        (worker_id,)
    )
    return [
        TeamMember(
            team_id=row["team_id"],
            worker_id=row["worker_id"],
            role=row["role"],
            joined_at=row["joined_at"],
        )
        for row in rows
    ]


def get_team_members_by_role(db: Database, team_id: str, role: str) -> list[TeamMember]:
    """Get team members with a specific role.

    Args:
        db: Database instance
        team_id: Team ID
        role: Role to filter by

    Returns:
        List of TeamMember records
    """
    rows = db.fetchall(
        "SELECT * FROM team_members WHERE team_id = ? AND role = ?",
        (team_id, role)
    )
    return [
        TeamMember(
            team_id=row["team_id"],
            worker_id=row["worker_id"],
            role=row["role"],
            joined_at=row["joined_at"],
        )
        for row in rows
    ]


__all__ = [
    "Team",
    "TeamMember",
    "create_team",
    "get_team",
    "get_team_channel",
    "get_team_children",
    "get_all_teams",
    "add_team_member",
    "get_team_member",
    "update_team_member_role",
    "remove_team_member",
    "get_team_members_list",
    "get_worker_team_memberships",
    "get_team_members_by_role",
]
