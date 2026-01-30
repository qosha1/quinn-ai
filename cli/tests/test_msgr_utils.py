"""Tests for msgr utility functions."""

import pytest
from pathlib import Path
import tempfile

from core.db import init_database
from core.queries.worker import create_worker
from core.queries.channel import create_channel, subscribe_to_channel
from msgr.utils import (
    ChannelResolutionError,
    resolve_channel,
    format_channel_name,
)


@pytest.fixture
def test_db():
    """Create a temporary test database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    db = init_database(db_path)
    yield db
    db.close()
    db_path.unlink()


@pytest.fixture
def setup_test_data(test_db):
    """Set up test workers and channels."""
    # Create a test team first
    from core.queries.team import create_team
    team = create_team(test_db, name="Engineering")

    # Create test workers
    alice = create_worker(
        test_db,
        name="Alice",
        role="Engineer",
        team_id=team.id,
        cost=50,
        manager_id=None,
    )
    bob = create_worker(
        test_db,
        name="Bob",
        role="Engineer",
        team_id=team.id,
        cost=50,
        manager_id=None,
    )

    # Create test channels
    general = create_channel(test_db, "general", "topic")
    team = create_channel(test_db, "engineering", "team")

    # Subscribe workers to channels
    subscribe_to_channel(test_db, general.id, alice.id)
    subscribe_to_channel(test_db, general.id, bob.id)

    return {
        "db": test_db,
        "alice": alice,
        "bob": bob,
        "general": general,
        "team": team,
    }


def test_resolve_channel_by_name(setup_test_data):
    """Test resolving channel by #name."""
    data = setup_test_data
    db = data["db"]
    alice = data["alice"]
    general = data["general"]

    # Resolve #general
    channel_id = resolve_channel(db, "#general", alice.id)
    assert channel_id == general.id


def test_resolve_channel_by_name_case_insensitive(setup_test_data):
    """Test that channel name resolution is case-insensitive."""
    data = setup_test_data
    db = data["db"]
    alice = data["alice"]
    general = data["general"]

    # Resolve #GENERAL (uppercase)
    channel_id = resolve_channel(db, "#GENERAL", alice.id)
    assert channel_id == general.id

    # Resolve #General (mixed case)
    channel_id = resolve_channel(db, "#General", alice.id)
    assert channel_id == general.id


def test_resolve_channel_not_found(setup_test_data):
    """Test error when channel name not found."""
    data = setup_test_data
    db = data["db"]
    alice = data["alice"]

    with pytest.raises(ChannelResolutionError, match="not found"):
        resolve_channel(db, "#nonexistent", alice.id)


def test_resolve_dm_channel(setup_test_data):
    """Test resolving DM channel with @worker-id."""
    data = setup_test_data
    db = data["db"]
    alice = data["alice"]
    bob = data["bob"]

    # Resolve @bob (creates DM channel)
    channel_id = resolve_channel(db, f"@{bob.id}", alice.id)
    assert channel_id is not None

    # Verify it's a valid channel ID and it's a direct channel
    from core.queries.channel import get_channel
    channel = get_channel(db, channel_id)
    assert channel is not None
    assert channel.type == "direct"


def test_resolve_dm_creates_channel(setup_test_data):
    """Test that DM resolution creates channel if it doesn't exist."""
    data = setup_test_data
    db = data["db"]
    alice = data["alice"]
    bob = data["bob"]

    # First call creates the channel
    channel_id_1 = resolve_channel(db, f"@{bob.id}", alice.id)

    # Second call returns the same channel
    channel_id_2 = resolve_channel(db, f"@{bob.id}", alice.id)

    assert channel_id_1 == channel_id_2


def test_resolve_dm_worker_not_found(setup_test_data):
    """Test error when DM target worker not found."""
    data = setup_test_data
    db = data["db"]
    alice = data["alice"]

    with pytest.raises(ChannelResolutionError, match="not found"):
        resolve_channel(db, "@nonexistent-worker", alice.id)


def test_resolve_dm_self(setup_test_data):
    """Test error when trying to DM yourself."""
    data = setup_test_data
    db = data["db"]
    alice = data["alice"]

    with pytest.raises(ChannelResolutionError, match="Cannot send direct message to yourself"):
        resolve_channel(db, f"@{alice.id}", alice.id)


def test_resolve_channel_by_id(setup_test_data):
    """Test resolving channel by raw ID."""
    data = setup_test_data
    db = data["db"]
    alice = data["alice"]
    general = data["general"]

    # Pass raw channel ID
    channel_id = resolve_channel(db, general.id, alice.id)
    assert channel_id == general.id


def test_resolve_channel_invalid_id(setup_test_data):
    """Test error when channel ID not found."""
    data = setup_test_data
    db = data["db"]
    alice = data["alice"]

    with pytest.raises(ChannelResolutionError, match="not found"):
        resolve_channel(db, "chan-nonexistent", alice.id)


def test_resolve_channel_empty(setup_test_data):
    """Test error when channel ref is empty."""
    data = setup_test_data
    db = data["db"]
    alice = data["alice"]

    with pytest.raises(ChannelResolutionError, match="cannot be empty"):
        resolve_channel(db, "", alice.id)


def test_resolve_channel_empty_after_prefix(setup_test_data):
    """Test error when channel name is empty after prefix."""
    data = setup_test_data
    db = data["db"]
    alice = data["alice"]

    with pytest.raises(ChannelResolutionError, match="cannot be empty"):
        resolve_channel(db, "#", alice.id)

    with pytest.raises(ChannelResolutionError, match="cannot be empty"):
        resolve_channel(db, "@", alice.id)


def test_format_channel_name_topic():
    """Test formatting topic channel names."""
    assert format_channel_name("general", "topic") == "#general"
    assert format_channel_name("announcements", "topic") == "#announcements"


def test_format_channel_name_team():
    """Test formatting team channel names."""
    assert format_channel_name("engineering", "team") == "#engineering"
    assert format_channel_name("product", "team") == "#product"


def test_format_channel_name_direct():
    """Test formatting direct channel names."""
    assert format_channel_name("dm-alice-bob", "direct") == "@alice↔bob"
    assert format_channel_name("dm-12345678-87654321", "direct") == "@12345678↔87654321"


def test_format_channel_name_direct_fallback():
    """Test formatting direct channel without dm- prefix."""
    # If channel doesn't follow dm-{id1}-{id2} format, just add @
    assert format_channel_name("custom-channel", "direct") == "@custom-channel"
