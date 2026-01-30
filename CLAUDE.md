# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## 🎯 CRITICAL: Understanding What QuinnAI Is

**QuinnAI is the COMPUTER, not the software that runs on it.**

### The Two Layers

1. **QuinnAI (THIS REPO) = The Platform/Computer**
   - We are building the system that manages AI organizations
   - Our beads track work on QuinnAI itself (CLI features, bug fixes, architecture)
   - Location: `/Users/qosha/Repos/small-bizs/agentic-tools/quinnai/`
   - Beads: `.beads/` in repo root (QuinnAI development work)

2. **Orgs/Projects (~/orgs/*) = Software/Applications**
   - Created BY QuinnAI using `qn org init`
   - Each org is a separate project with its own goals and beads
   - Example: `~/orgs/acme` is Acme's project, not QuinnAI work
   - Beads: `.beads/` in each org dir (that org's project work)

### Examples to Clarify

**QuinnAI Beads (this repo):**
- "Add qn org config set-provider command" ← QuinnAI feature
- "Fix default providers.yaml template" ← QuinnAI bug
- "Remove redundant --ceo-role parameter" ← QuinnAI CLI improvement

**Acme Org Beads (~/orgs/acme):**
- "Implement user authentication for Acme app" ← Acme's project work
- "Add dark mode to Acme dashboard" ← Acme's feature
- "Fix bug in Acme checkout flow" ← Acme's bug

### Never Confuse the Layers

❌ **WRONG:** Create QuinnAI platform bugs in an org's beads
✅ **RIGHT:** QuinnAI platform work goes in QuinnAI's beads

❌ **WRONG:** Track Acme project work in QuinnAI's beads
✅ **RIGHT:** Acme project work goes in Acme's beads

**When in doubt:** If the issue is about QuinnAI's code (CLI, session management, org init, etc.), it belongs in QuinnAI's beads. If it's about a specific org's project goals, it belongs in that org's beads.

---

## 🚨 Code Quality Commandments (MANDATORY)

### Test Before Respond
**Before EVERY response that modifies code, run the appropriate test suite:**

```bash
# QuinnAI is Python - run pytest
python -m pytest cli/tests/
python -m pytest shared/tests/
python -m pytest terminal-app/tests/

# Or use systemeval if available
systemeval test
```

Do NOT mark tasks complete until tests pass.

### Test-Driven Bug Fixing Process

⏺ **The Process**

1. **Investigate Why Tests Missed It**
   - Examine existing tests
   - Find gaps: what scenarios aren't covered?
   - Identify missing edge cases, timing issues, or state combinations

2. **Write Test That FAILS**
   - Create test that reproduces the exact failure scenario
   - Run it - watch it FAIL
   - Failure proves bug exists

3. **Fix The Code**
   - Implement the fixes
   - Keep it simple
   - Address root cause, not symptoms

4. **Test Now PASSES**
   - Same test, no changes
   - Run it - watch it PASS
   - Success proves bug is fixed

⏺ **The Philosophy**

**Never fix a bug you can't reproduce in a test.**

If you can't make a test FAIL, you don't understand the bug. If the test doesn't PASS after your fix, you didn't fix it. The test is proof both ways.

That's it. Everything else is noise.

### No Magic Strings
- All configuration values must come from environment variables or config files
- No hardcoded URLs, API keys, secrets, or environment-specific values in code
- Use constants for repeated string literals (see `cli/core/constants.py`)

### No Duplicate Functionality
- One codebase, one architecture
- Work within existing structures - extend, don't duplicate
- No `enhanced-*`, `improved-*`, `new-*`, or `simple-*` file variants
- Before creating a new file, verify similar functionality doesn't exist

### No Dead Code
- Remove unused imports, functions, and variables
- No commented-out code blocks (use git history)
- No `# TODO` without an associated beads issue

### Type Safety
- Python: type hints on all function signatures
- Use `from typing import` annotations
- No implicit type coercion in comparisons

### Error Handling
- No silent failures - log or propagate errors
- No empty except blocks
- Validate inputs at system boundaries
- Use specific exception classes (see `shared/exceptions.py`)

### File Management
- **DO NOT WRITE MD FILES** - No planning docs, architecture reviews, analysis files, etc.
  - MD files get stale and wrong quickly
  - Use beads for task tracking, not markdown files
  - Use code comments for implementation notes
  - Only exception: updating existing docs after code is validated and tested
- Never create task-specific MD files in root (no `ARCHITECTURE_REVIEW.md`, etc.)
- `docs/*` is for validated, tested documentation only - no planning docs
- No test output files (logs, snapshots) in root directory
- Use scratchpad directory for temporary analysis if absolutely necessary

### Commit Discipline
- No "Co-Authored-By" lines
- No hyperbolic language ("critical fix", "important update")
- Atomic commits - one logical change per commit

---

## QuinnAI Project Truth

**QuinnAI is a hierarchical AI organization management system.**

It's NOT:
- A Claude Code wrapper (it's CLI-agnostic)
- A Django/NextJS app (it's a Python CLI tool)
- A B2B SaaS template (it's open-source tooling)

It IS:
- Python CLI tool (`qn` command)
- Terminal UI dashboard (`qn board ui`)
- Multi-worker AI organization orchestration
- Session provider abstraction (supports claude_code, cursor, aider, etc.)
- Beads-based work tracking integration

---

## Architecture Overview

### Project Structure

```
quinnai/
├── cli/                    # QuinnAI CLI (`qn` command)
│   ├── commands/           # Click command groups
│   │   ├── org/            # Org lifecycle (init, start, stop, status, hire, fire)
│   │   └── wrkr/           # Worker operations
│   ├── core/               # Core business logic
│   │   ├── constants.py    # ALL magic values go here
│   │   ├── db.py           # Database layer
│   │   ├── worker.py       # Worker state machine
│   │   ├── org.py          # Org state machine
│   │   ├── session.py      # Session abstraction
│   │   ├── onboarding.py   # Worker onboarding system
│   │   └── storage.py      # Hierarchical storage manager
│   ├── config/             # Default configs and templates
│   └── tests/              # Pytest tests
├── shared/                 # Shared business logic
│   ├── exceptions.py       # All custom exceptions
│   ├── state_machines.py   # State transition rules
│   └── enums.py            # Enums (OrgStatus, RuntimeStatus, etc.)
├── terminal-app/           # TUI dashboard (Textual)
└── example_orgs/           # Example org configurations
```

### Core Concepts

**Organization (Org):**
- Lifecycle: UNINITIALIZED → INITIALIZED → RUNNING ⇄ STOPPED
- Has CEO, teams, workers
- Manages shared storage and communication channels

**Worker:**
- Dual state machines:
  - Lifecycle: pending → onboarding → active → offboarding → terminated
  - Runtime: starting → running ⇄ idle → stopped/crashed
- Has hierarchical storage: `storage/workers/{org-chart-path}/{worker-id}/`
- Has onboarding materials: BRIEFING.md, STORAGE.md, WELCOME.md

**Session:**
- Abstract interface for AI CLI sessions
- Providers: claude_code, cursor, aider (extensible)
- Registry pattern for provider selection
- 1:1 relationship with worker

**Storage:**
- Hierarchical worker storage mirrors org-chart
  - CEO: `workers/ceo/`
  - Director: `workers/ceo/director-{id}/`
  - Engineer: `workers/ceo/director-{id}/engineer-{id}/`
- Shared storage: `shared/topics/{topic}/`, `shared/teams/{team}/`
- Environment variables: `$WORKER_STORAGE`, `$SHARED_STORAGE` (absolute paths)

**Beads:**
- Work tracking system (issues, tasks, OKRs)
- Org-aware with permissions
- JSONL-backed with SQLite cache
- Integrated with bd CLI

---

## CRITICAL: No Provider Lock-in (Architectural Law)

**WE define the interfaces. Providers implement OUR contracts. Never the reverse.**

### Anti-patterns (NEVER do this):
- "Build AI service" → "Build OpenAI SDK wrapper" ❌
- "Build workflow system" → "Build Claude-to-Claude handoff" ❌
- "Build terminal manager" → "Custom scripts for one machine" ❌

### Correct pattern (ALWAYS do this):
```
Our Abstract Interface (we define)
        ↓
Provider Adapter (they implement our contract)
        ↓
[claude_code, cursor, aider, etc.] ← swappable via config
```

**Every external dependency gets wrapped in OUR abstraction:**
- `SessionInterface` base class → `ClaudeCodeSession`, `CursorSession` adapters
- `StorageProvider` base class → `LocalStorage`, `S3Storage` adapters
- Never import provider-specific code outside adapter modules

**Config-driven provider selection. Zero code changes to swap providers.**

---

## Learned Anti-Patterns (Applied to QuinnAI)

### 1. No Magic Strings, Values, or Numbers. EVER.
**Violation:** `/workspace`, `.beads/`, `timeout=30`, `max_retries=3`, port numbers, directory names buried in code.
**Result:** Cannot configure without code changes, values scattered and inconsistent.
**Fix:** ALL values go in `cli/core/constants.py`. Zero literals in function bodies.

**QuinnAI Example:**
```python
# BAD
timeout = 60
worker_dir = org_path / "storage" / "workers" / worker_id

# GOOD
from cli.core.constants import DEFAULT_TIMEOUT
timeout = DEFAULT_TIMEOUT
worker_dir = storage_manager.get_worker_path(worker_id)
```

### 2. Configuration Discovery Instead of Explicit Injection
**Violation:** Searching cwd and parent dirs for config files, env var expansion magic.
**Result:** Two processes with different cwd get different configs silently.
**Fix:** Configuration is passed explicitly at startup. No discovery. No magic.

### 3. Module-Level Side Effects
**Violation:** `_register_builtins()` called at import, global instances created on module load.
**Result:** Cannot control initialization order, tests pollute each other.
**Fix:** Explicit `initialize()` calls. No code runs at import time except definitions.

### 4. String-Based Dispatch Instead of Polymorphism
**Violation:** `if provider == "claude": ... elif provider == "openai": ...` scattered everywhere.
**Result:** Adding providers means editing core code, typos cause silent failures.
**Fix:** Provider classes implement interface. Registry returns instance. Zero string matching in business logic.

**QuinnAI Example:**
```python
# BAD
if provider == "claude_code":
    session = spawn_claude_code_session(...)
elif provider == "cursor":
    session = spawn_cursor_session(...)

# GOOD
registry = get_default_registry()
adapter = registry.get(provider)
session = adapter.spawn(config)
```

### 5. Direct Instantiation Instead of Injection
**Violation:** `WorkerQueue(self.worker_dir)` created inside classes that use them.
**Result:** Cannot swap implementations, cannot test in isolation.
**Fix:** Dependencies passed to constructors. Factories create configured instances.

### 6. Implementation-Shaped "Interfaces"
**Violation:** Interface shaped around specific implementation details.
**Result:** Interface exists but can't swap implementations.
**Fix:** Design interface FIRST as a true contract. Build as if there will be 10 providers.

### 7. Cascading Configuration Fallbacks
**Violation:** Check settings → check overrides → check env vars → check defaults → silent fallback.
**Result:** Debugging requires tracing 100+ lines of fallback logic.
**Fix:** Explicit required vs optional. Fail fast on missing required config. One source of truth.

### 8. Infrastructure Leaking Into Business Logic
**Violation:** Docker container states in session lifecycle, ANSI stripping in agent code.
**Result:** Business logic cannot run outside specific infrastructure.
**Fix:** Infrastructure behind adapters. Business logic is pure.

---

## Development Workflow

### Running Tests

```bash
# All tests
python -m pytest

# Specific test file
python -m pytest cli/tests/test_worker.py

# Specific test
python -m pytest cli/tests/test_worker.py::test_worker_lifecycle

# With coverage
python -m pytest --cov=cli --cov=shared
```

### Working with Beads

```bash
# List work
bd list --status=open --priority=0,1

# Find ready work
bd ready

# Claim work
bd update <bead-id> --status=in_progress

# Close work
bd close <bead-id> --reason "Description of what was done"

# Sync with remote
bd sync
```

### OKRs vs Operational Work

QuinnAI distinguishes between strategic objectives and day-to-day work:

**OKRs (Strategic):**
- Quarterly objectives with measurable key results
- Type: `epic`, Label: `okr`
- Created by CEO/managers
- Example: "Q1 2026: Build Core Data Infrastructure - 60/100 sources operational"

**Operational Work (Daily):**
- Tasks, bugs, features that advance OKRs
- Type: `task`, `bug`, `feature`
- Created by all developers
- Should link to parent OKR via `serves` dependency

**Query OKRs:**
```bash
bd list --label=okr              # List all OKRs
qn org okr list --from-db        # Show progress/key results
```

**Query operational work:**
```bash
bd list --type=task,bug,feature --status=open
bd ready                         # Show available work
```

**Link work to OKRs:**
```bash
# When creating work
bd create "Implement feature X" --type=task --deps "serves:<okr-id>"

# Link existing work
bd dep add <task-id> <okr-id>   # task serves okr
```

**Update OKR progress (when code affects key results):**
```bash
qn org okr list --from-db                          # Check current progress
qn org okr update-kr <okr-id> --metric="..." --current=X  # Update metric
```

**Example workflow:**
```bash
# 1. Check what OKR your work serves
bd show <task-id>  # Look for "serves" dependency

# 2. Do the work and verify key results
# If KR is "test coverage > 80%", run coverage tool
# If KR is "performance < 2s", measure performance

# 3. Update OKR progress if metrics changed
qn org okr update-kr quinnai-q1-infra --metric="sources" --current=65

# 4. Close work only if key results are met
bd close <task-id> --reason "Implemented feature, coverage now 85%"
```

### Org Operations

```bash
# Initialize org
qn org init --ceo-name="Alice" --ceo-role="CEO"

# Start org (activates CEO)
qn org start

# Check status
qn org status

# Stop org (graceful shutdown)
qn org stop --graceful-timeout=30

# Hire worker
qn org hire --name="Bob" --role="Engineer" --manager=ceo

# Fire worker
qn org fire worker-id --reason="Performance"
```

### Session Providers

Configure in `org/config/providers.yaml`:
```yaml
providers:
  claude_code:
    enabled: true
    model: claude-sonnet-4-5
    api_key_env: ANTHROPIC_API_KEY

  cursor:
    enabled: true
    model: gpt-4
    api_key_env: OPENAI_API_KEY
```

---

## Key Design Decisions (ADRs)

See `docs/architecture-decisions/` for full details:

- **ADR 001**: Storage architecture (hierarchical paths mirror org-chart)
- **ADR 002**: Worker onboarding 3-layer system (files + env vars + working dir)
- **ADR 003**: Onboarding modifies session spawn (env vars provide runtime identity)
- **ADR 004**: Use absolute paths in environment variables (convenience over portability)

---

## Constants Pattern

ALL magic values go in `cli/core/constants.py`:

```python
# Timeouts (seconds)
DEFAULT_TIMEOUT = 60
DEFAULT_STARTUP_TIMEOUT = 30
DEFAULT_GRACEFUL_TIMEOUT = 30

# Bead types
BEAD_TYPE_TASK = "task"
BEAD_TYPE_BUG = "bug"
BEAD_TYPE_FEATURE = "feature"
BEAD_TYPE_ASK = "ask"

# Entity types
ENTITY_TYPE_WORKER = "worker"
ENTITY_TYPE_ORG = "org"
ENTITY_TYPE_SESSION = "session"

# Permission levels
PERM_LEVEL_READ = 1
PERM_LEVEL_WRITE = 3
PERM_LEVEL_ADMIN = 5
```

Never hardcode these values anywhere else. Import from constants.

---

## Exception Hierarchy

See `shared/exceptions.py` for all custom exceptions:

```
Exception
├── InvalidStateTransition
├── InvalidOrgTransition
├── WorkerNotFound
├── OrgStartError
│   ├── OrgStructureError
│   ├── SessionSpawnError
│   └── SessionStartTimeout
└── ConfigurationError
```

Use specific exceptions, not generic `Exception` or `ValueError`.

---

## State Machines

Defined in `shared/state_machines.py`:

- `ORG_TRANSITIONS`: Valid org state transitions
- `LIFECYCLE_TRANSITIONS`: Worker lifecycle transitions
- `RUNTIME_TRANSITIONS`: Worker runtime transitions
- `LIFECYCLE_STATES`: Per-bead-type lifecycle states

Never modify state without checking valid transitions.

---

## Testing Requirements

- All new code must have tests
- Test files in `cli/tests/`, `shared/tests/`
- Use pytest fixtures for common setup
- Mock external dependencies (don't hit real APIs)
- Test both happy path and error cases

Example test structure:
```python
def test_worker_lifecycle_transition(db, org, ceo):
    """Test valid worker lifecycle transition."""
    # Setup
    assert ceo.lifecycle_status == "pending"

    # Execute
    ceo.start_onboarding()

    # Verify
    assert ceo.lifecycle_status == "onboarding"
```

---

## Git Workflow

1. Work on beads task (bd ready)
2. Claim task (bd update <id> --status=in_progress)
3. Make changes
4. Run tests (pytest)
5. Commit with clear message
6. Close bead (bd close <id> --reason="...")
7. Sync beads (bd sync)
8. Push to remote (git push)

---

## Common Gotchas

**Path handling:**
- Always use `Path` from pathlib, never string concatenation
- Worker paths are hierarchical, use `StorageManager.get_worker_path()`
- Environment variables are absolute paths (ADR 004)

**Database:**
- SQLite is thread-safe but not process-safe
- Always use context managers or try/finally for db.close()
- Database path: `org_path / "live" / "quinn.db"`

**Sessions:**
- 1:1 relationship with worker (enforced by ActiveSessionExistsError)
- Session spawning goes through registry, never direct instantiation
- Sessions are provider-agnostic

**Workers:**
- Dual state machines (lifecycle + runtime) are independent
- Lifecycle transitions modify database (persistent)
- Runtime transitions are process state (volatile)

**Beads:**
- bd CLI is org-aware (uses org's .beads directory)
- Permissions are enforced on write operations
- Types must be valid (use constants from cli/core/constants.py)

---

## When to Create New Files

**DO create new files when:**
- Adding a new command group (commands/org/, commands/wrkr/)
- Adding a new session provider (core/sessions/new_provider.py)
- Adding a new module with distinct responsibility

**DON'T create new files when:**
- The functionality belongs in an existing module
- You want to "improve" existing code (edit it instead)
- Creating test-specific outputs (use temp dirs)

---

## Documentation Standards

- Docstrings for all public functions/classes
- Use Google-style docstrings
- Keep README.md updated with new features
- ADRs for architectural decisions (docs/architecture-decisions/)
- Design docs for complex features (docs/)

**Docstring example:**
```python
def spawn_worker_session(
    worker: Worker,
    provider: str,
    config: SessionConfig,
) -> None:
    """Spawn a session for a worker.

    Args:
        worker: Worker instance to spawn session for
        provider: Session provider name (claude_code, cursor, etc.)
        config: Session configuration

    Raises:
        SessionSpawnError: If session spawn fails
        ActiveSessionExistsError: If worker already has active session
    """
```

---

## Performance Considerations

- SQLite is fast for single-org use case
- Worker count limited by system resources (tmux sessions)
- Session spawning is expensive (LLM context setup)
- Beads JSONL is append-only (fast writes)

Don't prematurely optimize. Profile first.

---

## Security Considerations

- Never commit API keys or secrets
- Use environment variables for credentials
- Worker storage is isolated (hierarchical paths)
- Permissions enforced on beads operations
- Sessions run in user's context (no privilege escalation)

---

## Future-Proofing

When adding new features, ask:
1. Is this extensible? (can we add more providers/types later?)
2. Is this configurable? (no hardcoded values)
3. Is this testable? (dependencies injected, not instantiated)
4. Is this documented? (docstrings, ADRs if architectural)

Build for the system we want, not just today's requirements.
