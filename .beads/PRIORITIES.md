# QuinnAI Work Priorities

**Generated**: 2026-01-23
**Status**: 128 open, 603 closed, 125 ready to work

## Current State Summary

The core system is **functional and tested** (1081 tests passing):
- CLI commands: 100% implemented (`qn org`, `qn wrkr`, `qn board`)
- Providers: Anthropic + OpenAI implemented and working
- Budget system: Complete with enforcement
- Session management: Working with tmux integration
- Board UI: Terminal app working with multi-org support

## Priority Order

### 1. PACKAGING (Blocked Chain) - Do First
These form a dependency chain that must be done in order:

```
quinnai-v4pq: Cross-Platform Binary Compilation
    ↓
quinnai-kdxu: Python Wheel with Embedded Binary
    ↓
quinnai-chhz: Automated Version Tagging
    ↓
quinnai-8vu0: Create install.sh Script
```

**Why First**: Can't distribute the product without packaging.

### 2. EPICS (Future Features) - Prioritize by Value

| Epic | Description | Priority |
|------|-------------|----------|
| quinnai-xo12 | DI & Config Wiring (2/5 tasks left) | HIGH - Architecture foundation |
| quinnai-lpdq | Escalation System (1/4 tasks left) | HIGH - Nearly done |
| quinnai-5dhh | Session Resource Monitoring | MEDIUM - Ops quality |
| quinnai-o0cb | Worker Storage Lifecycle | MEDIUM - Per CLAUDE.md design |
| quinnai-il1g | CLI Adapter System | LOW - Only need more providers |
| quinnai-70wl | Shared Configuration Types | LOW - Nice to have |

### 3. TESTING (8 items) - Ongoing
Test coverage expansion for untested modules:
- authorization.py
- quality.py (1039 lines!)
- MessagingService
- Integration tests
- Fixtures cleanup

### 4. REFACTORING (8 items) - As Needed
Service extraction and code organization:
- OrgChartService
- WorkerSessionService
- StateSync service
- Event centralization
- etc.

### 5. CODE QUALITY (4 items) - Backlog
- Type annotations
- Error handling patterns
- Naming conventions
- Docstrings

### 6. PERFORMANCE (3 items) - Backlog
- Query caching
- Git batching
- Large file chunking

## Recommended Execution Order

1. **quinnai-v4pq** - Cross-platform binary (unblocks packaging chain)
2. **quinnai-lpdq.4** - Wire EscalationManager (finishes escalation epic)
3. **quinnai-xo12.4 + xo12.5** - Workflow config (finishes DI epic)
4. Pick up testing tasks as you work on related code
5. Refactoring tasks can be done opportunistically

## Test Infrastructure (quinnai-cfox)

The systemeval integration epic covers testing across ALL sub-apps:
- **CLI**: Working (1081 tests, pytest)
- **Backend**: Django test integration needed
- **Frontend**: Vitest integration needed
- **E2E**: Playwright integration needed
- **Landing**: No tests yet

This is good-to-have but NOT blocking. Current CLI tests provide solid coverage.

## Commands

```bash
# See ready work
bd ready

# See blocked work
bd blocked

# Check specific epic
bd show <epic-id>

# Start work
bd update <id> --status=in_progress
```
