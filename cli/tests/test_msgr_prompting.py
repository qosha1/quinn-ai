"""
Test that workers are explicitly prompted to use msgr for team communication.

This test verifies the fix for quinnai-pyo3g: Workers have msgr CLI but never use it
because they aren't explicitly prompted to do so.
"""

import pytest
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from cli.core.onboarding import _generate_first_actions


class TestMsgrPrompting:
    """Test that msgr usage is explicitly prompted in all onboarding materials."""

    def test_briefing_template_contains_when_to_post_section(self):
        """BRIEFING.md template must include 'When to Post Status Updates' section."""
        # Load the briefing template
        template_dir = Path(__file__).parent.parent / "config" / "templates"
        env = Environment(loader=FileSystemLoader(str(template_dir)))
        template = env.get_template("briefing.md.jinja2")

        # Render with minimal context
        content = template.render(
            worker_id="test-worker",
            worker_name="Test Worker",
            worker_role="Engineer",
            team_name="engineering",
            manager_name="Manager",
            manager_id="mgr-1",
            org_mission="Test mission",
            okrs=[],
            worker_storage="/tmp/storage",
            shared_storage="/tmp/shared",
            is_ceo=False,
            is_manager=False,
            timestamp="2026-01-31",
            first_actions=["Action 1"],
            escalation_timeout_minutes=30,
        )

        # Verify "When to Post Status Updates" section exists
        assert "### When to Post Status Updates" in content, \
            "BRIEFING.md must include 'When to Post Status Updates' section"

        # Verify it includes concrete examples of WHEN to post
        assert "Start a task" in content, "Must tell workers to post when starting tasks"
        assert "Complete a task" in content, "Must tell workers to post when completing tasks"
        assert "Get blocked" in content, "Must tell workers to post when blocked"
        assert "Every 30-60 minutes" in content, "Must tell workers to post regular updates"

        # Verify it includes example workflow with msgr commands
        assert "msgr send" in content, "Must include msgr send examples"
        assert "Example workflow:" in content, "Must include example workflow"

        # Verify it explains WHY this matters
        assert "Team visibility is critical" in content or "Why this matters" in content, \
            "Must explain why messaging is important"

    def test_initial_task_prompt_includes_first_message(self):
        """INITIAL_TASK.md (CEO prompt) must require sending first message."""
        # This verifies the _send_initial_prompt_to_ceo() function in start.py
        # We'll test the prompt string directly since it's a template

        from cli.commands.org.start import _send_initial_prompt_to_ceo
        import inspect

        # Get the source code of the function
        source = inspect.getsource(_send_initial_prompt_to_ceo)

        # Verify the prompt includes explicit msgr usage as FIRST step
        assert 'msgr send #general' in source, \
            "Initial prompt must include msgr send command"
        assert 'FIRST:' in source or 'first message' in source.lower(), \
            "msgr usage must be marked as FIRST task"
        assert 'Introduce yourself' in source, \
            "Must explicitly tell CEO to introduce themselves"
        assert 'msgr channels' in source, \
            "Must show msgr channels command"
        assert 'msgr inbox' in source, \
            "Must show msgr inbox command to confirm message sent"

    def test_ceo_first_actions_includes_msgr_intro(self):
        """CEO first actions must include msgr introduction as first item."""
        actions = _generate_first_actions(
            worker_role="CEO",
            worker_id="ceo",
            is_ceo=True,
            is_manager=False,
            has_okrs=True,
            manager_name=None,
            manager_id=None,
            team_name="general",
        )

        # First action should be msgr introduction
        assert len(actions) > 0, "Must have at least one action"
        first_action = actions[0]
        assert "msgr send" in first_action, \
            "First action must include msgr send command"
        assert "#general" in first_action, \
            "CEO must post to #general channel"
        assert "Introduce" in first_action or "introduce" in first_action, \
            "First action must be an introduction"

        # Should also include reminder about regular updates
        last_actions_str = " ".join(actions[-2:])
        assert "msgr send" in last_actions_str, \
            "Later actions must remind about msgr usage"
        assert ("30-60 minutes" in last_actions_str or "regular" in last_actions_str.lower()), \
            "Must include reminder about regular status updates"

    def test_manager_first_actions_includes_msgr_intro(self):
        """Manager first actions must include msgr introduction as first item."""
        actions = _generate_first_actions(
            worker_role="Director",
            worker_id="dir-1",
            is_ceo=False,
            is_manager=True,
            has_okrs=True,
            manager_name="CEO",
            manager_id="ceo",
            team_name="engineering",
        )

        # First action should be msgr introduction
        assert len(actions) > 0, "Must have at least one action"
        first_action = actions[0]
        assert "msgr send" in first_action, \
            "First action must include msgr send command"
        assert "#engineering" in first_action or "team" in first_action.lower(), \
            "Manager must post to team channel"
        assert "Introduce" in first_action or "introduce" in first_action.lower(), \
            "First action must be an introduction"

    def test_worker_first_actions_includes_msgr_intro(self):
        """Worker first actions must include msgr introduction as first item."""
        actions = _generate_first_actions(
            worker_role="Engineer",
            worker_id="eng-1",
            is_ceo=False,
            is_manager=False,
            has_okrs=True,
            manager_name="Director",
            manager_id="dir-1",
            team_name="engineering",
        )

        # First action should be msgr introduction (DM to manager)
        assert len(actions) > 0, "Must have at least one action"
        first_action = actions[0]
        assert "msgr send" in first_action, \
            "First action must include msgr send command"
        assert "@dir-1" in first_action or "manager" in first_action.lower(), \
            "Worker must message their manager"
        assert "Introduce" in first_action or "introduce" in first_action.lower(), \
            "First action must be an introduction"

        # Should also include instructions about posting task updates
        actions_str = " ".join(actions)
        assert "Starting:" in actions_str or "starting" in actions_str.lower(), \
            "Must tell worker to post when starting tasks"
        assert "#engineering" in actions_str or "team" in actions_str.lower(), \
            "Must tell worker which channel to post to"

    def test_all_worker_types_have_msgr_in_first_three_actions(self):
        """All worker types must have msgr usage in their first 3 actions."""
        test_cases = [
            # (is_ceo, is_manager, role, expected_channel_pattern)
            (True, False, "CEO", "#general"),
            (False, True, "Director", "#"),
            (False, False, "Engineer", "msgr send"),
        ]

        for is_ceo, is_manager, role, channel_pattern in test_cases:
            actions = _generate_first_actions(
                worker_role=role,
                worker_id=f"{role.lower()}-1",
                is_ceo=is_ceo,
                is_manager=is_manager,
                has_okrs=True,
                manager_name="Manager" if not is_ceo else None,
                manager_id="mgr-1" if not is_ceo else None,
                team_name="engineering",
            )

            # Check first 3 actions for msgr usage
            first_three = " ".join(actions[:3])
            assert "msgr send" in first_three, \
                f"{role} must have msgr send in first 3 actions"
            if channel_pattern != "msgr send":
                assert channel_pattern in first_three, \
                    f"{role} must reference {channel_pattern} in first 3 actions"

    def test_briefing_includes_team_channel_variable(self):
        """BRIEFING.md must use team_name variable for channel references."""
        template_dir = Path(__file__).parent.parent / "config" / "templates"
        env = Environment(loader=FileSystemLoader(str(template_dir)))
        template = env.get_template("briefing.md.jinja2")

        # Render with specific team name
        content = template.render(
            worker_id="test-worker",
            worker_name="Test Worker",
            worker_role="Engineer",
            team_name="platform",  # Specific team name
            manager_name="Manager",
            manager_id="mgr-1",
            org_mission="Test mission",
            okrs=[],
            worker_storage="/tmp/storage",
            shared_storage="/tmp/shared",
            is_ceo=False,
            is_manager=False,
            timestamp="2026-01-31",
            first_actions=["Action 1"],
            escalation_timeout_minutes=30,
        )

        # Verify team name is rendered in examples
        assert "#platform" in content, \
            "BRIEFING.md must use team_name variable in channel examples"

        # Verify it appears in the status update section
        status_section_start = content.find("### When to Post Status Updates")
        if status_section_start != -1:
            status_section = content[status_section_start:status_section_start + 1000]
            assert "#platform" in status_section, \
                "Status update section must use team_name variable"
