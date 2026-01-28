# ADR-005: Delegation Authority System

**Status:** Accepted
**Date:** 2026-01-28
**Deciders:** Core team
**Epic:** quinnai-cr2v.9

## Context

QuinnAI organizations need to scale beyond single CEO management. As orgs grow to 10+ workers, hierarchical management with delegated hiring authority becomes essential for:

1. **Scalability**: CEO can't manually hire every worker
2. **Autonomy**: Managers should hire their own teams
3. **Accountability**: Clear authority chains for hiring decisions
4. **Security**: Prevent unauthorized hiring or authority escalation

## Decision

Implement a **hierarchical delegation authority system** where:

1. Hiring authority can be delegated from manager to direct report
2. Delegated authority is a **subset** of delegator's authority (roles, cost, budget)
3. Authority can be revoked, with optional cascade to downstream delegations
4. All delegations are tracked in audit log for accountability

### Core Design Principles

#### 1. Budget Analogy

Delegation works like budget allocation:
- Manager has delegated budget (e.g., $1000)
- Can sub-allocate to reports (e.g., $200 to Alice, $300 to Bob)
- Cannot delegate more than available
- Revocation returns budget to delegator

#### 2. Subset Constraints

Delegated authority must be **strictly subset** of delegator's:
```
CEO: [all roles, cost 100, budget 10000]
  └─> Director: [engineer,qa,designer, cost 70, budget 2000]
       └─> Manager: [engineer,qa, cost 50, budget 500]
```

#### 3. Security-First

Four P0 vulnerabilities addressed:

| Vulnerability | Prevention |
|--------------|------------|
| Self-delegation | Check `report.id != self.id` |
| Circular delegation | Graph cycle detection via BFS |
| Terminated worker delegation | Lifecycle status validation |
| Concurrent modification | Optimistic locking with `delegation_version` |

#### 4. Explicit Over Implicit

- Cascade revocation requires `--cascade` flag
- Dry-run mode (`--dry-run`) previews changes
- Interactive prompts before destructive operations
- Audit trail for all delegation changes

## Implementation

### Database Schema

**Migration v17** adds:

```sql
-- Delegation grants (active delegations)
CREATE TABLE delegation_grants (
    id TEXT PRIMARY KEY,
    delegator_id TEXT NOT NULL,  -- Who delegated
    delegate_id TEXT NOT NULL,    -- Who received authority
    granted_at TIMESTAMP NOT NULL,
    granted_scope TEXT NOT NULL,  -- JSON HiringScope
    granted_budget INTEGER NOT NULL,
    FOREIGN KEY (delegator_id) REFERENCES workers(id) ON DELETE CASCADE,
    FOREIGN KEY (delegate_id) REFERENCES workers(id) ON DELETE CASCADE,
    UNIQUE (delegate_id)  -- Each worker has at most one active delegation
);

-- Audit trail (immutable log)
CREATE TABLE delegation_audit (
    id TEXT PRIMARY KEY,
    action TEXT NOT NULL,  -- 'granted', 'revoked', 'expired'
    delegator_id TEXT NOT NULL,
    delegate_id TEXT NOT NULL,
    scope TEXT NOT NULL,
    budget INTEGER NOT NULL,
    performed_at TIMESTAMP NOT NULL,
    performed_by TEXT,
    reason TEXT
);

-- Optimistic locking on workers table
ALTER TABLE workers ADD COLUMN delegation_version INTEGER DEFAULT 0;
```

**Triggers:**
- `revoke_delegations_on_termination`: Auto-revoke when worker terminated
- `log_delegation_grant`: Auto-log to audit trail on grant
- `log_delegation_revoke`: Auto-log to audit trail on revoke

### CLI Commands

#### Low-Level Commands

**`qn org delegate-authority`**
- Grant hiring authority to direct report
- Modes: preset levels, custom roles, copy-from
- Validation: subset constraints, lifecycle checks, cycle detection

**`qn org revoke-authority`**
- Remove hiring authority
- Modes: single worker, cascade to downstream
- Safety: blocks if has downstream (unless --cascade)

#### High-Level Commands

**`qn org promote`**
- Convenience wrapper for delegation with preset levels
- Preset levels: team-lead, director, vp
- Internally calls `delegate-authority`

**`qn org demote`**
- Convenience wrapper for revocation
- Internally calls `revoke-authority --cascade`

#### Visibility

**`qn org delegations`**
- List all active delegations
- Tree view of delegation chain
- JSON output for automation

### Integration

**`qn org fire`** integration:
- Auto-revokes authority on termination
- Cascade revokes downstream delegations
- Prevents orphaned authority grants

**`qn org status`** integration:
- Shows count of managers (workers with authority)
- Displays CEO authority level

## Alternatives Considered

### Alternative 1: Role-Based Access Control (RBAC)

**Approach:** Predefined roles (Team Lead, Director, VP) with fixed permissions

**Rejected because:**
- Too rigid - can't customize per org/situation
- Doesn't handle budget allocation
- No delegation chain for accountability

### Alternative 2: Flat Permissions

**Approach:** Each worker has independent permissions, no delegation chain

**Rejected because:**
- No audit trail of who granted authority
- Can't revoke downstream authority
- Security risk: workers could grant themselves authority

### Alternative 3: Automatic Delegation on Hire

**Approach:** When hiring a manager, automatically grant appropriate authority

**Rejected because:**
- Too magic - unclear what authority was granted
- No explicit approval step
- Harder to audit and debug

## Consequences

### Positive

✅ **Scalability**: Orgs can grow beyond CEO micromanagement
✅ **Security**: P0 vulnerabilities prevented by design
✅ **Auditability**: Complete trail of delegation changes
✅ **Flexibility**: Supports both preset and custom authority
✅ **Safety**: Explicit flags for dangerous operations
✅ **Testability**: Clear contracts, comprehensive edge case tests

### Negative

⚠️ **Complexity**: More commands for users to learn
⚠️ **Migration**: Existing orgs need backfill (handled by migration)
⚠️ **Performance**: Cycle detection adds overhead (acceptable for rare operation)

### Neutral

➡️ **Budget tracking**: Delegated budget set but not yet consumed on hire (future enhancement)
➡️ **Max depth**: No hard limit on delegation chain depth (graph cycle detection prevents infinite loops)
➡️ **Transfer delegation**: Not implemented in V1 (use revoke + re-delegate pattern)

## Validation

### Test Coverage

- **140 unit tests** passing (worker lifecycle, delegation logic)
- **16 baseline integration tests** passing (hierarchical hiring)
- **13 edge case tests** (3 passing, 10 document future enhancements)

### Security Validation

All P0 vulnerabilities tested:
- ✅ Self-delegation blocked
- ✅ Circular delegation detected
- ✅ Terminated worker delegation prevented
- ✅ Concurrent modification handled

### User Validation

Example workflow validated:
```bash
# CEO hires Director
qn org hire --name Alice --role Director --manager CEO

# CEO promotes Alice to director level
qn org promote Alice --to director

# Alice hires Manager
qn org hire --name Bob --role Manager --manager Alice  # Works (Alice has authority)

# Alice promotes Bob to team-lead
qn org promote Bob --to team-lead

# Bob hires Engineer
qn org hire --name Carol --role engineer --manager Bob  # Works (Bob has authority)

# View delegation tree
qn org delegations --tree
# Output:
# CEO [all roles, cost 100]
# └── Alice (director) [engineer,analyst,designer,manager, cost 70]
#     └── Bob (team-lead) [engineer,analyst, cost 50]

# Revoke Alice's authority (cascade to Bob)
qn org revoke-authority Alice --cascade
# Result: Both Alice and Bob lose hiring authority
```

## References

- Epic planning: `scratchpad/delegation-epic-complete-summary.md`
- Safety analysis: `scratchpad/delegation-safety-analysis.md`
- Command design: `scratchpad/delegation-command-design.md`
- Database schema: `scratchpad/delegation-database-schema.md`
- Integration validation: `scratchpad/delegation-integration-validation.md`

## Future Enhancements

1. **Budget consumption**: Track and enforce budget usage on hire (quinnai-4m5r)
2. **Optimistic locking retry**: Exponential backoff on concurrent conflicts (quinnai-yrtf)
3. **Delegation transfer**: Transfer downstream delegations during revocation
4. **Time-limited delegation**: Expiring authority grants
5. **Notification system**: Alert when authority granted/revoked
6. **Delegation metrics**: Track delegation depth, authority utilization

## Notes

This ADR represents the culmination of:
- 16 hours of planning (Investigation → Safety → Design → Validation → Scope)
- 6 comprehensive design documents
- 4 P0 security vulnerabilities identified and addressed
- 32-hour implementation estimate across 6 phases
- Phases 1-4 complete (database, commands, integration, testing)

The delegation system integrates cleanly into existing architecture because it follows the established pattern of budget allocation - a familiar mental model for users and a proven implementation pattern for the codebase.
