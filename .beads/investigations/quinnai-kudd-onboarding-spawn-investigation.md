# Investigation: Should onboarding modify session spawn?

**Issue:** quinnai-kudd
**Date:** 2026-01-26

## Question

Should the onboarding system modify the session spawn flow (SessionConfig, working_directory, env_vars), or should it just create files and let workers discover them?

## Current Approach

Onboarding modifies spawn in `cli/commands/org/start.py`:

```python
config = SessionConfig(
    worker_id=ceo.id,
    provider=provider,
    command=command,
    args=args,
    working_directory=worker_dir,      # ← Modified to worker's directory
    env_vars=env_vars,                  # ← Injected worker identity/paths
)
```

## Analysis

### Design Doc Evidence (docs/worker-onboarding-design.md)

The design doc **explicitly specifies a 3-layer onboarding approach:**

**Layer 1: Filesystem (Permanent Reference)**
- Files in worker directory: BRIEFING.md, STORAGE.md, symlinks
- "Permanent reference (can re-read anytime)"

**Layer 2: Environment (Runtime Context)**
- Environment variables: WORKER_ID, WORKER_STORAGE, SHARED_STORAGE, etc.
- **Rationale given:**
  - "Instantly available in session"
  - "Scripts can reference them"
  - "No file I/O needed"
  - "Standard unix pattern"

**Layer 3: Welcome Message (First Impression)**
- ~~Displayed on spawn~~ (NOW: WELCOME.md file per quinnai-jjnx)
- "Immediate orientation"

### Design Principle: "Session = Worker's Brain"

From design doc:
> **Session = Worker's Brain** - Context must be in session's environment

This principle strongly suggests that worker identity and paths SHOULD be in the session environment (env vars), not just files.

### Working Directory Philosophy

The design doc shows `working_directory=worker_dir` explicitly in integration examples.

**Rationale:**
- **Isolation:** Worker starts in their private workspace
- **Storage Mirrors Org-Chart:** Worker directory reflects their place in hierarchy
- **Default context:** Worker's files (BRIEFING.md, etc.) are immediately accessible without cd

**Alternative:** Start at org root with full visibility, let worker navigate as needed.

**Design choice:** Isolation over access. Worker starts in their space.

### Comparison to CLAUDE.md Pattern

**CLAUDE.md:**
- Just symlinkfile
- No env vars
- No working directory change
- Worker discovers and reads when ready

**Onboarding:**
- Files + env vars + working directory
- More "opinionated" - sets up environment

**Why is onboarding different?**

CLAUDE.md is **architectural documentation** - universal, static, reference material.

Onboarding is **worker context** - identity, paths, role-specific information. This IS the session's runtime environment.

### "No Magic" Principle vs. Env Vars

CLAUDE.md says: "No Magic Strings, Values, or Numbers. EVER."

But also says: "ALL values go in config. Hierarchy: system-wide config → object/class config → module-level constants"

**Are env vars "magic"?**

NO, because:
1. **Explicitly passed** at spawn (not discovered) - follows "Configuration is passed explicitly" principle
2. **Documented** in BRIEFING.md and STORAGE.md - not hidden
3. **Standard Unix pattern** - $HOME, $USER, $PATH are universal patterns
4. **Expose, don't hide** - make worker identity transparent, not magical

If we removed env vars:
- Worker would need to parse `pwd` or read files to learn their ID
- Scripts would need file I/O: `WORKER_ID=$(cat .worker-id)`
- Violates "no magic" MORE (magic file locations) than env vars (explicit config)

### Three Options Evaluated

**Option A: Minimal files, no spawn modification**
```python
# Just create files, don't modify spawn
config = SessionConfig(worker_id=ceo.id, provider=provider, command=command, args=args)
# Use default working_directory (org root), no env vars
```
**Pros:** Least "opinionated", like CLAUDE.md pattern
**Cons:** Worker must discover everything, no runtime context, violates "Session = Worker's Brain"

**Option B: Files + env vars**
```python
config = SessionConfig(
    worker_id=ceo.id,
    provider=provider,
    command=command,
    args=args,
    env_vars=env_vars,  # Identity/paths available
)
# Default working directory (org root)
```
**Pros:** Runtime context available, worker navigates manually
**Cons:** Worker starts at org root (no isolation), must cd to workspace

**Option C: Files + working_directory + env vars (CURRENT)**
```python
config = SessionConfig(
    worker_id=ceo.id,
    provider=provider,
    command=command,
    args=args,
    working_directory=worker_dir,  # Start in workspace
    env_vars=env_vars,              # Identity/paths available
)
```
**Pros:** Full context, isolation, aligns with "Session = Worker's Brain" principle
**Cons:** Most "opinionated" - sets up worker's environment

## Recommendation

**Keep Option C: Files + working_directory + env vars (current approach)**

### Justification

1. **Design doc explicitly specifies this** - The 3-layer approach is deliberate, not accidental
2. **"Session = Worker's Brain" principle** - Context MUST be in session environment
3. **Env vars are not magic** - They're explicitly passed, documented, standard Unix patterns
4. **Working directory = isolation** - Worker starts in their workspace, must explicitly navigate to shared/ or other workers' dirs
5. **Follows principle hierarchy** - Design doc > CLAUDE.md generic rules
6. **Practical benefits:**
   - Worker can immediately: `cat BRIEFING.md` (no cd needed)
   - Scripts can use: `$WORKER_STORAGE`, `$SHARED_STORAGE` (no parsing)
   - Worker knows: `echo $WORKER_ID` (no file lookup)

### But We Should

1. **Document this decision** - Add to docs/architecture-decisions/ explaining WHY
2. **Make env vars transparent** - Ensure BRIEFING.md documents all env vars
3. **Test isolation** - Verify worker can access shared/ and other workers' dirs from their starting point
4. **Consider worker type differences:**
   - CEO might benefit from starting at org root (full visibility)
   - ICs benefit from starting in their workspace (isolation)
   - But consistency is more valuable than per-role customization

## Answers to Specific Questions

**1. Why set working_directory to worker dir?**
- **Answer:** Isolation principle. Worker starts in their space, has immediate access to their briefing/docs, must explicitly navigate elsewhere. Aligns with "Storage Mirrors Org-Chart."

**2. Why inject env vars?**
- **Answer:** "Session = Worker's Brain" - context must be in environment. Env vars are the standard Unix way to provide runtime identity and paths. Not magic - explicitly passed and documented.

**3. What's the minimal onboarding?**
- **Answer:** Technically minimal is just files. But design doc specifies 3 layers for good reasons. "Minimal" would violate the "Session = Worker's Brain" principle.

**4. Session = Worker's Brain - what does this mean?**
- **Answer:** The session IS the worker's cognitive environment. Their identity, workspace, and context should be immediately available without requiring discovery or file I/O. Just like a human brain knows "who am I" without looking it up.

## Conclusion

The current approach (Option C) is correct and aligns with the design doc principles. No changes needed.

The question itself is valuable because it forced us to justify the architecture, but the answer is: **keep the current design**.

## Implementation

No code changes needed. This investigation closes with recommendation to keep current approach.

Create an ADR (Architecture Decision Record) to document this for future reference:
- docs/architecture-decisions/003-onboarding-session-modification.md
