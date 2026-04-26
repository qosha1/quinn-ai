"""Structural guardrail: cli/, shared/, terminal-app/ never import B2B-stack modules.

QuinnAI is provider-agnostic Python CLI tooling. It must not depend on Django,
DRF, Stripe SDKs, NextJS bridges, or env files from the deleted B2B template.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

SCAN_ROOTS = ["cli", "shared", "terminal-app"]

FORBIDDEN_IMPORT_PATTERNS = [
    re.compile(r"^\s*import\s+django(\s|\.|$)", re.MULTILINE),
    re.compile(r"^\s*from\s+django(\s|\.)", re.MULTILINE),
    re.compile(r"^\s*from\s+rest_framework(\s|\.)", re.MULTILINE),
    re.compile(r"^\s*import\s+stripe(\s|\.|$)", re.MULTILINE),
    re.compile(r"^\s*from\s+stripe(\s|\.)", re.MULTILINE),
    re.compile(r"^\s*from\s+backend\.", re.MULTILINE),
    re.compile(r"^\s*import\s+backend\.", re.MULTILINE),
]

FORBIDDEN_STRING_PATTERNS = [
    ".envs/.local/.django",
    ".envs/.local/.postgres",
]

FORBIDDEN_DEPS = [
    "django",
    "djangorestframework",
    "stripe",
    "psycopg",
    "psycopg2",
    "celery",
]


def _python_files() -> list[Path]:
    files: list[Path] = []
    for sub in SCAN_ROOTS:
        base = ROOT / sub
        if not base.exists():
            continue
        files.extend(base.rglob("*.py"))
    return files


@pytest.mark.parametrize("pattern", FORBIDDEN_IMPORT_PATTERNS, ids=lambda p: p.pattern)
def test_no_b2b_imports(pattern: re.Pattern) -> None:
    offenders: list[str] = []
    for path in _python_files():
        text = path.read_text(errors="ignore")
        if pattern.search(text):
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, (
        f"Files matching forbidden pattern {pattern.pattern!r}: {offenders}"
    )


@pytest.mark.parametrize("needle", FORBIDDEN_STRING_PATTERNS)
def test_no_b2b_envfile_references(needle: str) -> None:
    offenders: list[str] = []
    for path in _python_files():
        if needle in path.read_text(errors="ignore"):
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, f"Files referencing {needle!r}: {offenders}"


def test_pyproject_has_no_b2b_dependencies() -> None:
    text = (ROOT / "pyproject.toml").read_text().lower()
    matches = [dep for dep in FORBIDDEN_DEPS if dep in text]
    assert not matches, f"pyproject.toml lists B2B dependencies: {matches}"
