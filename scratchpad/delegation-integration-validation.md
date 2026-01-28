# Delegation Integration Validation Report

**Date:** 2026-01-28
**System:** QuinnAI Hierarchical AI Organization Management
**Context:** Validating that delegation design integrates cleanly with all QuinnAI systems
**Design References:**
- `scratchpad/delegation-safety-analysis.md` - Safety analysis and edge cases
- `scratchpad/delegation-database-schema.md` - Database schema design

---

## Executive Summary

This document validates how the proposed hiring authority delegation system integrates with existing QuinnAI subsystems. The analysis reveals that delegation is well-positioned to integrate as a **first-class architectural component** rather than a bolted-on feature, primarily because:

1. **Budget System** already uses source-tracking patterns (`source_worker_id`) that delegation can mirror
2. **Event System** already has `BUDGET_DELEGATED` event type; authority delegation fits the same pattern
3. **Authorization System** already checks `hiring_authority_scope` - delegation extends this naturally
4. **Notification System** has patterns for worker-to-worker messaging that delegation can leverage

**Critical Integration Points Identified:**
- Budget allocation sync with delegated authority (P0)
- Event emission for delegation lifecycle (P0)
- Org chart display updates (P1)
- Session environment variables for authority awareness (P1)
- OKR scope for managers with hiring authority (P2)

---

## 1. Budget System Integration

### 1.1 Current State

**Files:** `cli/core/budget.py`, `cli/core/queries.py`

The budget system implements a cascading flow pattern:
```
Organization Pool -> CEO -> Directors -> Managers -> Workers
```

Key entities:
- `budget_allocations` table: Tracks allocated credits per worker
- `budget_transactions` table: Immutable ledger of all budget operations
- `BudgetBalance` dataclass: Current available/spent balance
- `BudgetService.delegate_budget()`: Transfers budget from manager to subordinate

**Existing Patterns:**
```python
# budget.py:628-762 - delegate_budget()
# Already tracks:
# - source_worker_id (who delegated)
# - transaction types: 'transfer_out', 'transfer_in'
# - can_delegate flag on allocations
```

### 1.2 Integration Point

**Question:** How does `workers.delegated_budget` relate to `budget_allocations` table?

**Answer:** They are **semantically different**:
- `workers.delegated_budget` = Budget worker can DELEGATE for hiring authority
- `budget_allocations.allocated_credits` = Budget worker can SPEND on operations

**Recommendation:** Rename for clarity:
```sql
-- Current (confusing)
workers.delegated_budget  -- Actually: budget for hiring delegation

-- Proposed (clear)
workers.hiring_budget_pool  -- Budget available to delegate for hiring
```

**Question:** Should delegation create a budget_allocation record for the delegate?

**Answer:** YES, but only for HIRING budget specifically.

**Implementation:**
```python
# In delegate_authority() - after creating delegation_grant
def delegate_authority(self, report, scope, hiring_budget):
    # ... create delegation_grant ...

    # If delegating hiring budget, create/update budget allocation
    if hiring_budget > 0:
        # Create hiring-specific allocation
        # Use separate pool_id to distinguish from operational budget
        budget_service.allocate_hiring_budget(
            source_worker_id=self.id,
            target_worker_id=report.id,
            amount=hiring_budget,
            scope=scope,  # Tied to hiring scope
        )
```

**Question:** What happens when delegator's budget allocation is reduced?

**Current:** No automatic handling.

**Recommendation (MUST):** When delegator's hiring budget is reduced below what they've delegated out:
1. Check active sub-delegations
2. If insufficient, block reduction OR cascade-reduce sub-delegations
3. Emit `BUDGET_DELEGATION_REDUCED` event

**Integration Code Location:** `cli/core/budget.py:update_worker_authority()`

### 1.3 Recommendations

| Priority | Change | Location |
|----------|--------|----------|
| MUST | Add `hiring_budget_pool` column distinct from operational budget | `cli/core/db.py` migration |
| MUST | Validate hiring budget when delegating authority | `Worker.delegate_authority()` |
| MUST | Block hiring if delegated budget insufficient | `Worker.can_hire()` |
| SHOULD | Auto-reduce sub-delegations when parent budget reduced | `BudgetService` |
| NICE | Show hiring budget separately in dashboard | `terminal-app/views/dashboard.py` |

---

## 2. Permissions and Beads

### 2.1 Current State

**Files:** `cli/core/authorization.py`, `cli/core/permissions.py`

The authorization system provides:
```python
# authorization.py:45-83
class AuthorizationManager:
    def can(self, worker_id, permission, target_id):
        # Dispatch to handlers:
        # - _can_hire()
        # - _can_fire()
        # - _can_delegate_budget()
        # - _can_escalate()
        # - _can_approve()
        # - _can_assign()
```

**Existing Hiring Check (authorization.py:163-181):**
```python
def _can_hire(self, worker, target_id):
    # Check authority via hiring_authority_scope
    if not self._has_hiring_authority(worker):
        return AuthorizationResult.deny(...)

    # Check budget for new worker
    balance = get_worker_balance(self._db, worker.id)
    if not balance or balance.available <= 0:
        return AuthorizationResult.deny(...)
```

### 2.2 Integration Point

**Question:** Does hiring authority affect bead creation permissions?

**Answer:** Currently NO. Bead creation uses `PermissionLevel` enum (READ/WRITE/ADMIN) not hiring authority.

**Recommendation:** Hiring authority SHOULD NOT affect bead permissions directly. They are orthogonal concerns:
- Bead permissions = who can view/edit work items
- Hiring authority = who can hire workers

**However:** Managers with hiring authority likely need:
- WRITE access to team's beads (for assigning work to new hires)
- ADMIN access to their direct reports' beads (for review/approval)

**Implementation Location:** `cli/core/permissions.py:can_worker_access_bead()`

**Question:** Should delegation grant additional bead permissions?

**Answer:** NO for general beads. YES for hiring-related beads.

**Pattern:**
```python
# When worker receives hiring authority:
# - Auto-subscribe to team's hiring channel
# - Grant WRITE on 'hiring' label beads
# - No change to general bead permissions
```

### 2.3 Recommendations

| Priority | Change | Location |
|----------|--------|----------|
| MUST | No change - keep bead permissions orthogonal | N/A |
| SHOULD | Auto-subscribe new managers to hiring channel | `Worker.delegate_authority()` |
| NICE | Add 'hiring' permission level for hiring-related beads | `cli/core/permissions.py` |

---

## 3. Event System

### 3.1 Current State

**File:** `cli/core/events.py`

Existing event types include:
```python
class EventType(Enum):
    # Worker events
    WORKER_HIRED = "worker.hired"
    WORKER_FIRED = "worker.fired"
    WORKER_PROMOTED = "worker.promoted"
    ...

    # Budget events
    BUDGET_WARNING = "budget.warning"
    BUDGET_EXHAUSTED = "budget.exhausted"
    BUDGET_DELEGATED = "budget.delegated"  # Already exists!
```

**Entity types (constants.py:308-338):**
```python
ENTITY_TYPE_WORKER = "worker"
ENTITY_TYPE_BUDGET = "budget"
# Missing: ENTITY_TYPE_DELEGATION
```

### 3.2 Integration Point

**Question:** Should delegation emit AUTHORITY_DELEGATED event?

**Answer:** YES. New event types needed:

```python
class EventType(Enum):
    # Delegation events (NEW)
    AUTHORITY_DELEGATED = "authority.delegated"
    AUTHORITY_REVOKED = "authority.revoked"
    AUTHORITY_CASCADE_REVOKED = "authority.cascade_revoked"
    AUTHORITY_EXPIRED = "authority.expired"
    AUTHORITY_MODIFIED = "authority.modified"
```

**New entity type:**
```python
ENTITY_TYPE_DELEGATION = "delegation"
```

**Event Payloads:**
```python
# AUTHORITY_DELEGATED
{
    "delegator_id": "director-001",
    "delegate_id": "manager-005",
    "scope": {"allowed_roles": ["engineer"], "max_cost": 50},
    "hiring_budget": 10000,
    "expires_at": null,  # or ISO timestamp
}

# AUTHORITY_REVOKED
{
    "delegator_id": "director-001",
    "delegate_id": "manager-005",
    "revoke_reason": "scope_reduction",  # or "termination", "manual", "expired"
    "cascade_count": 0,  # number of sub-delegations also revoked
}
```

**Question:** Who should receive event notifications?

**Answer:**
- `AUTHORITY_DELEGATED`: delegate (primary), delegator (audit), CEO (if P0 authority)
- `AUTHORITY_REVOKED`: delegate (primary), delegator (audit), affected sub-delegates (cascade)
- `AUTHORITY_CASCADE_REVOKED`: affected worker only

### 3.3 Recommendations

| Priority | Change | Location |
|----------|--------|----------|
| MUST | Add AUTHORITY_DELEGATED, AUTHORITY_REVOKED events | `cli/core/events.py` |
| MUST | Add ENTITY_TYPE_DELEGATION constant | `cli/core/constants.py` |
| MUST | Emit events in delegate_authority() and revoke_authority() | `cli/core/worker.py` |
| SHOULD | Add AUTHORITY_CASCADE_REVOKED for transparency | `cli/core/events.py` |
| NICE | Add event handler for notification creation | New subscription |

---

## 4. OKR System

### 4.1 Current State

**File:** `cli/commands/org/okr.py`, `cli/core/queries.py`

OKRs cascade from Board -> CEO -> Directors -> Managers -> Workers.

Key patterns:
- OKRs stored as beads issues with 'okr' label
- `owner_worker_id` tracks OKR ownership
- Key results tracked with progress metrics
- `parent_okr_id` creates OKR hierarchy

### 4.2 Integration Point

**Question:** Do managers with hiring authority need different OKRs?

**Answer:** Not necessarily different, but SHOULD have hiring-related key results.

**Pattern:**
```yaml
# Example OKR for manager with hiring authority
objective: "Build High-Performance Team"
key_results:
  - metric: "team_size"
    target: 10
    current: 7
  - metric: "time_to_fill"  # Days to fill open positions
    target: 14
    current: 21
  - metric: "new_hire_ramp_time"  # Days to productivity
    target: 30
    current: 45
```

**Question:** Should authority delegation trigger OKR review?

**Answer:** NICE to have. When delegation occurs:
1. Create notification bead for delegate
2. Suggest reviewing/creating team-building OKRs
3. No automatic OKR creation (too invasive)

**Question:** Can managers delegate OKR creation authority?

**Answer:** NO. OKR ownership follows org hierarchy, not delegation chain.
- OKRs are tied to reporting structure (`owner_worker_id` = worker who OWNS the objective)
- Delegation is about HIRING authority, not objective-setting authority

### 4.3 Recommendations

| Priority | Change | Location |
|----------|--------|----------|
| MUST | No change - keep OKRs independent of delegation | N/A |
| SHOULD | Add onboarding prompt for managers to set team OKRs | Onboarding templates |
| NICE | Add hiring-related OKR templates | `cli/config/templates/` |

---

## 5. Messaging/Notifications

### 5.1 Current State

**Files:** `cli/core/messaging.py`, `cli/core/notifications.py`, `cli/core/queries.py`

The messaging system provides:
```python
class MessagingService:
    def send_offboarding_notification(...)
    def create_direct_channel(...)
    def send_message(...)
    def notify_worker(...)
```

Notifications are ephemeral beads:
```python
@dataclass
class NotificationBead:
    id: str
    worker_id: str
    message_id: str
    channel_id: str
    status: str  # pending, read, actioned, closed
    priority: int
```

### 5.2 Integration Point

**Question:** Should worker receive notification when given authority?

**Answer:** YES. Use existing notification infrastructure.

**Implementation:**
```python
# In Worker.delegate_authority() after successful delegation
messaging = MessagingService(db)
channel_result = messaging.create_direct_channel(self.id, report.id)

message_result = messaging.send_message(
    channel_id=channel_result.channel_id,
    from_worker_id=self.id,
    content=(
        f"HIRING AUTHORITY GRANTED\n\n"
        f"You now have authority to hire workers.\n"
        f"Scope: {scope.allowed_roles}\n"
        f"Budget: ${hiring_budget}\n"
        f"Max cost per hire: {scope.max_cost}\n\n"
        f"Use 'qn org hire --manager={report.id}' to hire."
    ),
    priority=1,  # High priority
    time_sensitivity="hours",
)
```

**Question:** Format for delegation notifications?

**Answer:** Use existing notification bead structure with specific content:

```python
# Notification types for delegation
DELEGATION_NOTIFICATION_TYPES = {
    "authority_granted": {
        "priority": 1,
        "time_sensitivity": "hours",
        "title_template": "Hiring authority granted by {delegator_name}",
    },
    "authority_revoked": {
        "priority": 1,
        "time_sensitivity": "immediate",
        "title_template": "Hiring authority revoked",
    },
    "authority_expiring": {
        "priority": 2,
        "time_sensitivity": "days",
        "title_template": "Hiring authority expires in {days} days",
    },
}
```

### 5.3 Recommendations

| Priority | Change | Location |
|----------|--------|----------|
| MUST | Notify delegate when authority granted | `Worker.delegate_authority()` |
| MUST | Notify delegate when authority revoked | `revoke_authority()` |
| SHOULD | Notify affected sub-delegates on cascade revocation | `revoke_delegation_cascade()` |
| SHOULD | Post to board-channel for significant delegations | Event handler |
| NICE | Send expiration warnings (7 days, 1 day before) | Cleanup job |

---

## 6. Org Chart

### 6.1 Current State

**File:** `cli/core/org_chart.py`

The org chart system:
```python
def update_org_chart(db, org_path) -> Path:
    """Regenerate org-chart/current.yaml from database state."""
    # Walks worker hierarchy
    # Builds YAML structure
    # Writes to org-chart/current.yaml

def git_commit_org_chart(org_path, change_type, worker_name, ...):
    """Commit org-chart changes to git."""
```

Current YAML structure:
```yaml
version: "1.0"
workers:
  ceo-001:
    name: "Alice"
    role: "CEO"
    lifecycle: "active"
    manager: null
    reports: ["director-001", "director-002"]
hierarchy:
  root: "ceo-001"
```

### 6.2 Integration Point

**Question:** Does delegation affect org chart display?

**Answer:** YES. Add delegation status to worker entries.

**Proposed YAML enhancement:**
```yaml
workers:
  manager-005:
    name: "Carol"
    role: "Manager"
    lifecycle: "active"
    manager: "director-001"
    reports: ["engineer-010", "engineer-011"]
    # NEW: Delegation info
    hiring_authority:
      has_authority: true
      delegated_by: "director-001"
      allowed_roles: ["engineer"]
      max_cost: 50
      budget: 10000
      expires_at: null
```

**Question:** Should we show 'Manager (Hiring)' vs 'Manager (IC)' distinction?

**Answer:** YES, in display but not in role field.

**Implementation:**
```python
# In _build_worker_entry()
def _build_worker_entry(db, worker, workers_dict):
    has_authority = worker.hiring_authority_scope is not None

    workers_dict[worker.id] = {
        "name": worker.name,
        "role": worker.role,
        "lifecycle": worker.status,
        "manager": worker.manager_id,
        "reports": report_ids,
        # NEW
        "hiring_authority": {
            "has_authority": has_authority,
            "delegated_by": worker.delegated_by if has_authority else None,
            "scope": json.loads(worker.hiring_authority_scope) if has_authority else None,
        } if has_authority else None,
    }
```

**Question:** Git commit on delegation changes?

**Answer:** YES. Extend existing `git_commit_org_chart()`:

```python
# Add new change_type options
change_types = [
    "hired",
    "terminated",
    "promoted",
    "updated",
    "delegation_granted",  # NEW
    "delegation_revoked",  # NEW
]
```

### 6.3 Recommendations

| Priority | Change | Location |
|----------|--------|----------|
| MUST | Add hiring_authority section to org-chart YAML | `cli/core/org_chart.py` |
| SHOULD | Auto-commit org-chart on delegation changes | Event handler |
| SHOULD | Add delegation_granted/revoked change types | `git_commit_org_chart()` |
| NICE | Visual distinction in TUI dashboard | `terminal-app/views/` |

---

## 7. Session Lifecycle

### 7.1 Current State

**Files:** `cli/core/session.py`, `cli/core/sessions/`, `cli/core/onboarding.py`

Session spawning flow:
```python
# In onboarding.py
def prepare_worker_onboarding(db, worker_id, org_path):
    # Creates worker directory
    # Generates BRIEFING.md
    # Creates STORAGE.md guide
    # Creates WELCOME.md
    # Links architecture docs

def get_worker_env_vars(ctx, org_path, db) -> dict[str, str]:
    # Returns env vars for session:
    # WORKER_ID, WORKER_NAME, WORKER_ROLE, TEAM_NAME,
    # MANAGER_ID, ORG_PATH, WORKER_STORAGE, SHARED_STORAGE,
    # ORG_DB, BRIEFING_PATH, WORKER_BUDGET_ALLOCATED,
    # WORKER_COST_TIER, QUINN_SESSION_MODE
```

### 7.2 Integration Point

**Question:** Does delegation affect worker's session environment?

**Answer:** YES. Add authority-related env vars.

**New env vars:**
```python
# In get_worker_env_vars()
return {
    # ... existing vars ...

    # NEW: Hiring authority env vars
    "HIRING_AUTHORITY": "1" if ctx.has_hiring_authority else "0",
    "HIRING_AUTHORITY_ROLES": ",".join(scope.allowed_roles) if scope else "",
    "HIRING_AUTHORITY_MAX_COST": str(scope.max_cost) if scope else "0",
    "HIRING_BUDGET": str(ctx.hiring_budget_available),
    "DELEGATED_BY": ctx.delegated_by or "",
}
```

**Question:** Should managers with authority get different briefings?

**Answer:** YES. Add section to BRIEFING.md template.

**Template addition (briefing.md.jinja2):**
```markdown
{% if has_hiring_authority %}
## Hiring Authority

You have been granted hiring authority by {{ delegated_by_name }}.

**Scope:**
- Allowed roles: {{ allowed_roles | join(', ') }}
- Max cost per hire: {{ max_cost }}
- Budget: ${{ hiring_budget }}

**How to use:**
```bash
# List candidates (if integrated with recruiting system)
qn org candidates --role=engineer

# Hire a new worker
qn org hire --name="New Worker" --role=engineer --cost=50

# Check remaining budget
qn org hire-budget
```

**Responsibilities:**
- Only hire roles within your scope
- Stay within budget allocation
- Document hiring decisions in beads
{% endif %}
```

**Question:** Any onboarding changes for new managers?

**Answer:** YES. When worker receives delegation:
1. Regenerate BRIEFING.md with new section
2. Create notification about authority
3. Consider re-spawning session (if already running) - NICE to have

### 7.3 Recommendations

| Priority | Change | Location |
|----------|--------|----------|
| MUST | Add HIRING_AUTHORITY env vars to sessions | `cli/core/onboarding.py` |
| MUST | Add hiring authority section to BRIEFING.md | `cli/config/templates/briefing.md.jinja2` |
| SHOULD | Regenerate briefing when delegation changes | Event handler |
| NICE | Restart session to pick up new env vars | Session management |

---

## 8. Storage Permissions

### 8.1 Current State

**File:** `cli/core/storage.py`

Storage structure:
```
storage/
|-- shared/              # Org lifetime
|   |-- engineering/
|   |-- legal/
|   |-- company/
|   |-- teams/{team}/    # Team-specific
|-- workers/             # Worker lifetime (mirrors org-chart)
    |-- ceo/
        |-- director-abc/
        |   |-- engineer-xyz/
```

`StorageManager` provides:
```python
def get_worker_path(worker_id, reports_to) -> Path
def get_shared_path(topic) -> Path
def ensure_worker_storage(worker_id, reports_to) -> Path
def ensure_shared_storage(topic) -> Path
```

### 8.2 Integration Point

**Question:** Do managers with hiring authority need access to team storage?

**Answer:** Managers ALREADY have access to shared storage. Delegation doesn't change this.

**Current access model:**
- Workers can read/write their own storage: `storage/workers/{path}/{id}/`
- Workers can read/write shared storage: `storage/shared/{topic}/`
- Workers CANNOT access other workers' storage directly

**Question:** Should delegation grant storage creation permissions?

**Answer:** NO for worker storage (still follows org-chart).
**YES** for team-specific storage under shared/:

```python
# When manager receives hiring authority, ensure team storage exists
def on_authority_delegated(event: Event):
    # Get manager's team
    worker = get_worker(db, event.entity_id)
    team = get_team(db, worker.team_id)

    # Ensure team storage exists
    storage = StorageManager(org_path, db)
    storage.ensure_shared_storage(f"teams/{team.name}/hiring")
    storage.ensure_shared_storage(f"teams/{team.name}/candidates")
```

**Question:** Any storage quotas for managers?

**Answer:** Currently NO quotas exist. Consider for V2:
- Per-worker storage limits
- Team storage limits based on team size
- Hiring budget could correlate with storage allowance

### 8.3 Recommendations

| Priority | Change | Location |
|----------|--------|----------|
| MUST | No change - storage already accessible | N/A |
| SHOULD | Create team/hiring storage on delegation | Event handler |
| NICE | Add storage quotas correlated with authority | V2 enhancement |

---

## Integration Checklist

### P0: Must Fix for MVP (breaks without it)

| Item | Status | Integration Point | Notes |
|------|--------|-------------------|-------|
| Budget sync - delegated budget validates against allocation | TODO | `Worker.delegate_authority()` | Prevent over-delegation |
| Events - AUTHORITY_DELEGATED/REVOKED emitted | TODO | `cli/core/events.py` | Audit trail |
| Lifecycle check - only active workers can delegate/receive | PARTIAL | `Worker.delegate_authority()` | Check exists but incomplete |
| Self-delegation prevention | TODO | Schema CHECK constraint | Database level |

### P1: Should Fix for V1 (poor UX without it)

| Item | Status | Integration Point | Notes |
|------|--------|-------------------|-------|
| Org chart shows delegation status | TODO | `cli/core/org_chart.py` | Visual clarity |
| Session env vars include authority | TODO | `cli/core/onboarding.py` | Worker awareness |
| Notifications on delegation | TODO | `cli/core/messaging.py` | Worker informed |
| Briefing includes authority section | TODO | Templates | Onboarding |
| Git commit on delegation changes | TODO | Event handler | Audit |

### P2: Nice to Have for V2 (enhancement)

| Item | Status | Integration Point | Notes |
|------|--------|-------------------|-------|
| OKR templates for hiring managers | TODO | Templates | Guidance |
| Hiring-related bead permissions | TODO | `cli/core/permissions.py` | Fine-grained |
| Team storage auto-creation | TODO | Event handler | Convenience |
| Session restart on authority change | TODO | Session management | Seamless |
| Storage quotas tied to authority | TODO | `cli/core/storage.py` | Resource limits |
| Delegation dashboard view | TODO | Terminal app | Visibility |

---

## Gaps Identified

### Integrated Architecture (Good)

1. **Budget System** - Delegation fits naturally into existing cascade pattern
2. **Event System** - Clear extension point with existing `BUDGET_DELEGATED` precedent
3. **Authorization** - `AuthorizationManager.can()` already structured for this
4. **Messaging** - Notification infrastructure ready for delegation messages

### Bolted-On Concerns (Address)

1. **OKR System** - No natural integration point. Delegation is orthogonal to OKRs.
   - **Mitigation:** Keep them independent. Add templates as guidance only.

2. **Session Environment** - Currently no dynamic env var updates.
   - **Mitigation:** Regenerate briefing on delegation. Consider session restart.

3. **Org Chart YAML** - Schema needs extension for delegation info.
   - **Mitigation:** Add `hiring_authority` section to worker entries.

4. **Bead Permissions** - Permission model doesn't consider delegation.
   - **Mitigation:** Keep orthogonal. Delegation affects hiring, not bead access.

### Missing Infrastructure

1. **Delegation Event Handler** - No central handler to coordinate cross-system updates
   - **Recommendation:** Create `cli/core/delegation_handler.py` that:
     - Subscribes to delegation events
     - Triggers org chart update
     - Sends notifications
     - Creates team storage
     - Regenerates briefings

2. **Delegation CLI Commands** - Current `wrkr delegate` is for task delegation, not authority
   - **Recommendation:** Add to `cli/commands/org/`:
     - `qn org delegate-authority --to <worker> --scope <preset>`
     - `qn org revoke-authority --from <worker>`
     - `qn org show-delegations`

---

## Priority Matrix

### P0: Must Have for Production

| Feature | Effort | Impact | Risk if Missing |
|---------|--------|--------|-----------------|
| Budget validation in delegate_authority() | 2h | High | Over-allocation, budget exhaustion |
| Event emission (DELEGATED/REVOKED) | 2h | High | No audit trail, no notifications |
| Self-delegation CHECK constraint | 1h | High | Security vulnerability |
| Lifecycle status checks | 1h | High | Terminated workers keeping authority |

### P1: Should Have for V1

| Feature | Effort | Impact | Risk if Missing |
|---------|--------|--------|-----------------|
| Org chart delegation display | 4h | Medium | Poor visibility |
| Session env vars | 2h | Medium | Workers unaware of authority |
| Notifications | 3h | Medium | Workers not informed |
| Briefing template update | 2h | Medium | Poor onboarding |
| Git commits on delegation | 2h | Low | No version control |

### P2: Nice to Have for V2

| Feature | Effort | Impact | Risk if Missing |
|---------|--------|--------|-----------------|
| OKR templates | 4h | Low | Less guidance |
| Team storage auto-create | 2h | Low | Manual setup |
| Delegation dashboard | 8h | Medium | Less visibility |
| Storage quotas | 8h | Low | Unbounded growth |

---

## Implementation Roadmap

### Phase 1: Core Integration (Week 1)

1. Add delegation event types to `events.py`
2. Add ENTITY_TYPE_DELEGATION to `constants.py`
3. Implement event emission in `Worker.delegate_authority()`
4. Add budget validation to delegation flow
5. Add CHECK constraints to schema

### Phase 2: User Experience (Week 2)

6. Update org chart YAML schema
7. Add org chart event handler
8. Add session env vars for authority
9. Update briefing template
10. Implement notifications

### Phase 3: CLI & Dashboard (Week 3)

11. Add `qn org delegate-authority` command
12. Add `qn org revoke-authority` command
13. Add `qn org show-delegations` command
14. Update TUI dashboard

### Phase 4: Polish (Week 4)

15. Add OKR templates
16. Add team storage auto-creation
17. Add delegation dashboard view
18. Write documentation

---

## Conclusion

The hiring authority delegation system is well-positioned to integrate as a first-class component in QuinnAI. The primary integration points are:

1. **Budget System** - Mirror existing delegation patterns
2. **Event System** - Extend with new event types
3. **Org Chart** - Add authority metadata to worker entries
4. **Sessions** - Add env vars and update briefings

The key insight is that delegation is **analogous to budget allocation** - both are cascading authority transfers. Using the same patterns ensures consistency and reduces implementation risk.

**Estimated Total Effort:** 40-50 hours across 4 weeks

**Next Steps:**
1. Review this validation with team
2. Prioritize P0 items for immediate implementation
3. Create beads issues for each work item
4. Begin Phase 1 implementation

---

**File References:**
- Budget System: `/Users/qosha/Repos/small-bizs/agentic-tools/quinnai/cli/core/budget.py`
- Authorization: `/Users/qosha/Repos/small-bizs/agentic-tools/quinnai/cli/core/authorization.py`
- Events: `/Users/qosha/Repos/small-bizs/agentic-tools/quinnai/cli/core/events.py`
- OKR: `/Users/qosha/Repos/small-bizs/agentic-tools/quinnai/cli/commands/org/okr.py`
- Messaging: `/Users/qosha/Repos/small-bizs/agentic-tools/quinnai/cli/core/messaging.py`
- Notifications: `/Users/qosha/Repos/small-bizs/agentic-tools/quinnai/cli/core/notifications.py`
- Org Chart: `/Users/qosha/Repos/small-bizs/agentic-tools/quinnai/cli/core/org_chart.py`
- Session: `/Users/qosha/Repos/small-bizs/agentic-tools/quinnai/cli/core/session.py`
- Onboarding: `/Users/qosha/Repos/small-bizs/agentic-tools/quinnai/cli/core/onboarding.py`
- Storage: `/Users/qosha/Repos/small-bizs/agentic-tools/quinnai/cli/core/storage.py`
- Constants: `/Users/qosha/Repos/small-bizs/agentic-tools/quinnai/cli/core/constants.py`
