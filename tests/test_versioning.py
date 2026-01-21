"""
Tests for versioning and release infrastructure.

Verifies the project has proper versioning files and follows semver conventions.
"""

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent


class TestVersionFile:
    """Tests for VERSION file."""

    def test_version_file_exists(self):
        """VERSION file must exist in project root."""
        version_file = PROJECT_ROOT / "VERSION"
        assert version_file.exists(), "VERSION file not found in project root"

    def test_version_file_has_valid_semver(self):
        """VERSION file must contain valid semver."""
        version_file = PROJECT_ROOT / "VERSION"
        content = version_file.read_text().strip()

        # Semver pattern: MAJOR.MINOR.PATCH with optional pre-release/build
        semver_pattern = r'^\d+\.\d+\.\d+(-[a-zA-Z0-9.-]+)?(\+[a-zA-Z0-9.-]+)?$'
        assert re.match(semver_pattern, content), (
            f"VERSION '{content}' is not valid semver format"
        )

    def test_version_components_are_integers(self):
        """Version components must be non-negative integers."""
        version_file = PROJECT_ROOT / "VERSION"
        content = version_file.read_text().strip()

        # Extract base version (before any - or +)
        base_version = content.split('-')[0].split('+')[0]
        parts = base_version.split('.')

        assert len(parts) == 3, f"Version must have exactly 3 parts: {content}"

        for i, part in enumerate(parts):
            assert part.isdigit(), f"Version part {i} is not an integer: {part}"
            assert int(part) >= 0, f"Version part {i} is negative: {part}"


class TestChangelog:
    """Tests for CHANGELOG.md."""

    def test_changelog_exists(self):
        """CHANGELOG.md must exist in project root."""
        changelog = PROJECT_ROOT / "CHANGELOG.md"
        assert changelog.exists(), "CHANGELOG.md not found in project root"

    def test_changelog_has_unreleased_section(self):
        """CHANGELOG must have an [Unreleased] section."""
        changelog = PROJECT_ROOT / "CHANGELOG.md"
        content = changelog.read_text()

        assert "## [Unreleased]" in content, (
            "CHANGELOG.md must have an [Unreleased] section"
        )

    def test_changelog_follows_keepachangelog_format(self):
        """CHANGELOG should follow Keep a Changelog format."""
        changelog = PROJECT_ROOT / "CHANGELOG.md"
        content = changelog.read_text()

        # Check for common Keep a Changelog elements
        assert "# Changelog" in content, "Missing '# Changelog' header"

        # Should have at least one version section
        version_pattern = r'## \[\d+\.\d+\.\d+\]'
        assert re.search(version_pattern, content), (
            "No version sections found in changelog"
        )

    def test_changelog_has_valid_section_headers(self):
        """Changelog sections should use standard headers."""
        changelog = PROJECT_ROOT / "CHANGELOG.md"
        content = changelog.read_text()

        valid_headers = {
            "### Added",
            "### Changed",
            "### Deprecated",
            "### Removed",
            "### Fixed",
            "### Security",
        }

        # Find all ### headers in the file
        headers_found = re.findall(r'### \w+', content)

        # Check if any valid headers exist
        has_valid_header = any(h in valid_headers for h in headers_found)
        assert has_valid_header, (
            f"No valid Keep a Changelog headers found. Use: {valid_headers}"
        )


class TestBumpVersionScript:
    """Tests for version bump script."""

    def test_bump_version_script_exists(self):
        """Version bump script must exist."""
        script = PROJECT_ROOT / "scripts" / "bump-version.sh"
        assert script.exists(), "scripts/bump-version.sh not found"

    def test_bump_version_script_is_executable(self):
        """Version bump script must be executable."""
        script = PROJECT_ROOT / "scripts" / "bump-version.sh"
        assert script.stat().st_mode & 0o111, (
            "scripts/bump-version.sh is not executable"
        )

    def test_bump_version_script_handles_major_minor_patch(self):
        """Script should handle major, minor, and patch arguments."""
        script = PROJECT_ROOT / "scripts" / "bump-version.sh"
        content = script.read_text()

        assert "major)" in content, "Script missing major version handling"
        assert "minor)" in content, "Script missing minor version handling"
        assert "patch)" in content, "Script missing patch version handling"


class TestReleaseNotes:
    """Tests for release notes infrastructure."""

    def test_release_notes_directory_exists(self):
        """release-notes directory must exist."""
        release_notes_dir = PROJECT_ROOT / "release-notes"
        assert release_notes_dir.exists(), "release-notes directory not found"

    def test_release_notes_template_exists(self):
        """Release notes template must exist."""
        template = PROJECT_ROOT / "release-notes" / "TEMPLATE.md"
        assert template.exists(), "release-notes/TEMPLATE.md not found"

    def test_template_has_required_sections(self):
        """Template should have all required sections."""
        template = PROJECT_ROOT / "release-notes" / "TEMPLATE.md"
        content = template.read_text()

        required_sections = [
            "## Overview",
            "## Highlights",
            "## Breaking Changes",
            "## Migration Guide",
            "## New Features",
        ]

        for section in required_sections:
            assert section in content, f"Template missing section: {section}"


class TestVersionConsistency:
    """Tests for version consistency across files."""

    def test_version_matches_changelog_latest(self):
        """VERSION should match the latest non-Unreleased version in CHANGELOG."""
        version_file = PROJECT_ROOT / "VERSION"
        changelog = PROJECT_ROOT / "CHANGELOG.md"

        current_version = version_file.read_text().strip()
        changelog_content = changelog.read_text()

        # Find the first version that's not [Unreleased]
        version_pattern = r'## \[(\d+\.\d+\.\d+)\]'
        versions = re.findall(version_pattern, changelog_content)

        if versions:
            latest_changelog_version = versions[0]
            assert current_version == latest_changelog_version, (
                f"VERSION ({current_version}) doesn't match latest CHANGELOG "
                f"version ({latest_changelog_version})"
            )
