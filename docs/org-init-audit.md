# Org Initialization Audit

**Date:** 2026-01-23
**Issue:** CEO workers spawn with no context about mission, architecture, or tools

## Current Flow

### `qn org init`

1. **Folder Structure Created** (`cli/core/org_init.py:106-133`)
   ```
   org_path/
   ├── config/              # Templates copied here
   ├── org-chart/           # Git-tracked hiring output
   ├── live/                # Runtime state
   │   ├── quinn.db
   │   └── workers/
   └── storage/
       ├── shared/          # Org lifetime
       └── workers/         # Worker lifetime
   ```

2. **Config Templates Copied** (`org_init.py:135-152`)
   - `providers.yaml` - AI provider settings
   - `worker-templates.yaml` - Worker spawn templates
   - `ceo_briefing.md` - **TEMPLATE with placeholders**
   - `initial_okrs.json` - **TEMPLATE objectives**

3. **Database Initialized** (`db.py`)
   - Creates `quinn.db` with schema
   - No `notifications` table (causes briefing delivery to fail)

4. **CEO Worker Created** (`worker.py`)
   - Inserted into `workers` table
   - `id`, `name`, `role`, `status='active'`
   - No session spawned yet

### `qn org start`

1. **Org Status Transition** (`org.py:234-260`)
   - `INITIALIZED` → `RUNNING`
   - Spawns CEO session

2. **Briefing Delivery Attempted** (`org.py:244-246`)
   ```python
   briefing_path = self._get_briefing_path()  # config/ceo_briefing.md
   if briefing_path.exists():
       self._deliver_ceo_briefing(ceo.id, briefing_path)
   ```

3. **Briefing Delivery Fails Silently** (`org.py:268-299`)
   - Looks for `board-channel` in database
   - **Channels table only has:** `executive`, `general`, `escalations`
   - Returns early with no error: `if not channel_row: return`
   - **CEO never receives briefing**

4. **CEO Session Spawns** (`worker.py:spawn_session`)
   - Tmux session created: `qn-wrkr-{id}`
   - Working directory: `/Users/qosha/orgs/my-ai-company/live/workers/{id}`
   - **No briefing message**
   - **No onboarding checklist**
   - **No context about the project**

## What's Broken

### 1. Briefing File is a Template
**File:** `~/orgs/my-ai-company/config/ceo_briefing.md`

```markdown
## Context
We are building [PROJECT NAME], a [DESCRIPTION].
Target users: [WHO]
Tech stack: [TECHNOLOGIES]
```

**Problem:** User never fills in placeholders. CEO gets template or nothing.

### 2. Briefing Delivery Fails
**Code:** `cli/core/org.py:281-285`

```python
channel_row = self.db.fetchone(
    "SELECT id FROM channels WHERE name = 'board-channel'"
)
if not channel_row:
    return  # Board channel doesn't exist yet
```

**Problem:** `board-channel` never created. Silent failure.

### 3. No Notifications Table
**Error:** `no such table: notifications`

**Problem:** Briefing delivery code tries to create notification bead, but table doesn't exist in schema.

### 4. OKRs are Template Data
**File:** `~/orgs/my-ai-company/config/initial_okrs.json`

```json
[
  {
    "title": "Launch New Feature",
    "key_results": [
      {"metric": "Feature shipped", "target": 1, "unit": "boolean"},
      {"metric": "User adoption rate", "target": 25, "unit": "%"}
    ]
  }
]
```

**Problem:** Generic template. CEO has no real objectives.

### 5. No Architecture Context
**Missing:**
- `CLAUDE.md` not copied to worker context
- `AGENTS.md` not available
- Storage hierarchy not explained
- Beads usage not taught
- Available tools not documented

### 6. No Session Initialization
**Missing in tmux spawn:**
- Welcome message
- Context about mission
- Tour of file structure
- Checklist of first actions
- Links to documentation

## What Should Happen

### During `qn org init`

1. **Interactive Setup**
   ```bash
   qn org init
   > What is this org for?
   > Main objective?
   > Initial budget?
   ```

2. **Fill Briefing Template**
   - Prompt user for real values
   - OR accept briefing file path
   - Write actual content (not placeholders)

3. **Define Real OKRs**
   - Prompt for objectives
   - OR import from file
   - Save to database (not just JSON)

4. **Create Required Channels**
   - `board-channel` for board ↔ CEO
   - Ensure delivery mechanism works

### During CEO Spawn

1. **Create Notifications Table** (if missing)
   - Schema migration needed
   - Or add to initial schema

2. **Deliver Briefing via Multiple Channels**
   - Message in `board-channel`
   - Notification bead for CEO
   - **File in CEO's worker directory:** `workers/{id}/BRIEFING.md`
   - Welcome message in tmux session

3. **Copy Architecture Docs**
   ```
   workers/{id}/
   ├── BRIEFING.md (org mission)
   ├── CLAUDE.md (symlink to project CLAUDE.md)
   ├── AGENTS.md (symlink to backend/AGENTS.md)
   └── STORAGE.md (explain shared/ vs workers/)
   ```

4. **Initialize Session with Context**
   ```bash
   # In tmux session startup
   echo "Welcome, CEO!"
   echo "Your briefing: $(cat BRIEFING.md)"
   echo ""
   echo "Your OKRs:"
   bd list --assignee=me
   echo ""
   echo "Available tools: bd, qn wrkr, storage helpers"
   echo "Documentation: cat CLAUDE.md"
   ```

5. **Create Onboarding Checklist Bead**
   ```
   ☐ Read briefing
   ☐ Review OKRs
   ☐ Check budget
   ☐ Explore shared/ storage
   ☐ Review architectural rules
   ```

## Recommended Fixes (Priority Order)

### P0 - Blocking Issues

1. **Add notifications table to schema** (or fix delivery to not require it)
2. **Create board-channel during org init**
3. **Make briefing delivery robust** (fallback to file copy if channels fail)

### P1 - UX Critical

4. **Interactive org init** - Collect real mission, OKRs, constraints
5. **Copy docs to worker context** - CLAUDE.md, AGENTS.md, STORAGE.md
6. **Session welcome message** - Show briefing, OKRs, tools

### P2 - Nice to Have

7. **Onboarding checklist** - Create bead with first actions
8. **Better templates** - More helpful placeholder text
9. **Validation** - Error if briefing still has [PLACEHOLDERS]

## Testing Plan

1. **Create fresh org with current code**
   ```bash
   rm -rf ~/orgs/test-org
   qn org init ~/orgs/test-org
   qn org start
   ```

2. **Verify CEO receives:**
   - [ ] Briefing message
   - [ ] Notification
   - [ ] File in worker directory
   - [ ] OKRs in bd list

3. **After fixes, repeat test**
   - Confirm all context delivered
   - CEO can answer "what are we building?"
   - CEO knows where to save work

## References

- Epic: quinnai-tiqb
- Review task: quinnai-45sm (this document)
- Design task: quinnai-2ync (next step)
- Audit task: quinnai-rogb (spawn flow audit)
