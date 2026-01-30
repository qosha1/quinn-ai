# QuinnAI Organization - Agent Instructions

You are a worker in a **QuinnAI organization**. This is an AI-powered organization management system where:
- Workers use `qn wrkr` commands for work operations
- Work is tracked in **beads** (issues/tasks) and aligned to **OKRs** (strategic objectives)
- All commands require worker identity (`--worker-id` or `$QUINN_WORKER_ID` env var)

## Essential Commands

### Work Management
```bash
qn wrkr get-work              # Get your assigned work (ordered by priority)
qn wrkr status                # Check your lifecycle and runtime status
qn wrkr report                # Post status updates / report blockers
```

### Communication
```bash
qn wrkr inbox                 # View notifications and messages
qn wrkr send <channel> <msg>  # Send message to channel or worker
qn wrkr search <keyword>      # Search message history
```

### Beads (Work Tracking)
```bash
bd ready                      # Find available work (no blockers)
bd show <id>                  # View issue details
bd update <id> --status=in_progress  # Claim work
bd close <id> --reason="..."  # Complete work with explanation
bd sync                       # Sync beads with git remote
```

### OKRs (Strategic Alignment)
```bash
qn org okr list               # List all OKRs
qn org okr show <okr-id>      # Show OKR details + progress
qn org okr link <work-id> <okr-id>  # Link work to OKR (serves relationship)
bd dep add <work-id> <okr-id>       # Alternative: link via dependency
```

## Understanding OKRs vs Operational Work

**OKRs (Objectives & Key Results)** - Strategic quarterly goals set by leadership
- Type: `epic`, Label: `okr`
- Have measurable key results (metrics to track)
- Example: "Q1 2026: Ship Beads Dashboard v1.0 - 100% test coverage, <2s load time"

**Operational Work** - Day-to-day tasks that advance OKRs
- Type: `task`, `bug`, `feature`
- Should link to parent OKR via `serves` dependency
- Example: "Add pagination to API" serves "Dashboard v1.0 OKR"

**Your Workflow:**
1. Check which OKR your work blocks: `bd show <work-id>` (look at "Blocks" section)
2. Read the OKR's key results: `bd show <okr-id>` (understand success criteria)
3. Do the work and measure against OKR key results
4. Close work when complete: `bd close <id> --reason="Feature complete, tests at 95%"`

**Dependency Model:**
- Tasks **block** epics/OKRs (epic depends on tasks being complete)
- When you complete a task, the epic gets closer to completion
- Use `bd show <id>` to see what your work blocks (impacts)

**CRITICAL:** Work contributes to OKRs by blocking them. When all tasks blocking an OKR are done, the OKR can be closed.

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd sync
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds

