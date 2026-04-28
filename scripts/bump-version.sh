#!/bin/bash
#
# Version Bump Script
#
# Usage: ./scripts/bump-version.sh [major|minor|patch]
#
# - major/minor: Requires CHANGELOG.md and RELEASE_NOTES.md updates
# - patch: Auto-generates from git commit messages
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VERSION_FILE="$PROJECT_ROOT/VERSION"
CHANGELOG_FILE="$PROJECT_ROOT/CHANGELOG.md"
RELEASE_NOTES_DIR="$PROJECT_ROOT/release-notes"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Read current version
if [[ ! -f "$VERSION_FILE" ]]; then
    log_error "VERSION file not found at $VERSION_FILE"
    exit 1
fi

CURRENT_VERSION=$(cat "$VERSION_FILE" | tr -d '[:space:]')
log_info "Current version: $CURRENT_VERSION"

# Parse version components
IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT_VERSION"

# Determine bump type
BUMP_TYPE="${1:-patch}"

case "$BUMP_TYPE" in
    major)
        NEW_MAJOR=$((MAJOR + 1))
        NEW_MINOR=0
        NEW_PATCH=0
        ;;
    minor)
        NEW_MAJOR=$MAJOR
        NEW_MINOR=$((MINOR + 1))
        NEW_PATCH=0
        ;;
    patch)
        NEW_MAJOR=$MAJOR
        NEW_MINOR=$MINOR
        NEW_PATCH=$((PATCH + 1))
        ;;
    *)
        log_error "Invalid bump type: $BUMP_TYPE"
        echo "Usage: $0 [major|minor|patch]"
        exit 1
        ;;
esac

NEW_VERSION="${NEW_MAJOR}.${NEW_MINOR}.${NEW_PATCH}"
log_info "New version will be: $NEW_VERSION"

# For major/minor releases, enforce changelog and release notes
if [[ "$BUMP_TYPE" == "major" ]] || [[ "$BUMP_TYPE" == "minor" ]]; then
    log_info "Major/minor release requires changelog and release notes..."

    # Check if [Unreleased] section has content
    UNRELEASED_CONTENT=$(sed -n '/## \[Unreleased\]/,/## \[/p' "$CHANGELOG_FILE" | grep -E "^- " || true)

    if [[ -z "$UNRELEASED_CONTENT" ]]; then
        log_error "CHANGELOG.md [Unreleased] section is empty!"
        log_error "Please document changes before bumping $BUMP_TYPE version."
        echo ""
        echo "Required CHANGELOG sections:"
        echo "  ### Added - for new features"
        echo "  ### Changed - for changes in existing functionality"
        echo "  ### Deprecated - for soon-to-be removed features"
        echo "  ### Removed - for now removed features"
        echo "  ### Fixed - for any bug fixes"
        echo "  ### Security - for vulnerabilities"
        echo ""
        exit 1
    fi

    log_success "Changelog has content in [Unreleased] section"

    # Create release notes directory if needed
    mkdir -p "$RELEASE_NOTES_DIR"

    # Check for release notes file
    RELEASE_NOTES_FILE="$RELEASE_NOTES_DIR/v${NEW_VERSION}.md"

    if [[ ! -f "$RELEASE_NOTES_FILE" ]]; then
        log_warn "Release notes file not found: $RELEASE_NOTES_FILE"
        log_info "Creating template..."

        cat > "$RELEASE_NOTES_FILE" << EOF
# Release v${NEW_VERSION}

**Release Date:** $(date +%Y-%m-%d)
**Release Type:** ${BUMP_TYPE^} Release

## Overview

<!-- Brief description of this release (2-3 sentences) -->

## Highlights

<!-- Key features or changes users should know about -->

## Breaking Changes

<!-- List any breaking changes. Remove section if none -->

- None

## Migration Guide

<!-- Steps users need to take when upgrading. Remove if not applicable -->

No migration required.

## New Features

<!-- Detailed description of new features -->

## Improvements

<!-- Enhancements to existing features -->

## Bug Fixes

<!-- Notable bug fixes -->

## Dependencies

<!-- Updated dependencies -->

## Contributors

<!-- Credit contributors -->

---

*Full changelog: [v${CURRENT_VERSION}...v${NEW_VERSION}](https://github.com/qosha1/quinn-ai/compare/v${CURRENT_VERSION}...v${NEW_VERSION})*
EOF

        log_info "Created release notes template at: $RELEASE_NOTES_FILE"
        log_error "Please fill out the release notes before continuing."
        log_info "Run this script again after completing the release notes."
        exit 1
    fi

    # Verify release notes isn't just a template
    if grep -q "<!-- Brief description" "$RELEASE_NOTES_FILE"; then
        log_error "Release notes file appears to still be a template."
        log_error "Please fill out: $RELEASE_NOTES_FILE"
        exit 1
    fi

    log_success "Release notes found and populated"
fi

# For patch releases, auto-generate changelog entry from commits
if [[ "$BUMP_TYPE" == "patch" ]]; then
    log_info "Generating patch notes from git commits..."

    # Get commits since last tag
    LAST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "")

    if [[ -n "$LAST_TAG" ]]; then
        COMMITS=$(git log --oneline "$LAST_TAG"..HEAD --no-merges 2>/dev/null || echo "")
    else
        COMMITS=$(git log --oneline -10 --no-merges 2>/dev/null || echo "")
    fi

    if [[ -z "$COMMITS" ]]; then
        log_warn "No commits found since last tag"
    else
        log_info "Commits to include:"
        echo "$COMMITS"
    fi
fi

# Confirmation
echo ""
read -p "Proceed with version bump to $NEW_VERSION? [y/N] " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    log_info "Aborted."
    exit 0
fi

# Update VERSION file
echo "$NEW_VERSION" > "$VERSION_FILE"
log_success "Updated VERSION file"

# Keep pyproject.toml version in sync with VERSION (single source of truth)
ROOT_PYPROJECT="$PROJECT_ROOT/pyproject.toml"
if [[ -f "$ROOT_PYPROJECT" ]]; then
    sed -i.bak -E "s/^version = \"[^\"]+\"/version = \"$NEW_VERSION\"/" "$ROOT_PYPROJECT"
    rm -f "$ROOT_PYPROJECT.bak"
    log_success "Updated version in pyproject.toml"
fi

# Update CHANGELOG.md - move [Unreleased] to new version
if [[ "$BUMP_TYPE" == "major" ]] || [[ "$BUMP_TYPE" == "minor" ]]; then
    TODAY=$(date +%Y-%m-%d)

    # Create new changelog content
    sed -i.bak "s/## \[Unreleased\]/## [Unreleased]\n\n---\n\n## [$NEW_VERSION] - $TODAY/" "$CHANGELOG_FILE"
    rm -f "$CHANGELOG_FILE.bak"

    # Add version link at bottom
    echo "[$NEW_VERSION]: https://github.com/qosha1/quinn-ai/compare/v${CURRENT_VERSION}...v${NEW_VERSION}" >> "$CHANGELOG_FILE"

    log_success "Updated CHANGELOG.md"
fi

# Run tests before tagging
log_info "Running tests..."
if command -v systemeval &> /dev/null; then
    if ! systemeval test; then
        log_error "Tests failed! Reverting version bump."
        echo "$CURRENT_VERSION" > "$VERSION_FILE"
        exit 1
    fi
else
    log_warn "systemeval not found, skipping tests"
fi

# Stage changes
git add VERSION CHANGELOG.md pyproject.toml
if [[ -d "$RELEASE_NOTES_DIR" ]]; then
    git add "$RELEASE_NOTES_DIR/"
fi

log_success "Staged version files"

# Create commit message
COMMIT_MSG="chore: bump version to $NEW_VERSION"

echo ""
log_info "Ready to commit and tag."
log_info "Commit message: $COMMIT_MSG"
log_info "Tag: v$NEW_VERSION"
echo ""
read -p "Create commit and tag? [y/N] " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    log_info "Files staged but not committed. Run manually:"
    echo "  git commit -m \"$COMMIT_MSG\""
    echo "  git tag -a v$NEW_VERSION -m \"Release v$NEW_VERSION\""
    exit 0
fi

# Commit
git commit -m "$COMMIT_MSG"
log_success "Created commit"

# Create annotated tag
git tag -a "v$NEW_VERSION" -m "Release v$NEW_VERSION"
log_success "Created tag v$NEW_VERSION"

echo ""
log_success "Version bumped to $NEW_VERSION"
echo ""
log_info "Next steps:"
echo "  1. Review the commit: git show HEAD"
echo "  2. Push changes: git push origin main"
echo "  3. Push tag: git push origin v$NEW_VERSION"
echo ""
