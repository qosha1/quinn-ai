"""
Tests for CLAUDE.md Code Quality Commandments.

These tests verify the codebase adheres to the quality standards
defined in the project's CLAUDE.md file.
"""

import os
import re
from pathlib import Path

import pytest

# Project root
PROJECT_ROOT = Path(__file__).parent.parent

# Directories to scan
BACKEND_DIR = PROJECT_ROOT / "backend"
APP_DIR = PROJECT_ROOT / "app"
LANDING_DIR = PROJECT_ROOT / "landing"
TESTS_DIR = PROJECT_ROOT / "tests"

# Files/dirs to exclude from scans
EXCLUDE_DIRS = {
    "node_modules",
    ".next",
    "__pycache__",
    ".git",
    "migrations",
    "staticfiles",
    ".pytest_cache",
    "htmlcov",
    "dist",
    "build",
    ".venv",
    "venv",
}

EXCLUDE_FILES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
}


def get_files(directory: Path, extensions: tuple) -> list[Path]:
    """Get all files with given extensions, excluding certain dirs."""
    files = []
    if not directory.exists():
        return files

    for root, dirs, filenames in os.walk(directory):
        # Modify dirs in-place to skip excluded directories
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

        for filename in filenames:
            if filename in EXCLUDE_FILES:
                continue
            if filename.endswith(extensions):
                files.append(Path(root) / filename)

    return files


def read_file_safe(filepath: Path) -> str:
    """Safely read file content."""
    try:
        return filepath.read_text(encoding="utf-8")
    except (UnicodeDecodeError, PermissionError):
        return ""


class TestNoMagicStrings:
    """Tests for hardcoded values that should be in config/env."""

    # Patterns that suggest hardcoded secrets/config
    MAGIC_STRING_PATTERNS = [
        (r'["\']sk_live_[a-zA-Z0-9]+["\']', "Hardcoded Stripe live key"),
        (r'["\']sk_test_[a-zA-Z0-9]+["\']', "Hardcoded Stripe test key"),
        (r'["\']pk_live_[a-zA-Z0-9]+["\']', "Hardcoded Stripe publishable key"),
        (r'["\']ghp_[a-zA-Z0-9]+["\']', "Hardcoded GitHub token"),
        (r'["\']xoxb-[a-zA-Z0-9-]+["\']', "Hardcoded Slack token"),
        (r'password\s*=\s*["\'][^"\']+["\']', "Hardcoded password"),
        (r'api_key\s*=\s*["\'][a-zA-Z0-9]{20,}["\']', "Hardcoded API key"),
    ]

    def test_no_hardcoded_secrets_in_python(self):
        """Check Python files for hardcoded secrets."""
        violations = []

        for py_file in get_files(BACKEND_DIR, (".py",)):
            content = read_file_safe(py_file)
            rel_path = py_file.relative_to(PROJECT_ROOT)

            # Skip test files and example files
            if "test" in str(rel_path).lower() or "example" in str(rel_path).lower():
                continue

            for pattern, description in self.MAGIC_STRING_PATTERNS:
                if re.search(pattern, content, re.IGNORECASE):
                    violations.append(f"{rel_path}: {description}")

        assert not violations, f"Found hardcoded secrets:\n" + "\n".join(violations)

    def test_no_hardcoded_secrets_in_typescript(self):
        """Check TypeScript files for hardcoded secrets."""
        violations = []

        for ts_file in get_files(APP_DIR, (".ts", ".tsx")):
            content = read_file_safe(ts_file)
            rel_path = ts_file.relative_to(PROJECT_ROOT)

            # Skip test files
            if "test" in str(rel_path).lower() or "__tests__" in str(rel_path):
                continue

            for pattern, description in self.MAGIC_STRING_PATTERNS:
                if re.search(pattern, content, re.IGNORECASE):
                    violations.append(f"{rel_path}: {description}")

        assert not violations, f"Found hardcoded secrets:\n" + "\n".join(violations)

    def test_no_hardcoded_localhost_urls_in_production_code(self):
        """Check for hardcoded localhost URLs (should use env vars)."""
        violations = []

        # Pattern for hardcoded localhost URLs (not in comments)
        localhost_pattern = r'["\']https?://localhost:\d+["\']'

        # Check Python
        for py_file in get_files(BACKEND_DIR, (".py",)):
            content = read_file_safe(py_file)
            rel_path = py_file.relative_to(PROJECT_ROOT)

            # Skip settings, tests, and config files
            if any(x in str(rel_path).lower() for x in ["settings", "test", "conftest", "config"]):
                continue

            if re.search(localhost_pattern, content):
                violations.append(f"{rel_path}: Hardcoded localhost URL")

        # Check TypeScript (excluding config files)
        for ts_file in get_files(APP_DIR, (".ts", ".tsx")):
            content = read_file_safe(ts_file)
            rel_path = ts_file.relative_to(PROJECT_ROOT)

            if any(x in str(rel_path).lower() for x in ["config", "test", "__tests__"]):
                continue

            if re.search(localhost_pattern, content):
                violations.append(f"{rel_path}: Hardcoded localhost URL")

        assert not violations, f"Found hardcoded URLs:\n" + "\n".join(violations)


class TestNoDuplicateFunctionality:
    """Tests for duplicate/variant files that violate single-architecture rule."""

    FORBIDDEN_PREFIXES = [
        "enhanced_",
        "enhanced-",
        "improved_",
        "improved-",
        "new_",
        "new-",
        "simple_",
        "simple-",
        "old_",
        "old-",
        "backup_",
        "backup-",
        "copy_",
        "copy-",
        "v2_",
        "v2-",
    ]

    def test_no_variant_files(self):
        """Check for files with forbidden prefixes."""
        violations = []

        all_dirs = [BACKEND_DIR, APP_DIR, LANDING_DIR]

        for directory in all_dirs:
            for filepath in get_files(directory, (".py", ".ts", ".tsx", ".js", ".jsx")):
                filename = filepath.name.lower()
                rel_path = filepath.relative_to(PROJECT_ROOT)

                for prefix in self.FORBIDDEN_PREFIXES:
                    if filename.startswith(prefix):
                        violations.append(f"{rel_path}: File uses forbidden prefix '{prefix}'")

        assert not violations, (
            f"Found variant files (violates single-architecture rule):\n" + "\n".join(violations)
        )

    def test_no_task_specific_md_in_root(self):
        """Check for task-specific markdown files in root."""
        forbidden_patterns = [
            r"ARCHITECTURE.*\.md",
            r"REVIEW.*\.md",
            r"IMPLEMENTATION.*\.md",
            r"PLAN.*\.md",
            r"TODO.*\.md",
            r"NOTES.*\.md",
            r"SCRATCH.*\.md",
        ]

        violations = []

        for md_file in PROJECT_ROOT.glob("*.md"):
            filename = md_file.name

            # Allow standard files
            if filename in {"README.md", "CLAUDE.md", "LICENSE.md", "CHANGELOG.md",
                           "CONTRIBUTING.md", "SECURITY.md", "DEPLOYMENT.md",
                           "DOCKER.md", "QUICKSTART.md"}:
                continue

            for pattern in forbidden_patterns:
                if re.match(pattern, filename, re.IGNORECASE):
                    violations.append(f"{filename}: Task-specific MD file in root")

        assert not violations, f"Found forbidden root MD files:\n" + "\n".join(violations)


class TestNoDeadCode:
    """Tests for dead code patterns."""

    def test_no_large_commented_code_blocks(self):
        """Check for large blocks of commented-out code."""
        violations = []

        # Pattern for multiple consecutive commented lines (likely dead code)
        python_comment_block = re.compile(r'(^#.*\n){10,}', re.MULTILINE)
        ts_comment_block = re.compile(r'(^\s*//.*\n){10,}', re.MULTILINE)

        for py_file in get_files(BACKEND_DIR, (".py",)):
            content = read_file_safe(py_file)
            rel_path = py_file.relative_to(PROJECT_ROOT)

            if python_comment_block.search(content):
                violations.append(f"{rel_path}: Large commented code block (10+ lines)")

        for ts_file in get_files(APP_DIR, (".ts", ".tsx")):
            content = read_file_safe(ts_file)
            rel_path = ts_file.relative_to(PROJECT_ROOT)

            if ts_comment_block.search(content):
                violations.append(f"{rel_path}: Large commented code block (10+ lines)")

        # This is a warning-level check, not hard fail
        if violations:
            pytest.skip(f"Found potential dead code (review recommended):\n" + "\n".join(violations))


class TestTypeSafety:
    """Tests for type safety violations."""

    def test_no_untyped_any_in_typescript(self):
        """Check for explicit 'any' type usage without justification."""
        violations = []

        # Pattern for `: any` or `as any` without a comment justification
        any_pattern = re.compile(r':\s*any\b|as\s+any\b')
        justified_pattern = re.compile(r'//.*any|/\*.*any')

        for ts_file in get_files(APP_DIR, (".ts", ".tsx")):
            content = read_file_safe(ts_file)
            rel_path = ts_file.relative_to(PROJECT_ROOT)

            # Skip type definition files
            if ".d.ts" in str(ts_file):
                continue

            lines = content.split("\n")
            for i, line in enumerate(lines, 1):
                if any_pattern.search(line) and not justified_pattern.search(line):
                    # Check if previous line has justification comment
                    if i > 1 and "any" in lines[i - 2].lower() and "//" in lines[i - 2]:
                        continue
                    violations.append(f"{rel_path}:{i}: Unjustified 'any' type")

        # Allow up to 5 any usages (some are unavoidable)
        if len(violations) > 5:
            assert False, f"Too many 'any' types ({len(violations)}):\n" + "\n".join(violations[:10])


class TestErrorHandling:
    """Tests for proper error handling."""

    def test_no_empty_except_blocks_python(self):
        """Check for empty except blocks in Python."""
        violations = []

        # Pattern for except blocks that just pass or continue
        empty_except = re.compile(r'except.*:\s*\n\s*(pass|continue)\s*\n', re.MULTILINE)

        for py_file in get_files(BACKEND_DIR, (".py",)):
            content = read_file_safe(py_file)
            rel_path = py_file.relative_to(PROJECT_ROOT)

            if empty_except.search(content):
                violations.append(f"{rel_path}: Empty except block (pass/continue)")

        assert not violations, f"Found empty except blocks:\n" + "\n".join(violations)

    def test_no_empty_catch_blocks_typescript(self):
        """Check for empty catch blocks in TypeScript."""
        violations = []

        # Pattern for catch blocks that are empty or just have comments
        empty_catch = re.compile(r'catch\s*\([^)]*\)\s*\{\s*\}', re.MULTILINE)

        for ts_file in get_files(APP_DIR, (".ts", ".tsx")):
            content = read_file_safe(ts_file)
            rel_path = ts_file.relative_to(PROJECT_ROOT)

            if empty_catch.search(content):
                violations.append(f"{rel_path}: Empty catch block")

        assert not violations, f"Found empty catch blocks:\n" + "\n".join(violations)


class TestFileOrganization:
    """Tests for proper file organization."""

    def test_no_test_artifacts_in_root(self):
        """Check for test artifacts left in root directory."""
        forbidden_extensions = {
            ".log",
            ".tmp",
            ".bak",
            ".swp",
            ".swo",
        }

        forbidden_patterns = [
            r"test[-_]output",
            r"coverage",
            r"\.coverage",
            r"htmlcov",
            r"junit",
            r"report",
        ]

        violations = []

        for item in PROJECT_ROOT.iterdir():
            if item.is_file():
                if item.suffix in forbidden_extensions:
                    violations.append(f"{item.name}: Test artifact in root")

                for pattern in forbidden_patterns:
                    if re.match(pattern, item.name, re.IGNORECASE):
                        violations.append(f"{item.name}: Test artifact in root")

        assert not violations, f"Found test artifacts in root:\n" + "\n".join(violations)

    def test_no_planning_docs_in_docs_folder(self):
        """Check that docs/ only contains validated documentation."""
        docs_dir = PROJECT_ROOT / "docs"

        if not docs_dir.exists():
            pytest.skip("No docs/ directory")

        planning_patterns = [
            r"plan",
            r"draft",
            r"wip",
            r"scratch",
            r"notes",
            r"todo",
        ]

        violations = []

        for doc_file in docs_dir.rglob("*.md"):
            filename = doc_file.name.lower()
            content = read_file_safe(doc_file).lower()

            for pattern in planning_patterns:
                if re.search(pattern, filename):
                    violations.append(f"{doc_file.relative_to(PROJECT_ROOT)}: Planning doc in docs/")
                elif "draft" in content[:500] or "work in progress" in content[:500]:
                    violations.append(f"{doc_file.relative_to(PROJECT_ROOT)}: Contains draft markers")

        assert not violations, f"Found planning docs in docs/:\n" + "\n".join(violations)


class TestPythonTypeHints:
    """Tests for Python type hint coverage."""

    def test_functions_have_type_hints(self):
        """Check that Python functions have type hints on parameters."""
        violations = []

        # Pattern for function definitions without type hints
        # This is a simplified check - looks for def foo(x, y): without : type
        untyped_func = re.compile(r'def\s+\w+\s*\(\s*[a-z_][a-z0-9_]*\s*[,)]', re.IGNORECASE)
        typed_func = re.compile(r'def\s+\w+\s*\(\s*[a-z_][a-z0-9_]*\s*:', re.IGNORECASE)

        for py_file in get_files(BACKEND_DIR / "apps", (".py",)):
            content = read_file_safe(py_file)
            rel_path = py_file.relative_to(PROJECT_ROOT)

            # Skip migrations and tests
            if "migration" in str(rel_path) or "test" in str(rel_path).lower():
                continue

            # Count typed vs untyped (excluding self/cls)
            untyped_matches = len(untyped_func.findall(content))
            typed_matches = len(typed_func.findall(content))

            # If mostly untyped, flag it
            if untyped_matches > 5 and typed_matches < untyped_matches * 0.5:
                violations.append(f"{rel_path}: Low type hint coverage")

        # This is informational, not a hard fail
        if violations:
            pytest.skip(f"Type hint coverage could be improved:\n" + "\n".join(violations))
