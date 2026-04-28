# ADR 004: Use Absolute Paths in Environment Variables

**Status:** Accepted
**Date:** 2026-01-26
**Deciders:** Architecture review (quinnai-5wy8 investigation)
**Related:** quinnai-5wy8, quinnai-4cic (onboarding epic)

## Context

Worker sessions receive environment variables with storage paths:
- `WORKER_STORAGE` - Worker's private workspace
- `SHARED_STORAGE` - Shared org knowledge
- `ORG_PATH` - Organization root

With hierarchical worker storage (workers/ceo/director-{id}/engineer-{id}/), relative paths to shared storage vary by depth:
- CEO: `../../shared/` (2 levels up)
- Director: `../../../shared/` (3 levels up)
- Engineer: `../../../../shared/` (4 levels up)

Question: Should environment variables use absolute or relative paths?

## Decision

**Use absolute paths in environment variables.**

Environment variables are set to absolute paths:
```bash
WORKER_STORAGE=/full/path/to/org/storage/workers/ceo/director-{id}/
SHARED_STORAGE=/full/path/to/org/storage/shared
ORG_PATH=/full/path/to/org
```

## Rationale

### 1. Convenience Over Portability

Environment variables are for **convenience** - they should "just work" from anywhere in the worker's session.

Workers might:
- `cd $SHARED_STORAGE` to browse shared knowledge
- `cd ../director-abc/` to check a peer's public work
- `cd $ORG_PATH/config` to view org settings
- Run commands from any cwd: `cp report.md $SHARED_STORAGE/topics/reports/`

With absolute paths, `$SHARED_STORAGE` works from any current directory. With relative paths, it only works when `pwd` is the worker directory.

### 2. Not a Portability Concern

Env vars are set **fresh each session** for that specific org on that machine. They're not:
- Stored in files and copied between machines
- Committed to git
- Shared between orgs

Portability (relative paths) would only matter if we were serializing env vars to files, which we don't.

### 3. Templates Use Env Vars

Templates (BRIEFING.md, STORAGE.md) reference env vars:
```bash
cp file.md $SHARED_STORAGE/topics/architecture/
```

Because they use env vars (not hardcoded relative paths), they work regardless of:
- Worker's hierarchy depth
- Current working directory
- Org installation path

### 4. Hierarchical Storage Already Works

StorageManager returns absolute paths via `get_worker_path()` and `get_shared_path()`. These are the source of truth for env vars.

The hierarchy is transparent to workers - they don't need to know their depth, just use the env vars.

## Alternatives Considered

### Option A: Relative Paths
```bash
WORKER_STORAGE=.
SHARED_STORAGE=../../shared  # CEO
SHARED_STORAGE=../../../shared  # Director
SHARED_STORAGE=../../../../shared  # Engineer
```

**Rejected because:**
- Only works when `pwd` is worker directory
- Breaks if worker does `cd $SHARED_STORAGE && some_command $SHARED_STORAGE/file`
- Requires workers to know their hierarchy depth
- More complex to set (need to calculate relative path based on depth)

### Option B: Both Absolute and Relative
```bash
WORKER_STORAGE=/full/path/to/workers/ceo/
WORKER_STORAGE_REL=.
SHARED_STORAGE=/full/path/to/shared
SHARED_STORAGE_REL=../../shared
```

**Rejected because:**
- Unnecessary complexity
- No use case for relative paths given absolute paths exist
- More env vars to document and maintain

### Option C: No Env Vars, Let Workers Figure It Out
```bash
# Workers must do: pwd, parse path, calculate relative paths
```

**Rejected because:**
- Defeats purpose of onboarding system (provide context)
- Every worker reimplements path discovery
- Error-prone (what if worker messes up the calculation?)

## Consequences

### Positive
- Workers can use `$WORKER_STORAGE` and `$SHARED_STORAGE` from any cwd
- Templates work regardless of hierarchy depth
- Simple to set - just absolute paths from StorageManager
- Workers don't need to know their hierarchy depth

### Negative
- Paths are machine-specific (but this doesn't matter - see rationale #2)
- Cannot serialize env vars to portable config (but we don't do this)

### Neutral
- Org path is part of env vars (explicit, not hidden)
- Templates document env vars (STORAGE.md "Quick Reference" section)

## Implementation

Environment variables are set in `cli/core/onboarding.py`:

```python
def get_worker_env_vars(
    ctx: OnboardingContext,
    org_path: Path,
    db: Database,
) -> dict[str, str]:
    """Get environment variables for worker session."""
    storage = StorageManager(org_path, db)
    worker_dir = storage.get_worker_path(ctx.worker_id)  # Absolute path

    return {
        "WORKER_ID": ctx.worker_id,
        "WORKER_NAME": ctx.worker_name,
        "WORKER_ROLE": ctx.worker_role,
        "TEAM_NAME": ctx.team_name,
        "MANAGER_ID": ctx.manager_id or "",
        "ORG_PATH": str(org_path),  # Absolute
        "WORKER_STORAGE": str(worker_dir),  # Absolute
        "SHARED_STORAGE": str(org_path / "storage" / "shared"),  # Absolute
        "ORG_DB": str(org_path / "live" / "quinn.db"),  # Absolute
        "BRIEFING_PATH": str(worker_dir / "BRIEFING.md"),  # Absolute
        # ... more env vars
    }
```

All paths use `str(Path(...))` which produces absolute paths.

## Related Decisions

- ADR 001: Storage architecture (hierarchical paths mirror org-chart)
- ADR 002: Worker onboarding 3-layer system (env vars are Layer 2)
- ADR 003: Onboarding modifies session spawn (sets working_directory and env_vars)

## Notes

This decision was questioned (quinnai-5wy8) after implementation. Investigation confirmed absolute paths are the correct choice.

If reconsidering in the future, focus on:
1. Do workers need to work from different cwds?
2. Are env vars being serialized/shared across machines?
3. Do templates break with current absolute paths?

If answers are yes, yes, no - keep absolute paths.
