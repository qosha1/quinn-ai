# ADR 003: Onboarding System Modifies Session Spawn

**Status:** Accepted
**Date:** 2026-01-26
**Deciders:** Architecture review (quinnai-kudd investigation)
**Related:** quinnai-kudd, quinnai-4cic (onboarding epic)

## Context

Workers (CEO, managers, ICs) spawn into AI assistant sessions. The question arose: should the onboarding system modify the session spawn configuration (working directory, environment variables), or should it just create files and let workers discover context naturally?

Three options were considered:
- **A:** Minimal files only (no spawn modification)
- **B:** Files + env vars (start at org root)
- **C:** Files + working_directory + env vars (current)

## Decision

**We keep Option C: Files + working_directory + env vars**

The onboarding system modifies session spawn to:
1. Set `working_directory` to the worker's hierarchical storage path
2. Inject environment variables with worker identity and key paths
3. Create reference files (BRIEFING.md, STORAGE.md, WELCOME.md)

Example:
```python
config = SessionConfig(
    worker_id=ceo.id,
    provider=provider,
    command=command,
    args=args,
    working_directory=worker_dir,  # workers/{hierarchy}/
    env_vars={
        "WORKER_ID": worker_id,
        "WORKER_STORAGE": str(worker_dir),
        "SHARED_STORAGE": str(shared_dir),
        # ... more context
    },
)
```

## Rationale

### 1. Aligns with "Session = Worker's Brain" Principle

From design doc:
> **Session = Worker's Brain** - Context must be in session's environment

A worker's session IS their cognitive environment. Their identity, workspace, and key paths should be immediately available, not requiring discovery or file I/O.

Just like a human knows "who am I?" without looking it up, a worker session should know `$WORKER_ID` instantly.

### 2. Multi-Layer Onboarding Design

The design doc explicitly specifies 3 concurrent layers:
- **Layer 1:** Filesystem (files workers can re-read)
- **Layer 2:** Environment (runtime context via env vars)
- **Layer 3:** Welcome message (first impression)

This is a deliberate design, not accidental. Each layer serves a purpose:
- Files: Persistent reference
- Env vars: Instant access, no I/O
- Welcome: Orientation

### 3. Env Vars Are Not "Magic"

CLAUDE.md prohibits "magic strings" - hardcoded values buried in code.

But env vars are NOT magic because they:
- Are explicitly passed at spawn (not discovered)
- Are documented in BRIEFING.md (not hidden)
- Follow standard Unix patterns ($HOME, $USER, $PATH)
- Expose configuration, don't hide it

Alternative (no env vars) would be MORE magic:
- Worker parses `pwd` to learn their ID? (magic location parsing)
- Worker reads `.worker-id` file? (magic file location)
- Worker searches parent dirs for config? (magic discovery)

Env vars are the **least magic** way to provide runtime identity.

### 4. Working Directory = Isolation Principle

Setting `working_directory` to the worker's path provides:
- **Isolation:** Worker starts in their private workspace
- **Immediate access:** `cat BRIEFING.md` works without `cd`
- **Explicit navigation:** Worker must explicitly `cd` to shared/ or other workers' dirs
- **Org-chart alignment:** Worker directory mirrors their place in hierarchy

Alternative (start at org root) gives too much visibility by default. Workers should start in their space and navigate outward intentionally.

### 5. Different from CLAUDE.md Pattern - By Design

CLAUDE.md symlink:
- Just a file, no spawn modification
- Universal architectural documentation
- Static, same for all workers

Onboarding:
- Files + env vars + working dir
- Per-worker runtime context
- Dynamic, role-specific

**CLAUDE.md is documentation. Onboarding is identity.**

They serve different purposes and should behave differently.

## Consequences

### Positive
- Workers have immediate context without discovery
- Scripts can use `$WORKER_STORAGE` and `$SHARED_STORAGE` reliably
- Workers start in their workspace (isolation)
- Identity is transparent: `echo $WORKER_ID`
- Aligns with Unix standards (env vars for runtime context)

### Negative
- More "opinionated" than minimal file approach
- Session spawn is modified (adds complexity to SessionConfig)
- Requires passing db to `get_worker_env_vars()` for hierarchical paths

### Neutral
- Env vars must be documented in BRIEFING.md (ensures transparency)
- Working directory must support hierarchical paths (via StorageManager)

## Alternatives Considered

### Option A: Minimal Files Only
```python
# Just create BRIEFING.md, STORAGE.md, symlinks
# Don't modify spawn at all
config = SessionConfig(worker_id=ceo.id, provider=provider, command=command, args=args)
```

**Rejected because:**
- Violates "Session = Worker's Brain" principle
- Worker must discover identity from files or pwd parsing
- No runtime context available for scripts
- Starting at org root gives too much default visibility

### Option B: Files + Env Vars (No Working Directory)
```python
config = SessionConfig(
    worker_id=ceo.id,
    provider=provider,
    command=command,
    args=args,
    env_vars=env_vars,  # Identity available
    # Start at org root
)
```

**Rejected because:**
- Worker starts at org root (no isolation)
- Worker must `cd $WORKER_STORAGE` to access their files
- Loses "Storage Mirrors Org-Chart" principle
- Inconsistent with design doc examples

## Related Decisions

- ADR 001: Storage architecture (hierarchical paths mirror org-chart)
- ADR 002: Worker onboarding 3-layer system
- Design doc: docs/worker-onboarding-design.md

## Notes

This decision was questioned (quinnai-kudd) after implementation, which is good - it forced us to justify the architecture.

The investigation confirmed the current approach is correct per design principles. No changes needed.

If we reconsider this in the future, focus on:
1. Does "Session = Worker's Brain" still hold?
2. Are env vars still the best way to provide runtime identity?
3. Does working directory isolation still serve us?

If answers are yes, keep this approach.
