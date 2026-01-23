# Agent Instructions

This project uses **bd** (beads) for issue tracking. Run `bd onboard` to get started.

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

