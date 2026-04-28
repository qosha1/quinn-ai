# Stub Completion Strategy - 2026-01-26 (HISTORICAL)

> **⚠️ HISTORICAL PLANNING DOC — DO NOT TREAT AS CURRENT.**
>
> This is the strategy/plan written in response to the Jan 2026 stub
> audit (`stub-audit-2026-01-25.md`). The work it proposed has either
> been completed or superseded by later refactors (board merge,
> package splits across session/, org_init/, okr/, escalation/,
> plus the Q1-Q2 sweeps). Phase plans and prioritizations below
> reflect Jan-2026 priorities, not current ones. Use as historical
> context only.

**Task:** quinnai-iqxt
**Author:** Claude (automated)
**Parent Audit:** quinnai-uk90 (docs/audits/stub-audit-2026-01-25.md)

---

## Executive Summary (at the time)

After reviewing the stub audit from 2026-01-25 and re-scanning the current codebase, most identified issues have been resolved. Only **2 active TODO markers** remain in production code, plus **1 in documentation**.

### Current Status
- **Total active TODOs in code**: 2 (down from 14 in audit)
- **Actual incomplete implementations**: 1 blocking (real-time subscriptions)
- **UI improvements**: 1 nice-to-have (close button per tab)
- **Documentation TODOs**: 1 (provider research)
- **False positives**: 12 (variable names, intentional exception handlers)

---

## Real TODOs Identified

### P0 - Blocking Real-Time Updates

**File:** `terminal-app/src/board_ui/services/org_connection.py:1297`
**Issue:** Real-time subscriptions not implemented

```python
# TODO: Implement real-time subscriptions via:
# 1. SQLite WAL polling
# 2. File system watching on quinn.db-wal
```

**Impact:**
- Blocks live status updates in qn board ui terminal UI
- Users must manually refresh to see worker status changes
- Related to open issue: quinnai-dj2h (Debug qn board ui UI status update failures)

**Dependencies:**
- Understanding of SQLite WAL (Write-Ahead Logging) mode
- File system watching (inotify/fsevents/watchdog)
- Textual app reactive bindings

**Implementation Approach:**

1. **Option A: SQLite WAL Polling** (Recommended)
   - Poll `PRAGMA wal_checkpoint` to detect changes
   - Use last_seen_version tracking
   - Lightweight, no external dependencies
   - 100-500ms poll interval acceptable for UI

2. **Option B: File System Watching**
   - Watch `quinn.db-wal` for modifications
   - Use `watchdog` library (cross-platform)
   - More responsive but adds dependency
   - May trigger too frequently on high write volume

3. **Option C: Hybrid Approach**
   - FS watch triggers immediate poll
   - Fallback to periodic polling if watch fails
   - Best of both worlds but more complex

**Recommended:** Option A (WAL polling) for MVP, Option C for production.

**Subtasks to Create:**
1. Research SQLite WAL checkpoint detection methods
2. Implement WAL polling service in org_connection.py
3. Add reactive data bindings to OrgConnection
4. Update UI components to subscribe to data changes
5. Add debouncing to prevent excessive UI updates
6. Test with multiple concurrent writers

**Complexity:** Moderate (2-3 hours)
**Priority:** P0 (blocks critical functionality)

---

### P2 - UI Improvement

**File:** `terminal-app/src/board_ui/views/org_tabs.py:146`
**Issue:** Close button per tab not implemented

```python
# TODO: Implement separate close button per tab
# For now, clicking the tab switches to it
```

**Impact:**
- Minor UX inconvenience
- Users cannot close org tabs without keyboard shortcut
- Clicking "×" symbol switches tab instead of closing

**Implementation Approach:**

1. Separate tab button into two clickable regions:
   - Tab label (left) → switches to tab
   - Close button (right "×") → closes tab

2. Use Textual button composition:
   - Container with two child buttons
   - Style close button differently
   - Handle click events separately

3. Add confirmation for closing modified orgs (optional)

**Subtasks to Create:**
1. Refactor tab button to compound widget
2. Add close handler that calls `close_org(org_path)`
3. Update styling to distinguish clickable regions
4. Add keyboard shortcut documentation

**Complexity:** Trivial (30 minutes)
**Priority:** P2 (nice-to-have, not blocking)

---

### P3 - Documentation

**File:** `cli/docs/design/provider-research-openai.md:48`
**Issue:** CodexParser not implemented

```markdown
**TODO:** Create `CodexParser` for accurate output parsing.
```

**Impact:**
- Documentation note for future OpenAI provider work
- Not blocking current functionality (Claude provider is primary)
- Codex is deprecated anyway (replaced by GPT-4)

**Recommendation:**
- Close as WONTFIX - Codex is deprecated
- Update doc to reflect modern OpenAI models (GPT-4, GPT-4o)
- Remove TODO or replace with guidance on GPT-4 output parsing

**Complexity:** Trivial (update documentation)
**Priority:** P3 (documentation cleanup)

---

## False Positives (Already Complete)

### Variable Name: TODO_WRITE_TOOL

**Files:**
- `shared/pyterm/tools.py:718`
- `shared/pyterm/__init__.py:65, 159`

**Explanation:**
- `TODO_WRITE_TOOL` is a constant name for the TodoWrite tool
- Not a TODO comment - just unfortunate naming
- Fully implemented, no action needed

**Recommendation:** No change needed (intentional naming)

---

### Intentional Exception Handlers

**Files:** Multiple (cli/core/worker.py, cli/core/permissions.py, etc.)

**Pattern:**
```python
except SomeError:
    # Intentionally swallowed: <explanation>
    pass
```

**Explanation:**
- All `pass` statements in exception handlers are documented
- Represent best-effort operations (event publishing, file cleanup, etc.)
- Failures are intentionally ignored to prevent cascading errors

**Recommendation:** No action needed (correct error handling pattern)

---

## Completion Strategy

### Phase 1: Critical Path (P0)

**Focus:** Real-time subscriptions (blocking qn board ui status updates)

**Tasks:**
1. Create subtask: `quinnai-<new>: Implement SQLite WAL polling for real-time updates`
2. Research WAL checkpoint detection
3. Implement polling service
4. Add reactive bindings
5. Test with concurrent writes
6. Close parent issue: quinnai-dj2h

**Timeline:** 1 day (with testing)
**Owner:** Assign to backend/UI specialist

---

### Phase 2: UI Polish (P2)

**Focus:** Tab close buttons

**Tasks:**
1. Create subtask: `quinnai-<new>: Add close button per org tab`
2. Refactor tab widget
3. Add close handler
4. Update styling

**Timeline:** 2-3 hours
**Owner:** Assign to UI developer

---

### Phase 3: Cleanup (P3)

**Focus:** Documentation updates

**Tasks:**
1. Update provider-research-openai.md
2. Remove Codex references
3. Document GPT-4 parsing approach

**Timeline:** 30 minutes
**Owner:** Assign to documentation maintainer

---

## Architecture Decisions

### AD-001: Real-Time Update Strategy

**Decision:** Use SQLite WAL polling for real-time updates

**Rationale:**
- SQLite is already in WAL mode (enabled in db.py)
- No external dependencies required
- Cross-platform (works on all OSes)
- Predictable resource usage
- Sufficient for terminal UI responsiveness

**Alternatives Considered:**
- File system watching: Platform-specific, may trigger too frequently
- Database triggers: Not supported across process boundaries in SQLite
- Message queue: Overkill for single-machine deployment

**Trade-offs:**
- Polling latency (100-500ms acceptable for UI)
- Small CPU overhead (negligible for periodic checks)
- Simpler than FS watching
- No new dependencies

---

### AD-002: Tab Close Button Implementation

**Decision:** Use compound widget with separate click regions

**Rationale:**
- Standard UI pattern (browser tabs)
- Clear user affordance
- No breaking changes to existing tab switching

**Alternatives Considered:**
- Right-click menu: Not discoverable
- Middle-click to close: Not intuitive for CLI users
- Keyboard-only: Already exists, but not enough

---

## Verification Checklist

For each completed implementation:

- [ ] Code review passed
- [ ] Tests added/updated
- [ ] Documentation updated
- [ ] No new TODOs introduced
- [ ] Performance impact measured (if applicable)
- [ ] Cross-platform tested (if applicable)
- [ ] User-facing changes documented in CHANGELOG

---

## Subtasks to Create

### Immediate (P0)
1. **quinnai-<new>**: Implement SQLite WAL polling for real-time updates
   - Parent: quinnai-iqxt
   - Blocks: quinnai-dj2h
   - Complexity: Moderate
   - Priority: P0

### Soon (P2)
2. **quinnai-<new>**: Add close button per org tab
   - Parent: quinnai-iqxt
   - Complexity: Trivial
   - Priority: P2

### Later (P3)
3. **quinnai-<new>**: Update provider research docs (remove Codex references)
   - Parent: quinnai-iqxt
   - Complexity: Trivial
   - Priority: P3

---

## Notes

**Good News:**
Most TODO markers from the 2026-01-25 audit have been resolved. The codebase is in much better shape than the audit suggested.

**Key Insight:**
The audit's "14 files with TODO/FIXME markers" included many false positives:
- Variable names (TODO_WRITE_TOOL)
- Documented exception handlers (intentional `pass`)
- Old references in .beads/issues.jsonl (historical data)
- Test file exclusion patterns (test data, not real TODOs)

**Recommendation:**
Focus on the 2 real TODOs (real-time subscriptions, tab close button) rather than creating unnecessary work from false positives.

**Follow-up:**
After completing these tasks, run a fresh audit to verify no new stubs have been introduced.

---

## Success Criteria

**This task (quinnai-iqxt) is complete when:**
1. ✅ Completion strategy documented (this file)
2. ✅ Subtasks created for each real TODO
3. ✅ Dependencies identified
4. ✅ Implementation approaches designed
5. ✅ Priorities assigned based on impact

**Blocked tasks (quinnai-68a1, quinnai-ytzs, quinnai-zhvy) are unblocked when:**
- This strategy is reviewed and approved
- Subtasks are created in beads
- Work can begin on P0 items
