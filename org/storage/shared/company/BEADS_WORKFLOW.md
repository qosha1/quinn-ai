# Beads Workflow Guide

## What is Beads?

**Beads** is our work tracking system. Think of it as our issue tracker - tasks, bugs, features, and OKRs all live in beads.

## Core Commands

### Finding Work

```bash
# Show work ready to start (no blockers)
bd ready

# List all open work
bd list --status=open

# List by priority
bd list --status=open --priority=0,1

# List by type
bd list --type=task,bug

# Filter by team (when implemented)
bd list --status=open --team=engineering
```

### Working on Issues

```bash
# View full details
bd show <id>

# Claim work (sets you as assignee + in_progress)
bd update <id> --claim

# Update status manually
bd update <id> --status=in_progress

# Add notes
bd update <id> --notes="Working on DB pooling, found bottleneck in connection mgmt"

# Close when done
bd close <id> --reason="Implemented connection pooling, tests pass, p95 latency now 75ms"
```

### Creating Work

```bash
# Create a task
bd create --title="Fix memory leak in worker process" --type=task --priority=0 --description="Details here"

# Create a bug
bd create --title="Dashboard crashes on empty data" --type=bug --priority=1

# Create a feature
bd create --title="Add dark mode toggle" --type=feature --priority=2
```

### Dependencies

```bash
# Add dependency (A depends on B = B blocks A)
bd dep add <blocked-id> <blocker-id>

# Example: Task depends on setup being done
bd dep add my-task setup-complete

# Remove dependency
bd dep rm <blocked-id> <blocker-id>

# View blocked issues
bd blocked
```

### Syncing

```bash
# Sync with git remote (run at session end)
bd sync

# Check sync status
bd sync --status
```

## Issue Lifecycle

```
open → in_progress → closed
  ↓         ↓
 (ready)  (working)
```

**States:**
- `open` - Not started, available to claim
- `in_progress` - Someone is actively working on it
- `closed` - Complete

**Transitions:**
- `bd update <id> --claim` → Sets in_progress
- `bd close <id>` → Sets closed

## Issue Types

- **task** - Work to be done (default)
- **bug** - Something broken that needs fixing
- **feature** - New functionality to build
- **epic** - Large initiative containing many tasks (often used for OKRs)
- **chore** - Maintenance work (dependencies, cleanup)

## Priority Levels

- **P0** (0) - Critical, drop everything
- **P1** (1) - High priority, next up
- **P2** (2) - Medium priority
- **P3** (3) - Low priority
- **P4** (4) - Backlog

Use `--priority=0` or `--priority=P0` (both work).

## Labels

Labels categorize work:

```bash
# Add label
bd update <id> --add-label okr

# Add multiple
bd update <id> --add-label frontend --add-label ui

# Remove label
bd update <id> --remove-label wip

# List by label
bd list --label=okr
```

**Common labels:**
- `okr` - Strategic objective
- `frontend` - UI work
- `backend` - API/server work
- `testing` - Test-related
- `docs` - Documentation

## Best Practices

### 1. Claim Before Starting
```bash
# Good
bd update <id> --claim
# Work starts...

# Bad
# Start work without claiming
```

### 2. Close with Reason
```bash
# Good
bd close <id> --reason="Added pooling with max 20 connections, tested under load, p95 latency 75ms"

# Bad
bd close <id>  # No context
```

### 3. Link Dependencies
```bash
# If your task depends on another task, link them
bd dep add my-task dependency-task-id

# This prevents my-task from showing in bd ready until dependency is done
```

### 4. Use Priorities Correctly
- **P0:** Production down, security issue, blocking all work
- **P1:** Important, impacts release timeline
- **P2:** Should do this iteration
- **P3:** Nice to have
- **P4:** Future consideration

### 5. Keep Descriptions Updated
```bash
# If you discover something while working, add notes
bd update <id> --notes="Found that connection leak was caused by unclosed transactions"
```

### 6. Sync Regularly
```bash
# End of day / before stopping
bd sync
```

## Common Workflows

### Daily Standup
```bash
# What I worked on yesterday
bd list --status=closed --assignee=me

# What I'm working on today
bd list --status=in_progress --assignee=me

# Blockers
bd list --status=open --assignee=me | grep "Depends on"
```

### Finding Next Work
```bash
# 1. Check what's ready (no blockers)
bd ready

# 2. Pick highest priority
# (bd ready orders by priority)

# 3. Claim it
bd update <id> --claim

# 4. Check details
bd show <id>
```

### Unblocking Work
```bash
# Find what's blocked
bd blocked

# Complete blocking tasks first
bd close <blocker-id> --reason="..."

# Blocked work now appears in bd ready
```

### Sprint Planning
```bash
# See all open work
bd list --status=open --priority=0,1

# Create sprint epic
bd create --title="Sprint 5: Performance" --type=epic --priority=1

# Link tasks to epic
bd dep add sprint-epic task-1
bd dep add sprint-epic task-2

# Track progress
bd show sprint-epic  # See blocked tasks
```

## Troubleshooting

**Issue not appearing in `bd ready`?**
- Check if it's blocked: `bd show <id>` (look for "Depends on")
- Check status: Should be `open`, not `in_progress` or `closed`
- Check if already assigned: `bd ready` only shows unassigned work by default

**Can't close an issue?**
- Verify you're the assignee or have permission
- Check if issues block this one (can't close if it blocks open work)

**Sync conflicts?**
- Run `git status` to check for conflicts
- Resolve conflicts in `.beads/*.jsonl` files
- Run `bd sync` again

## Integration with QuinnAI

### Worker Commands
```bash
# QuinnAI workers use both qn wrkr and bd commands:

qn wrkr get-work     # Gets assigned work from queue
bd ready             # Shows available work to claim
bd show <id>         # View details
bd update <id> --claim  # Claim work
bd close <id> --reason="..."  # Complete work
```

### OKRs
```bash
# OKRs are beads with label=okr
bd list --label=okr

# Tasks block OKRs
bd show <task-id>  # See "Blocks:" section
```

## Quick Reference Card

```bash
# Find work
bd ready                    # Ready to work (no blockers)
bd list --status=open       # All open work
bd blocked                  # All blocked work

# Work on issue
bd show <id>                # Full details
bd update <id> --claim      # Claim it
bd update <id> --notes="x"  # Add notes
bd close <id> --reason="x"  # Complete

# Dependencies
bd dep add <A> <B>          # A depends on B (B blocks A)
bd dep rm <A> <B>           # Remove dependency

# Sync
bd sync                     # Sync with remote
```
