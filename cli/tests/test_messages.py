"""
Unit tests for message and channel storage operations.

Tests message CRUD, channel management, subscriptions, threading,
references, and full-text search.
"""

import tempfile
from pathlib import Path

import pytest

from cli.core.db import init_database
from cli.core.queries import (
    # Teams & Workers (for setup)
    create_team,
    create_worker,
    add_team_member,
    # Channels
    create_channel,
    create_direct_channel,
    get_or_create_direct_channel,
    get_channel,
    get_channel_by_name,
    get_team_channel,
    create_default_org_channels,
    subscribe_to_channel,
    unsubscribe_from_channel,
    get_channel_subscribers,
    get_worker_channels,
    is_subscribed_to_channel,
    can_subscribe_to_channel,
    ChannelAccessError,
    # Messages
    create_message,
    get_message,
    get_channel_messages,
    get_thread_messages,
    search_messages,
    add_message_ref,
    get_message_refs,
)


@pytest.fixture
def db_path():
    """Create a temporary database path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "live" / "quinn.db"


@pytest.fixture
def db(db_path):
    """Create and initialize a test database."""
    database = init_database(db_path)
    yield database
    database.close()


@pytest.fixture
def team(db):
    """Create a test team."""
    return create_team(db, "Engineering")


@pytest.fixture
def worker(db, team):
    """Create a test worker."""
    return create_worker(db, "Alice", "Developer", team.id, 50)


@pytest.fixture
def worker2(db, team):
    """Create a second test worker."""
    return create_worker(db, "Bob", "Developer", team.id, 50)


@pytest.fixture
def channel(db):
    """Create a test channel."""
    return create_channel(db, "general", "topic")


class TestChannelCreation:
    """Test channel creation operations."""

    def test_create_topic_channel(self, db):
        """Should create a topic channel."""
        channel = create_channel(db, "announcements", "topic")
        assert channel.name == "announcements"
        assert channel.type == "topic"
        assert channel.id.startswith("chan-")
        assert channel.team_id is None

    def test_create_team_channel(self, db, team):
        """Should create a team channel linked to team."""
        channel = create_channel(db, "eng-general", "team", team_id=team.id)
        assert channel.name == "eng-general"
        assert channel.type == "team"
        assert channel.team_id == team.id

    def test_create_direct_channel(self, db):
        """Should create a direct message channel."""
        channel = create_channel(db, "dm-alice-bob", "direct")
        assert channel.type == "direct"

    def test_create_channel_with_custom_id(self, db):
        """Should allow custom channel ID."""
        channel = create_channel(db, "custom", "topic", channel_id="chan-custom-123")
        assert channel.id == "chan-custom-123"


class TestTeamChannelAutoCreation:
    """Test automatic channel creation when teams are created."""

    def test_create_team_auto_creates_channel(self, db):
        """Creating a team should auto-create a team channel."""
        team = create_team(db, "Engineering")
        channel = get_team_channel(db, team.id)
        assert channel is not None
        assert channel.type == "team"
        assert channel.team_id == team.id

    def test_team_channel_name_is_lowercase(self, db):
        """Team channel name should be lowercase version of team name."""
        team = create_team(db, "Marketing")
        channel = get_team_channel(db, team.id)
        assert channel.name == "marketing"

    def test_team_channel_name_replaces_spaces(self, db):
        """Team channel name should replace spaces with hyphens."""
        team = create_team(db, "Data Science")
        channel = get_team_channel(db, team.id)
        assert channel.name == "data-science"

    def test_create_team_without_auto_channel(self, db):
        """Should be able to create team without auto channel."""
        team = create_team(db, "NoChannel", auto_create_channel=False)
        channel = get_team_channel(db, team.id)
        assert channel is None


class TestGetChannelByName:
    """Test channel retrieval by name."""

    def test_get_channel_by_name(self, db):
        """Should retrieve channel by name."""
        created = create_channel(db, "my-channel", "topic")
        fetched = get_channel_by_name(db, "my-channel")
        assert fetched is not None
        assert fetched.id == created.id

    def test_get_channel_by_name_case_insensitive(self, db):
        """Should retrieve channel by name case-insensitively."""
        created = create_channel(db, "MyChannel", "topic")
        fetched = get_channel_by_name(db, "mychannel")
        assert fetched is not None
        assert fetched.id == created.id

    def test_get_nonexistent_channel_by_name(self, db):
        """Should return None for missing channel name."""
        result = get_channel_by_name(db, "nonexistent")
        assert result is None


class TestDefaultOrgChannels:
    """Test default org-wide channel creation."""

    def test_create_default_channels(self, db):
        """Should create general and escalations channels."""
        channels = create_default_org_channels(db)
        names = {c.name for c in channels}
        assert "general" in names
        assert "escalations" in names

    def test_default_channels_are_topic_type(self, db):
        """Default channels should be topic type."""
        channels = create_default_org_channels(db)
        for channel in channels:
            assert channel.type == "topic"

    def test_default_channels_have_no_team(self, db):
        """Default channels should be org-wide (no team_id)."""
        channels = create_default_org_channels(db)
        for channel in channels:
            assert channel.team_id is None

    def test_create_default_channels_idempotent(self, db):
        """Creating default channels twice should not duplicate."""
        channels1 = create_default_org_channels(db)
        channels2 = create_default_org_channels(db)
        # First call creates 2, second call creates 0 (already exist)
        assert len(channels1) == 2
        assert len(channels2) == 0


class TestChannelRetrieval:
    """Test channel retrieval operations."""

    def test_get_channel_by_id(self, db, channel):
        """Should retrieve channel by ID."""
        fetched = get_channel(db, channel.id)
        assert fetched is not None
        assert fetched.id == channel.id
        assert fetched.name == channel.name

    def test_get_nonexistent_channel(self, db):
        """Should return None for missing channel."""
        result = get_channel(db, "nonexistent-id")
        assert result is None


class TestChannelSubscriptions:
    """Test channel subscription operations."""

    def test_subscribe_worker_to_channel(self, db, channel, worker):
        """Should subscribe worker to channel."""
        subscribe_to_channel(db, channel.id, worker.id)
        subscribers = get_channel_subscribers(db, channel.id)
        assert worker.id in subscribers

    def test_subscribe_multiple_workers(self, db, channel, worker, worker2):
        """Should allow multiple workers to subscribe."""
        subscribe_to_channel(db, channel.id, worker.id)
        subscribe_to_channel(db, channel.id, worker2.id)
        subscribers = get_channel_subscribers(db, channel.id)
        assert len(subscribers) == 2
        assert worker.id in subscribers
        assert worker2.id in subscribers

    def test_unsubscribe_worker_from_channel(self, db, channel, worker):
        """Should unsubscribe worker from channel."""
        subscribe_to_channel(db, channel.id, worker.id)
        unsubscribe_from_channel(db, channel.id, worker.id)
        subscribers = get_channel_subscribers(db, channel.id)
        assert worker.id not in subscribers

    def test_get_worker_channels(self, db, worker):
        """Should get all channels a worker is subscribed to."""
        chan1 = create_channel(db, "channel-1", "topic")
        chan2 = create_channel(db, "channel-2", "topic")
        chan3 = create_channel(db, "channel-3", "topic")

        subscribe_to_channel(db, chan1.id, worker.id)
        subscribe_to_channel(db, chan2.id, worker.id)
        # Not subscribed to chan3

        channels = get_worker_channels(db, worker.id)
        channel_ids = {c.id for c in channels}
        assert len(channels) == 2
        assert chan1.id in channel_ids
        assert chan2.id in channel_ids
        assert chan3.id not in channel_ids

    def test_duplicate_subscription_ignored(self, db, channel, worker):
        """Should ignore duplicate subscriptions."""
        subscribe_to_channel(db, channel.id, worker.id)
        subscribe_to_channel(db, channel.id, worker.id)  # Duplicate
        subscribers = get_channel_subscribers(db, channel.id)
        assert subscribers.count(worker.id) == 1


class TestMessageCreation:
    """Test message creation operations."""

    def test_create_message(self, db, channel, worker):
        """Should create a message with default values."""
        msg = create_message(db, channel.id, worker.id, "Hello world")
        assert msg.content == "Hello world"
        assert msg.channel_id == channel.id
        assert msg.from_worker_id == worker.id
        assert msg.priority == 2  # default
        assert msg.time_sensitivity == "whenever"  # default
        assert msg.id.startswith("msg-")

    def test_create_message_with_priority(self, db, channel, worker):
        """Should create message with custom priority."""
        msg = create_message(
            db, channel.id, worker.id, "Urgent!",
            priority=0, time_sensitivity="immediate"
        )
        assert msg.priority == 0
        assert msg.time_sensitivity == "immediate"

    def test_create_message_in_thread(self, db, channel, worker):
        """Should create message in a thread."""
        thread_id = "thread-abc123"
        msg = create_message(
            db, channel.id, worker.id, "Thread reply",
            thread_id=thread_id
        )
        assert msg.thread_id == thread_id

    def test_create_message_with_parent(self, db, channel, worker):
        """Should create message with parent reference."""
        parent = create_message(db, channel.id, worker.id, "Parent message")
        reply = create_message(
            db, channel.id, worker.id, "Reply",
            parent_id=parent.id, thread_id=parent.id
        )
        assert reply.parent_id == parent.id

    def test_create_message_with_custom_id(self, db, channel, worker):
        """Should allow custom message ID."""
        msg = create_message(
            db, channel.id, worker.id, "Custom",
            message_id="msg-custom-456"
        )
        assert msg.id == "msg-custom-456"


class TestMessageRetrieval:
    """Test message retrieval operations."""

    def test_get_message_by_id(self, db, channel, worker):
        """Should retrieve message by ID."""
        created = create_message(db, channel.id, worker.id, "Test message")
        fetched = get_message(db, created.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.content == "Test message"

    def test_get_nonexistent_message(self, db):
        """Should return None for missing message."""
        result = get_message(db, "nonexistent-id")
        assert result is None

    def test_get_channel_messages_ordered(self, db, channel, worker):
        """Should get channel messages newest first."""
        create_message(db, channel.id, worker.id, "First")
        create_message(db, channel.id, worker.id, "Second")
        create_message(db, channel.id, worker.id, "Third")

        messages = get_channel_messages(db, channel.id)
        assert len(messages) == 3
        assert messages[0].content == "Third"  # newest
        assert messages[2].content == "First"  # oldest

    def test_get_channel_messages_with_limit(self, db, channel, worker):
        """Should limit number of returned messages."""
        for i in range(10):
            create_message(db, channel.id, worker.id, f"Message {i}")

        messages = get_channel_messages(db, channel.id, limit=5)
        assert len(messages) == 5

    def test_get_channel_messages_with_offset(self, db, channel, worker):
        """Should paginate with offset."""
        for i in range(10):
            create_message(db, channel.id, worker.id, f"Message {i}")

        page1 = get_channel_messages(db, channel.id, limit=3, offset=0)
        page2 = get_channel_messages(db, channel.id, limit=3, offset=3)

        assert len(page1) == 3
        assert len(page2) == 3
        # No overlap
        page1_ids = {m.id for m in page1}
        page2_ids = {m.id for m in page2}
        assert len(page1_ids & page2_ids) == 0

    def test_get_thread_messages_ordered(self, db, channel, worker):
        """Should get thread messages oldest first."""
        thread_id = "thread-test"
        create_message(db, channel.id, worker.id, "First reply", thread_id=thread_id)
        create_message(db, channel.id, worker.id, "Second reply", thread_id=thread_id)
        create_message(db, channel.id, worker.id, "Third reply", thread_id=thread_id)

        messages = get_thread_messages(db, thread_id)
        assert len(messages) == 3
        assert messages[0].content == "First reply"  # oldest
        assert messages[2].content == "Third reply"  # newest


class TestMessageReferences:
    """Test message reference operations."""

    def test_add_bead_reference(self, db, channel, worker):
        """Should add bead reference to message."""
        msg = create_message(db, channel.id, worker.id, "Working on bead-123")
        add_message_ref(db, msg.id, "bead", "bead-123")

        refs = get_message_refs(db, msg.id)
        assert ("bead", "bead-123") in refs

    def test_add_multiple_references(self, db, channel, worker):
        """Should add multiple references to message."""
        msg = create_message(db, channel.id, worker.id, "Multi-ref message")
        add_message_ref(db, msg.id, "bead", "bead-123")
        add_message_ref(db, msg.id, "okr", "okr-456")
        add_message_ref(db, msg.id, "ask", "ask-789")

        refs = get_message_refs(db, msg.id)
        assert len(refs) == 3
        assert ("bead", "bead-123") in refs
        assert ("okr", "okr-456") in refs
        assert ("ask", "ask-789") in refs

    def test_duplicate_reference_ignored(self, db, channel, worker):
        """Should ignore duplicate references."""
        msg = create_message(db, channel.id, worker.id, "Test")
        add_message_ref(db, msg.id, "bead", "bead-123")
        add_message_ref(db, msg.id, "bead", "bead-123")  # Duplicate

        refs = get_message_refs(db, msg.id)
        bead_refs = [r for r in refs if r == ("bead", "bead-123")]
        assert len(bead_refs) == 1

    def test_get_refs_for_message_without_refs(self, db, channel, worker):
        """Should return empty list for message without refs."""
        msg = create_message(db, channel.id, worker.id, "No refs")
        refs = get_message_refs(db, msg.id)
        assert refs == []


class TestMessageSearch:
    """Test message full-text search operations."""

    def test_search_messages_basic(self, db, channel, worker):
        """Should find messages by content."""
        create_message(db, channel.id, worker.id, "The quick brown fox")
        create_message(db, channel.id, worker.id, "A lazy dog sleeps")
        create_message(db, channel.id, worker.id, "Hello world")

        results = search_messages(db, "fox")
        assert len(results) == 1
        assert results[0].content == "The quick brown fox"

    def test_search_messages_multiple_results(self, db, channel, worker):
        """Should return multiple matching messages."""
        create_message(db, channel.id, worker.id, "Python is great")
        create_message(db, channel.id, worker.id, "Python programming")
        create_message(db, channel.id, worker.id, "JavaScript is different")

        results = search_messages(db, "Python")
        assert len(results) == 2

    def test_search_messages_no_results(self, db, channel, worker):
        """Should return empty list when no matches."""
        create_message(db, channel.id, worker.id, "Hello world")

        results = search_messages(db, "nonexistent")
        assert results == []

    def test_search_messages_filter_by_channel(self, db, worker):
        """Should filter search results by channel."""
        chan1 = create_channel(db, "channel-1", "topic")
        chan2 = create_channel(db, "channel-2", "topic")

        create_message(db, chan1.id, worker.id, "Python in channel 1")
        create_message(db, chan2.id, worker.id, "Python in channel 2")

        results = search_messages(db, "Python", channel_id=chan1.id)
        assert len(results) == 1
        assert results[0].channel_id == chan1.id

    def test_search_messages_with_limit(self, db, channel, worker):
        """Should limit search results."""
        for i in range(10):
            create_message(db, channel.id, worker.id, f"Test message number {i}")

        results = search_messages(db, "Test", limit=3)
        assert len(results) == 3

    def test_search_messages_with_offset(self, db, channel, worker):
        """Should paginate search results."""
        for i in range(10):
            create_message(db, channel.id, worker.id, f"Search term number {i}")

        page1 = search_messages(db, "Search", limit=3, offset=0)
        page2 = search_messages(db, "Search", limit=3, offset=3)

        assert len(page1) == 3
        assert len(page2) == 3
        # No overlap
        page1_ids = {m.id for m in page1}
        page2_ids = {m.id for m in page2}
        assert len(page1_ids & page2_ids) == 0

    def test_search_messages_phrase(self, db, channel, worker):
        """Should search for phrases."""
        create_message(db, channel.id, worker.id, "The quick brown fox jumps")
        create_message(db, channel.id, worker.id, "Quick fixes are temporary")

        # Phrase search with quotes
        results = search_messages(db, '"quick brown"')
        assert len(results) == 1
        assert "quick brown" in results[0].content.lower()

    def test_search_messages_case_insensitive(self, db, channel, worker):
        """Should search case-insensitively."""
        create_message(db, channel.id, worker.id, "UPPERCASE MESSAGE")
        create_message(db, channel.id, worker.id, "lowercase message")

        results = search_messages(db, "message")
        assert len(results) == 2


class TestMessageChannelIntegration:
    """Test message and channel integration scenarios."""

    def test_messages_isolated_by_channel(self, db, worker):
        """Messages should be isolated to their channels."""
        chan1 = create_channel(db, "channel-1", "topic")
        chan2 = create_channel(db, "channel-2", "topic")

        create_message(db, chan1.id, worker.id, "Message in chan1")
        create_message(db, chan1.id, worker.id, "Another in chan1")
        create_message(db, chan2.id, worker.id, "Message in chan2")

        chan1_messages = get_channel_messages(db, chan1.id)
        chan2_messages = get_channel_messages(db, chan2.id)

        assert len(chan1_messages) == 2
        assert len(chan2_messages) == 1

    def test_thread_across_messages(self, db, channel, worker, worker2):
        """Thread should span multiple messages from different workers."""
        thread_id = "thread-collab"

        create_message(
            db, channel.id, worker.id, "Starting discussion",
            thread_id=thread_id
        )
        create_message(
            db, channel.id, worker2.id, "I agree",
            thread_id=thread_id
        )
        create_message(
            db, channel.id, worker.id, "Great, let's proceed",
            thread_id=thread_id
        )

        thread = get_thread_messages(db, thread_id)
        assert len(thread) == 3
        # Check both workers participated
        worker_ids = {m.from_worker_id for m in thread}
        assert worker.id in worker_ids
        assert worker2.id in worker_ids


class TestChannelPermissionValidation:
    """Test channel permission validation for subscriptions.

    Security tests ensuring workers can only subscribe to channels
    they are allowed to access based on channel type.
    """

    def test_topic_channel_open_to_all(self, db, worker):
        """Topic channels should allow any worker to subscribe."""
        topic = create_channel(db, "announcements", "topic")
        can_sub, reason = can_subscribe_to_channel(db, topic.id, worker.id)

        assert can_sub is True
        assert "open to all" in reason.lower()

    def test_team_channel_requires_membership(self, db, team):
        """Team channels should only allow team members."""
        # Create a team channel for this team
        team_channel = create_channel(db, "eng-internal", "team", team_id=team.id)

        # Worker in the team should be able to subscribe
        team_worker = create_worker(db, "TeamMember", "Developer", team.id, 50)
        can_sub, reason = can_subscribe_to_channel(db, team_channel.id, team_worker.id)
        assert can_sub is True

        # Worker in different team should NOT be able to subscribe
        other_team = create_team(db, "Marketing")
        other_worker = create_worker(db, "Outsider", "Marketer", other_team.id, 50)
        can_sub, reason = can_subscribe_to_channel(db, team_channel.id, other_worker.id)
        assert can_sub is False
        assert "not a member" in reason.lower()

        # Verify subscribe_to_channel raises error
        with pytest.raises(ChannelAccessError) as exc_info:
            subscribe_to_channel(db, team_channel.id, other_worker.id)
        assert "not a member" in str(exc_info.value).lower()

    def test_team_channel_allows_team_members_table(self, db):
        """Team channel should allow workers added via team_members table."""
        team1 = create_team(db, "Engineering")
        team2 = create_team(db, "Platform")

        # Create worker primarily in team2
        worker = create_worker(db, "CrossTeam", "Developer", team2.id, 50)

        # Create channel for team1
        team1_channel = create_channel(db, "eng-channel", "team", team_id=team1.id)

        # Initially cannot subscribe
        can_sub, _ = can_subscribe_to_channel(db, team1_channel.id, worker.id)
        assert can_sub is False

        # Add worker to team1 via team_members
        add_team_member(db, team1.id, worker.id)

        # Now should be able to subscribe
        can_sub, _ = can_subscribe_to_channel(db, team1_channel.id, worker.id)
        assert can_sub is True

    def test_direct_channel_limited_to_participants(self, db, team):
        """Direct channels should only allow the two participants."""
        worker1 = create_worker(db, "Alice", "Developer", team.id, 50)
        worker2 = create_worker(db, "Bob", "Developer", team.id, 50)
        worker3 = create_worker(db, "Charlie", "Developer", team.id, 50)

        # Create direct channel between worker1 and worker2
        dm_channel = create_direct_channel(db, worker1.id, worker2.id)

        # Participants should have access
        can_sub1, _ = can_subscribe_to_channel(db, dm_channel.id, worker1.id)
        can_sub2, _ = can_subscribe_to_channel(db, dm_channel.id, worker2.id)
        assert can_sub1 is True
        assert can_sub2 is True

        # Third party should NOT have access
        can_sub3, reason = can_subscribe_to_channel(db, dm_channel.id, worker3.id)
        assert can_sub3 is False
        assert "not a participant" in reason.lower()

        # Verify subscribe_to_channel raises error
        with pytest.raises(ChannelAccessError) as exc_info:
            subscribe_to_channel(db, dm_channel.id, worker3.id)
        assert "not a participant" in str(exc_info.value).lower()

    def test_create_direct_channel_validates_workers(self, db, team):
        """create_direct_channel should validate both workers exist."""
        worker = create_worker(db, "Real", "Developer", team.id, 50)

        # Should raise for non-existent worker
        with pytest.raises(ChannelAccessError) as exc_info:
            create_direct_channel(db, worker.id, "fake-worker-id")
        assert "not found" in str(exc_info.value).lower()

    def test_get_or_create_direct_channel_idempotent(self, db, team):
        """get_or_create_direct_channel should return same channel."""
        worker1 = create_worker(db, "Alice", "Developer", team.id, 50)
        worker2 = create_worker(db, "Bob", "Developer", team.id, 50)

        # Create channel
        dm1 = get_or_create_direct_channel(db, worker1.id, worker2.id)

        # Get again (reversed order should still find same channel)
        dm2 = get_or_create_direct_channel(db, worker2.id, worker1.id)

        assert dm1.id == dm2.id

    def test_is_subscribed_to_channel(self, db, channel, worker):
        """is_subscribed_to_channel should correctly report subscription status."""
        # Not subscribed initially
        assert is_subscribed_to_channel(db, channel.id, worker.id) is False

        # Subscribe
        subscribe_to_channel(db, channel.id, worker.id)

        # Now subscribed
        assert is_subscribed_to_channel(db, channel.id, worker.id) is True

        # Unsubscribe
        unsubscribe_from_channel(db, channel.id, worker.id)

        # No longer subscribed
        assert is_subscribed_to_channel(db, channel.id, worker.id) is False

    def test_skip_validation_allows_bypass(self, db, team):
        """skip_validation=True should bypass permission checks."""
        other_team = create_team(db, "Marketing")
        outsider = create_worker(db, "Outsider", "Marketer", other_team.id, 50)

        # Create team channel
        team_channel = create_channel(db, "eng-private", "team", team_id=team.id)

        # Outsider can't normally subscribe
        can_sub, _ = can_subscribe_to_channel(db, team_channel.id, outsider.id)
        assert can_sub is False

        # But with skip_validation, it works (for internal use)
        subscribe_to_channel(db, team_channel.id, outsider.id, skip_validation=True)
        subscribers = get_channel_subscribers(db, team_channel.id)
        assert outsider.id in subscribers
