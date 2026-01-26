# Agent Instructions

This project uses **bd** (beads) for issue tracking. Run `bd onboard` to get started.

> **Deployed docs live under** `shared/onboarding/configs/`. Keep the root-level `CLAUDE.md`, `AGENTS.md`, and `README.md` focused on this repo and the way our internal agent workflows should behave. The files under `shared/onboarding/configs/` are what we ship into deployed QuinnAI orgs.

## Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --status in_progress  # Claim work
bd close <id>         # Complete work
bd sync               # Sync with git
```

## Verifying Work Against OKRs

**Before closing any work item**, verify it meets the linked OKR's key results:

1. **Find the OKR** - Check what OKR your work serves:
   ```bash
   bd show <work-id>  # Look for "serves" dependency
   qn org okr progress <okr-id>  # View key results and targets
   ```

2. **Run verification** - Execute tests/checks for each key result:
   - If KR is "test coverage > 80%": run coverage tool
   - If KR is "Lighthouse > 90": run lighthouse audit
   - If KR is "load time < 2s": measure performance

3. **Update progress** - Record your results:
   ```bash
   qn org okr update-kr <okr-id> --metric="lighthouse" --current=92
   ```

4. **Only close if targets met** - If key results aren't met, iterate on the work

**If no OKR exists**, escalate to your manager:
- "This work has no measurable key results. What quality bar should I verify against?"

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

## How Deployed Org Workers Should Act

The paragraphs below describe how workers inside a deployed QuinnAI org operate. These are org-facing concepts (OKRs, escalation, storage rules), not contributor workflow. The same guidance is duplicated under `shared/onboarding/configs/` so the deployed environment receives the right CLAUDE/AGENTS/README.

- Follow cascaded OKRs and your manager's direction; clarify scope before starting.
- Use `shared/` for durable knowledge; keep drafts in your worker folder.
- Escalate early when off-track; use messages and beads rather than side channels.
- Treat the deployed `CLAUDE.md` and `AGENTS.md` as the source of truth for behavior.

### Workday Lifecycle

- **Hiring**: `qn org hire --name <name> --role <role> --manager <manager>` equals spawning a worker, starting their session, and delivering the onboarding packets. Hiring does not require a separate `--start-session` flag; it is part of the same flow.
- **Starting a workday**: `qn org start --worker <name>` always creates a fresh session for the worker, bumps `QUINN_WORKER_ID`, and plays a short wakeup message so everyone knows the current priorities. It is equivalent to spawning their terminal (tmux, shell, etc.) if nothing is running.
- **Stopping a workday**: `qn org stop --worker <name>` requests that the worker wrap up, closes the terminal/session once the work is safe, and records the end-of-day state. Workers should use this instead of manually abandoning sessions.
- **Org shutdown**: `qn org stop` pauses the entire org and closes sessions for everyone, while `qn org cleanup` sweeps stray notifications and sessions.

### Worker Commands

- `qn wrkr status` – Inspect your lifecycle/runtime state. Requires `--worker-id <id>` or `QUINN_WORKER_ID`.
- `qn wrkr get-work` – Pull the next assigned bead. The command derives the worker identity from the `QUINN_WORKER_ID` environment variable that `qn org start --worker` sets at session start, or from an explicit `--worker-id`.
- `qn wrkr report` – Send progress updates or blockers so the board can track work.
- `qn wrkr inbox` / `qn wrkr send` / `qn wrkr search` – Read notifications, send messages, and search history. All commands require the worker identity.
- `qn wrkr delegate` – Hand hiring authority to a report when delegated by your manager.
- `qn-bd ready`, `qn-bd list`, `qn-bd show`, `qn-bd update`, `qn-bd close` – Use the bundled beads CLI to discover, claim, and resolve work.

### Org Controller Commands (CEOs, managers, board members)

- `qn org status` – Snapshot org and worker lifecycles.
- `qn org hire` / `qn org fire` – Add or remove a worker (hire auto-starts the session; fire stops it and closes the space).
- `qn org start --worker <name>` / `qn org stop --worker <name>` – Wake or wrap-up a specific worker.
- `qn org observe --worker <name>` – Attach/stream to a worker's session (tmux).
- `qn org logs --worker <name>` – View tmux scrollback for auditing.
- `qn org cleanup` – Tear down orphaned sessions/notifications.
- `qn org message ceo ...` – Send high-level nudges (e.g., remind the CEO to add measurable KRs).
- `qn org okr list|add|set|update-kr|link` – Manage OKRs that every worker must verify against before closing work.
