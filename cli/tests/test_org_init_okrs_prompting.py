"""Tests for OKR prompting and file import during org initialization."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from cli.commands.main import qn
from cli.core.org_init import OrgInitConfig, ObjectiveConfig, init_org
from cli.core.org import Org
from cli.core.db import init_database, open_database, get_org_db_path
from cli.core.queries.okr import get_okrs_by_owner
from cli.core.constants import DEFAULT_BOOTSTRAP_OKR_TITLE


@pytest.fixture
def runner():
    """Get Click test runner."""
    return CliRunner()


@pytest.fixture
def temp_org_dir():
    """Create a temporary org directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        org_path = Path(tmpdir) / "test-org"
        org_path.mkdir(parents=True)
        yield org_path


@pytest.fixture
def temp_okrs_file():
    """Create a temporary OKRs JSON file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        okrs_data = [
            {
                "title": "Launch MVP",
                "description": "Build and ship MVP to customers",
                "key_results": [
                    {"metric": "features", "target": 5.0, "unit": "count"},
                ]
            },
            {
                "title": "Build engineering team",
                "key_results": [
                    {"metric": "engineers", "target": 3.0, "unit": "count"},
                ]
            }
        ]
        json.dump(okrs_data, f)
        f.flush()
        yield Path(f.name)
    Path(f.name).unlink(missing_ok=True)


class TestOKRsFileImport:
    """Test importing OKRs from a file during org init."""

    def test_init_with_okrs_file_creates_okrs(self, runner, temp_org_dir, temp_okrs_file):
        """Test that --okrs-file flag imports OKRs from file."""
        result = runner.invoke(
            qn,
            ['--org-path', str(temp_org_dir), 'org', 'init', '--okrs-file', str(temp_okrs_file)],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "Loaded 2 objective(s)" in result.output

        # Verify OKRs were created in database
        db_path = get_org_db_path(temp_org_dir)
        assert db_path.exists()

        db = open_database(db_path)
        try:
            # Get CEO to find their OKRs
            from cli.core.org import Org
            org = Org.load(db)
            ceo_id = org.ceo_worker_id

            okrs = get_okrs_by_owner(db, ceo_id)
            assert len(okrs) == 2

            titles = {o.title for o in okrs}
            assert "Launch MVP" in titles
            assert "Build engineering team" in titles
        finally:
            db.close()

    def test_init_with_invalid_okrs_file_fails(self, runner, temp_org_dir):
        """Test that invalid JSON file raises an error."""
        # Create invalid JSON file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{ not valid json }")
            invalid_file = Path(f.name)

        try:
            result = runner.invoke(
                qn,
                ['--org-path', str(temp_org_dir), 'org', 'init', '--okrs-file', str(invalid_file)],
            )

            assert result.exit_code != 0
            assert "Invalid JSON" in result.output
        finally:
            invalid_file.unlink(missing_ok=True)

    def test_init_with_nonexistent_okrs_file_fails(self, runner, temp_org_dir):
        """Test that nonexistent file raises an error."""
        result = runner.invoke(
            qn,
            ['--org-path', str(temp_org_dir), 'org', 'init', '--okrs-file', '/nonexistent/path/okrs.json'],
        )

        assert result.exit_code != 0
        assert "not found" in result.output.lower()


class TestSkipOKRsFlag:
    """Test skipping OKR prompting with --skip-okrs flag."""

    def test_skip_okrs_uses_bootstrap(self, runner, temp_org_dir):
        """Test that --skip-okrs creates bootstrap OKR without prompting."""
        result = runner.invoke(
            qn,
            ['--org-path', str(temp_org_dir), 'org', 'init', '--skip-okrs'],
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify bootstrap OKR was created
        db_path = get_org_db_path(temp_org_dir)
        db = open_database(db_path)
        try:
            from cli.core.org import Org
            org = Org.load(db)
            ceo_id = org.ceo_worker_id

            okrs = get_okrs_by_owner(db, ceo_id)
            assert len(okrs) == 1
            assert okrs[0].title == DEFAULT_BOOTSTRAP_OKR_TITLE
        finally:
            db.close()


class TestInteractiveOKRPrompting:
    """Test interactive OKR prompting during org init."""

    def test_interactive_prompting_creates_okrs(self, runner, temp_org_dir):
        """Test interactive prompting for OKRs creates them in database."""
        # Simulate user input:
        # - First OKR title: "Build product"
        # - Add another? y
        # - Second OKR title: "Grow team"
        # - Add another? n
        user_input = "Build product\ny\nGrow team\nn\n"

        result = runner.invoke(
            qn,
            ['--org-path', str(temp_org_dir), 'org', 'init'],
            input=user_input,
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "Collected 2 objective(s)" in result.output

        # Verify OKRs were created
        db_path = get_org_db_path(temp_org_dir)
        db = open_database(db_path)
        try:
            from cli.core.org import Org
            org = Org.load(db)
            ceo_id = org.ceo_worker_id

            okrs = get_okrs_by_owner(db, ceo_id)
            assert len(okrs) == 2

            titles = {o.title for o in okrs}
            assert "Build product" in titles
            assert "Grow team" in titles
        finally:
            db.close()

    def test_interactive_prompting_empty_skips_to_bootstrap(self, runner, temp_org_dir):
        """Test that entering empty OKR title creates bootstrap OKR."""
        # User just presses Enter without entering an OKR
        user_input = "\n"

        result = runner.invoke(
            qn,
            ['--org-path', str(temp_org_dir), 'org', 'init'],
            input=user_input,
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"

        # Verify bootstrap OKR was created
        db_path = get_org_db_path(temp_org_dir)
        db = open_database(db_path)
        try:
            from cli.core.org import Org
            org = Org.load(db)
            ceo_id = org.ceo_worker_id

            okrs = get_okrs_by_owner(db, ceo_id)
            assert len(okrs) == 1
            assert okrs[0].title == DEFAULT_BOOTSTRAP_OKR_TITLE
        finally:
            db.close()

    def test_interactive_prompting_max_three_okrs(self, runner, temp_org_dir):
        """Test that interactive prompting allows max 3 OKRs during init."""
        # User enters 3 OKRs - should not prompt for 4th
        user_input = "OKR 1\ny\nOKR 2\ny\nOKR 3\n"

        result = runner.invoke(
            qn,
            ['--org-path', str(temp_org_dir), 'org', 'init'],
            input=user_input,
        )

        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "Collected 3 objective(s)" in result.output

        # Verify 3 OKRs were created
        db_path = get_org_db_path(temp_org_dir)
        db = open_database(db_path)
        try:
            from cli.core.org import Org
            org = Org.load(db)
            ceo_id = org.ceo_worker_id

            okrs = get_okrs_by_owner(db, ceo_id)
            assert len(okrs) == 3
        finally:
            db.close()


class TestOrgInitConfigObjectives:
    """Test OrgInitConfig.objectives are passed through correctly."""

    def test_objectives_passed_to_init_org(self, runner, temp_org_dir, temp_okrs_file):
        """Test that objectives in config are passed through to OKRs.

        This test verifies the data flow from CLI options through OrgInitConfig
        to the database. We use the --okrs-file flag as it exercises the same
        code path as objectives passed directly to OrgInitConfig.
        """
        # Create OKRs file with specific objectives
        okrs_data = [
            {"title": "Strategic objective 1"},
            {"title": "Strategic objective 2"},
        ]
        Path(temp_okrs_file).write_text(json.dumps(okrs_data))

        result = runner.invoke(
            qn,
            ['--org-path', str(temp_org_dir), 'org', 'init', '--okrs-file', str(temp_okrs_file)],
        )

        assert result.exit_code == 0, f"Init failed: {result.output}"

        # Verify OKRs from config were created
        db_path = get_org_db_path(temp_org_dir)
        db = open_database(db_path)
        try:
            org = Org.load(db)
            okrs = get_okrs_by_owner(db, org.ceo_worker_id)
            # Should have the 2 configured OKRs (no bootstrap)
            assert len(okrs) == 2

            titles = {o.title for o in okrs}
            assert "Strategic objective 1" in titles
            assert "Strategic objective 2" in titles
        finally:
            db.close()


class TestHelpOutput:
    """Test help output shows OKR options."""

    def test_init_help_shows_okrs_options(self, runner):
        """Test that qn org init --help shows OKR options."""
        result = runner.invoke(qn, ['org', 'init', '--help'])

        assert result.exit_code == 0
        assert "--okrs-file" in result.output
        assert "--skip-okrs" in result.output
