# Storage Architecture Guide

QuinnAI uses a hierarchical storage system that mirrors the org chart.

## Directory Structure

```
org/
├── storage/
│   ├── shared/                      # Org lifetime - permanent knowledge
│   │   ├── engineering/             # Default shared topics
│   │   ├── legal/
│   │   ├── company/
│   │   └── archive/                 # Offboarded worker files
│   └── workers/                     # Worker lifetime - mirrors org chart
│       └── ceo/                     # CEO at root
│           ├── director-abc/        # Director reports to CEO
│           │   └── engineer-xyz/    # Engineer reports to director
│           └── manager-def/         # Manager reports to CEO
├── live/                            # Runtime state (database, logs)
└── config/                          # Org configuration
```

**Worker storage mirrors org-chart hierarchy:**
- CEO: `workers/ceo/`
- Directors: `workers/ceo/director-{id}/`
- Their reports: `workers/ceo/director-{id}/engineer-{id}/`

## Storage Tiers

### Your Workspace (`$WORKER_STORAGE`)

**Location:** Mirrors your position in the org chart
- If you're CEO: `workers/ceo/`
- If you report to CEO: `workers/ceo/{your-id}/`
- If you report to a director: `workers/ceo/director-{id}/{your-id}/`

**Lifetime:** Deleted when you're fired (after teammate review)

**Use for:**
- Work in progress
- Personal notes
- Temporary files
- Drafts before sharing

**Examples:**
```bash
# Your workspace (you're already here)
pwd  # shows your hierarchical path

# Create notes
echo "Research findings" > research-notes.md

# Organize your work
mkdir drafts/
mkdir experiments/
```

### Shared Topics (`shared/topics/{topic}/`)

**Lifetime:** Permanent (org lifetime)

**Use for:**
- Completed research
- Architectural decisions
- Reusable code/templates
- Documentation

**Examples:**
```bash
# Save architecture decision
cp architecture-proposal.md $SHARED_STORAGE/topics/architecture/

# Save reusable template
cp email-template.md $SHARED_STORAGE/topics/templates/

# Search shared knowledge
grep -r "API design" $SHARED_STORAGE/topics/
```

### Shared Teams (`shared/teams/{team}/`)

**Lifetime:** Permanent (org lifetime)

**Use for:**
- Team processes
- Team-specific knowledge
- Shared team resources

**Examples:**
```bash
# Save team process
cp our-standup-notes.md $SHARED_STORAGE/teams/{your-team}/

# Team standards
cat $SHARED_STORAGE/teams/{your-team}/coding-standards.md
```

## Workflow: From Private to Shared

1. **Start in your workspace** (you're already here)
   ```bash
   vim research.md
   ```

2. **When complete and valuable, save to shared**
   ```bash
   cp research.md $SHARED_STORAGE/topics/research/api-design.md
   ```

3. **Teammates can now find it**
   ```bash
   # Another worker
   cat $SHARED_STORAGE/topics/research/api-design.md
   ```

## When You're Fired

**Process (per system design):**
1. Your workspace is frozen (read-only)
2. System creates ask bead: "Offboard storage review: {your-id}"
3. Teammate reviews your workspace
4. Teammate moves useful artifacts to shared/
5. On ask completion, system deletes your workspace

**This is why shared/ is important** - it's the only way your work survives.

## Rules

✓ **DO:** Save important discoveries to shared/
✓ **DO:** Use descriptive paths and filenames
✓ **DO:** Document what you save (README.md in each topic/)

✗ **DON'T:** Leave valuable work in workers/ - it will be deleted
✗ **DON'T:** Pollute shared/ with temporary files
✗ **DON'T:** Store secrets in shared/ - use secure storage

## Quick Reference

**Environment Variables:**
- `$WORKER_STORAGE` - Your workspace
- `$SHARED_STORAGE` - Shared storage root
- `$ORG_PATH` - Organization root

**Useful Commands:**
```bash
# Show your storage
ls -la $WORKER_STORAGE

# Browse shared topics
ls $SHARED_STORAGE/topics/

# Search all shared knowledge
grep -r "keyword" $SHARED_STORAGE/

# Copy to shared topics
cp myfile.md $SHARED_STORAGE/topics/category/
```
