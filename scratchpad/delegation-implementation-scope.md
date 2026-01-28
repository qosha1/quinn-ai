# Delegation Implementation Scope

**Date:** 2026-01-28
**Author:** Claude Sonnet 4.5
**Status:** Implementation-ready task breakdown
**Estimated Total Time:** 32 hours (4 days)

---

## Executive Summary

This document provides a complete, implementation-ready breakdown of the hiring authority delegation feature for QuinnAI. The delegation system enables managers to grant subordinates hiring authority within specified constraints, creating a cascade of authority from CEO → Directors → Managers.

**Key Deliverables:**
- Database migration (v16 → v17) with delegation_grants and delegation_audit tables
- 4 new CLI commands (delegate-authority, revoke-authority, promote, demote, delegations)
- Enhanced Worker.delegate_authority() with P0 security fixes
- Comprehensive test suite (20+ test cases)
- Documentation (ADR, README updates, command help)

**Critical P0 Vulnerabilities Fixed:**
1. Self-delegation prevention
2. Terminated worker validation
3. Circular delegation detection
4. Optimistic locking for concurrent modifications

---

## 1. File Manifest

### 1.1 New Files

| File Path | LOC | Purpose |
|-----------|-----|---------|
| `cli/core/delegation.py` | ~200 | Delegation business logic (preset expansion, validation, tree formatting) |
| `cli/commands/org/delegate_authority.py` | ~120 | CLI command for delegating authority |
| `cli/commands/org/revoke_authority.py` | ~150 | CLI command for revoking authority |
| `cli/commands/org/promote.py` | ~100 | CLI command for promoting to manager |
| `cli/commands/org/demote.py` | ~120 | CLI command for demoting from manager |
| `cli/commands/org/delegations.py` | ~180 | CLI command for listing delegations |
| `cli/tests/test_delegation_unit.py` | ~400 | Unit tests for delegation logic |
| `cli/tests/test_delegation_integration.py` | ~600 | Integration tests for CLI commands |
| `docs/architecture-decisions/ADR-006-delegation.md` | ~300 | Architecture decision record |
| **Total New Files** | **~2,170 LOC** | |

### 1.2 Modified Files

| File Path | Changes | Est. LOC |
|-----------|---------|----------|
| `cli/core/db.py` | Add migration v17, update SCHEMA_VERSION | +300 |
| `cli/core/queries.py` | Add 8 new delegation query functions | +250 |
| `cli/core/worker.py` | Enhance delegate_authority(), add revoke_authority() | +150 |
| `cli/core/constants.py` | Add delegation preset and event constants | +30 |
| `cli/commands/org/__init__.py` | Register 5 new commands | +5 |
| `cli/tests/test_worker.py` | Update test_hierarchical_hiring | +50 |
| `README.md` | Add delegation examples and command reference | +100 |
| **Total Modified** | | **+885 LOC** |

### 1.3 Total Implementation Size

**Total Lines of Code:** ~3,055 LOC
**Test Coverage:** ~1,000 LOC (33% of total)

---

## 2. Function Signatures

### 2.1 Database Layer (cli/core/queries.py)

```python
@dataclass
class DelegationGrant:
    """Delegation grant record."""
    id: str
    delegator_id: str
    delegate_id: str
    scope: dict  # HiringScope JSON
    budget_amount: int
    granted_at: datetime
    expires_at: Optional[datetime]
    revoked_at: Optional[datetime]
    revoked_by: Optional[str]
    revoke_reason: Optional[str]
    granted_by_cli_user: Optional[str]
    metadata: Optional[dict]


@dataclass
class DelegationAuditRecord:
    """Delegation audit trail record."""
    id: str
    event_type: str  # granted, revoked, expired, cascade_revoked, etc.
    delegator_id: str
    delegate_id: str
    delegation_grant_id: Optional[str]
    scope_before: Optional[dict]
    scope_after: Optional[dict]
    budget_before: Optional[int]
    budget_after: Optional[int]
    performed_by: str
    performed_by_cli_user: Optional[str]
    reason: Optional[str]
    timestamp: datetime


@dataclass
class RevokeResult:
    """Result of delegation revocation."""
    revoked_grant_ids: list[str]
    cascade_count: int
    affected_workers: list[str]


def create_delegation_grant(
    db: Database,
    delegator_id: str,
    delegate_id: str,
    scope: dict,
    budget: int,
    granted_by_cli_user: Optional[str] = None,
    expires_at: Optional[datetime] = None,
) -> DelegationGrant:
    """Create a new delegation grant.

    Args:
        db: Database instance
        delegator_id: Worker ID granting authority
        delegate_id: Worker ID receiving authority
        scope: HiringScope dict (allowed_roles, max_cost, max_budget)
        budget: Budget amount to delegate
        granted_by_cli_user: Optional CLI user who initiated grant
        expires_at: Optional expiration timestamp

    Returns:
        Created DelegationGrant

    Raises:
        ValueError: If delegate already has active delegation
        sqlite3.IntegrityError: If workers don't exist or self-delegation
    """


def get_delegation_grant(
    db: Database,
    delegate_id: str,
) -> Optional[DelegationGrant]:
    """Get active delegation grant for a delegate.

    Args:
        db: Database instance
        delegate_id: Worker ID to check

    Returns:
        Active DelegationGrant or None if no active delegation
    """


def revoke_delegation_grant(
    db: Database,
    delegate_id: str,
    revoked_by: str,
    reason: Optional[str] = None,
    cascade: bool = False,
) -> RevokeResult:
    """Revoke delegation grant for a delegate.

    Args:
        db: Database instance
        delegate_id: Worker ID whose delegation to revoke
        revoked_by: Worker ID performing revocation
        reason: Optional human-readable reason
        cascade: If True, also revoke delegations granted by this delegate

    Returns:
        RevokeResult with details of revocation

    Raises:
        ValueError: If no active delegation found
    """


def get_delegation_chain(
    db: Database,
    worker_id: str,
) -> list[DelegationGrant]:
    """Get complete delegation chain for a worker.

    Returns chain from root (CEO) down to worker, or empty list if
    worker has no delegation.

    Args:
        db: Database instance
        worker_id: Worker ID to trace

    Returns:
        List of DelegationGrants in chain order (root → leaf)
    """


def check_delegation_cycle(
    db: Database,
    delegator_id: str,
    delegate_id: str,
) -> bool:
    """Check if delegation would create a circular reference.

    Args:
        db: Database instance
        delegator_id: Worker ID granting authority
        delegate_id: Worker ID receiving authority

    Returns:
        True if cycle would be created, False otherwise
    """


def get_delegation_audit(
    db: Database,
    worker_id: Optional[str] = None,
    limit: int = 100,
) -> list[DelegationAuditRecord]:
    """Get delegation audit records.

    Args:
        db: Database instance
        worker_id: Optional filter by delegator or delegate
        limit: Maximum records to return

    Returns:
        List of audit records, newest first
    """


def expire_delegations(db: Database) -> list[str]:
    """Expire delegations past their expires_at timestamp.

    Called periodically (e.g., on org start, before delegation operations).

    Args:
        db: Database instance

    Returns:
        List of expired delegation grant IDs
    """


def get_delegations_by_delegator(
    db: Database,
    delegator_id: str,
    include_revoked: bool = False,
) -> list[DelegationGrant]:
    """Get delegations granted by a delegator.

    Args:
        db: Database instance
        delegator_id: Worker ID who granted delegations
        include_revoked: Include revoked delegations

    Returns:
        List of DelegationGrants
    """
```

### 2.2 Core Logic (cli/core/worker.py)

```python
def delegate_authority(
    self,
    report: "Worker",
    budget: int,
    scope: HiringScope,
    granted_by_cli_user: Optional[str] = None,
    expires_at: Optional[datetime] = None,
) -> DelegationGrant:
    """Delegate hiring authority to a direct report.

    ENHANCED VERSION with P0 security fixes:
    - Prevents self-delegation
    - Validates delegate lifecycle status
    - Detects circular delegation
    - Uses optimistic locking

    Args:
        report: Worker to delegate authority to (must be direct report)
        budget: Budget to delegate
        scope: HiringScope defining allowed roles/costs
        granted_by_cli_user: Optional CLI user initiating delegation
        expires_at: Optional expiration timestamp

    Returns:
        Created DelegationGrant

    Raises:
        ValueError: If report is not direct report, self-delegation, or terminated
        InsufficientHiringAuthority: If budget exceeds delegator's budget
        CircularDelegationError: If delegation would create cycle
        ConcurrentModificationError: If delegator's budget changed during operation
    """


def revoke_authority(
    self,
    delegate: "Worker",
    cascade: bool = False,
    reason: Optional[str] = None,
) -> RevokeResult:
    """Revoke hiring authority from a delegate.

    Args:
        delegate: Worker whose authority to revoke
        cascade: If True, revoke delegations granted by delegate
        reason: Optional human-readable reason

    Returns:
        RevokeResult with revocation details

    Raises:
        ValueError: If no active delegation found
        InvalidStateTransition: If delegate in invalid lifecycle state
    """


def can_hire(self, cost: int) -> bool:
    """Check if worker can hire someone with given cost.

    ENHANCED VERSION: Checks delegation expiry.

    Args:
        cost: Cost score of candidate worker

    Returns:
        True if worker has authority and budget, False otherwise
    """
```

### 2.3 Delegation Business Logic (cli/core/delegation.py)

```python
@dataclass
class HiringScope:
    """Hiring scope constraints."""
    allowed_roles: set[str]
    max_cost: int
    max_budget: int

    def to_json(self) -> str:
        """Serialize to JSON."""

    @classmethod
    def from_json(cls, json_str: str) -> "HiringScope":
        """Deserialize from JSON."""

    def allows_role(self, role: str) -> bool:
        """Check if role is allowed."""

    def allows_cost(self, cost: int) -> bool:
        """Check if cost is within limit."""


# Delegation presets
DELEGATION_PRESETS = {
    "team-lead": {
        "allowed_roles": {"engineer", "designer", "qa"},
        "max_cost": 60,
        "max_budget": 5000,
    },
    "director": {
        "allowed_roles": {"engineer", "designer", "qa", "manager", "team-lead"},
        "max_cost": 80,
        "max_budget": 20000,
    },
    "vp": {
        "allowed_roles": {"*"},  # All roles
        "max_cost": 90,
        "max_budget": 100000,
    },
}


def expand_delegation_preset(preset_name: str) -> HiringScope:
    """Expand a delegation preset to HiringScope.

    Args:
        preset_name: Preset name (team-lead, director, vp)

    Returns:
        HiringScope instance

    Raises:
        ValueError: If preset not found
    """


def format_delegation_tree(
    grants: list[DelegationGrant],
    workers: dict[str, str],  # worker_id -> name mapping
) -> str:
    """Format delegation grants as ASCII tree.

    Args:
        grants: List of DelegationGrants
        workers: Mapping of worker IDs to names

    Returns:
        ASCII tree representation

    Example:
        CEO (Alice)
        ├── Director (Bob) [budget: $10K, roles: engineer,manager]
        │   ├── Team Lead (Carol) [budget: $3K, roles: engineer]
        │   └── Team Lead (Dave) [budget: $3K, roles: engineer]
        └── Director (Eve) [budget: $10K, roles: engineer,manager]
    """


def validate_delegation_scope(
    delegator_scope: HiringScope,
    delegate_scope: HiringScope,
) -> tuple[bool, Optional[str]]:
    """Validate that delegate scope is subset of delegator scope.

    Args:
        delegator_scope: Delegator's hiring scope
        delegate_scope: Proposed delegate scope

    Returns:
        (valid, error_message) tuple
    """
```

---

## 3. Test Case List

### 3.1 Unit Tests (cli/tests/test_delegation_unit.py)

```python
def test_self_delegation_blocked(db, ceo):
    """Verify self-delegation is prevented."""
    # P0 security fix validation


def test_delegate_to_terminated_blocked(db, ceo, terminated_worker):
    """Verify cannot delegate to terminated worker."""
    # P0 security fix validation


def test_delegate_from_terminated_blocked(db, terminated_manager, report):
    """Verify terminated worker cannot delegate."""
    # P0 security fix validation


def test_circular_delegation_detected(db, alice, bob, carol):
    """Verify circular delegation is detected.

    Scenario: Alice → Bob → Carol → Alice (should fail)
    """
    # P0 security fix validation


def test_concurrent_delegation_fails(db, manager):
    """Verify optimistic locking prevents concurrent delegation."""
    # P0 security fix validation


def test_preset_expansion_team_lead(db):
    """Verify team-lead preset expands correctly."""


def test_preset_expansion_director(db):
    """Verify director preset expands correctly."""


def test_preset_expansion_vp(db):
    """Verify vp preset expands correctly."""


def test_preset_not_found(db):
    """Verify unknown preset raises ValueError."""


def test_delegation_grant_created(db, delegator, delegate):
    """Verify create_delegation_grant creates record."""


def test_delegation_audit_logged(db, delegator, delegate):
    """Verify delegation creates audit record."""


def test_delegation_scope_validation(db):
    """Verify delegate scope must be subset of delegator scope."""


def test_delegation_chain_retrieval(db, ceo, director, manager):
    """Verify get_delegation_chain returns correct chain."""


def test_delegation_expiry(db, delegator, delegate):
    """Verify expired delegations are detected."""


def test_cascade_revocation(db, delegator, delegate, sub_delegate):
    """Verify cascade revocation revokes entire chain."""
```

### 3.2 Integration Tests (cli/tests/test_delegation_integration.py)

```python
def test_delegate_authority_command(org_path, cli_runner):
    """Test qn org delegate-authority command."""


def test_delegate_authority_with_preset(org_path, cli_runner):
    """Test qn org delegate-authority --level=team-lead."""


def test_delegate_authority_custom_scope(org_path, cli_runner):
    """Test qn org delegate-authority --roles=engineer,qa --max-cost=50."""


def test_delegate_authority_not_direct_report(org_path, cli_runner):
    """Verify error when delegate is not direct report."""


def test_delegate_authority_insufficient_budget(org_path, cli_runner):
    """Verify error when delegator lacks budget."""


def test_revoke_authority_command(org_path, cli_runner):
    """Test qn org revoke-authority command."""


def test_revoke_authority_cascade(org_path, cli_runner):
    """Test qn org revoke-authority --cascade."""


def test_revoke_authority_interactive_prompt(org_path, cli_runner):
    """Test interactive confirmation for cascade revocation."""


def test_revoke_authority_no_delegation(org_path, cli_runner):
    """Verify error when worker has no delegation."""


def test_promote_command(org_path, cli_runner):
    """Test qn org promote worker --to=team-lead."""


def test_promote_already_has_delegation(org_path, cli_runner):
    """Test promote when worker already has delegation."""


def test_demote_command(org_path, cli_runner):
    """Test qn org demote worker."""


def test_demote_cascade(org_path, cli_runner):
    """Test qn org demote worker --cascade."""


def test_delegations_list_command(org_path, cli_runner):
    """Test qn org delegations."""


def test_delegations_list_for_worker(org_path, cli_runner):
    """Test qn org delegations --worker=alice."""


def test_delegations_tree_command(org_path, cli_runner):
    """Test qn org delegations --tree."""


def test_hire_uses_delegation(org_path, cli_runner):
    """Test that qn org hire checks delegation expiry."""


def test_fire_revokes_delegation(org_path, cli_runner):
    """Test that qn org fire auto-revokes delegation."""


def test_delegation_e2e_workflow(org_path, cli_runner):
    """End-to-end: delegate → hire → revoke → verify."""
```

### 3.3 Updated Tests (cli/tests/test_worker.py)

```python
def test_hierarchical_hiring(db, org_path):
    """Test multi-level hiring with delegation.

    CURRENTLY SKIPPED - will be unskipped and updated.

    Scenario:
    1. CEO delegates to Director
    2. Director delegates to Manager
    3. Manager hires Engineer
    4. Verify budget tracking
    5. Verify authority constraints
    """


def test_delegation_prevents_hiring_without_authority(db, worker):
    """Verify worker without delegation cannot hire."""


def test_delegation_expires(db, delegator, delegate):
    """Verify expired delegation prevents hiring."""
```

---

## 4. Implementation Checklist

### Phase 1: Database Foundation (P0) - 4 hours

- [ ] **Task 1.1:** Create migration script v16→v17 (1 hour)
  - Add `delegation_grants` table with all constraints
  - Add `delegation_audit` table
  - Add triggers for auto-audit logging
  - Add trigger for cascade revocation on worker termination
  - Dependencies: None

- [ ] **Task 1.2:** Add delegation queries to `cli/core/queries.py` (2 hours)
  - `create_delegation_grant()`
  - `get_delegation_grant()`
  - `revoke_delegation_grant()`
  - `get_delegation_chain()`
  - `check_delegation_cycle()`
  - `get_delegation_audit()`
  - `expire_delegations()`
  - `get_delegations_by_delegator()`
  - Dependencies: Task 1.1

- [ ] **Task 1.3:** Write migration rollback script (30 min)
  - Script to safely revert v17→v16
  - Document data loss warnings
  - Dependencies: Task 1.1

- [ ] **Task 1.4:** Test migration on sample orgs (30 min)
  - Create test org with existing workers
  - Run migration v16→v17
  - Verify schema correctness
  - Test rollback
  - Dependencies: Task 1.1, 1.3

### Phase 2: Core Logic (P1) - 6 hours

- [ ] **Task 2.1:** Add delegation business logic (2 hours)
  - Create `cli/core/delegation.py`
  - Implement `HiringScope` dataclass
  - Add `DELEGATION_PRESETS` constant dict
  - Implement `expand_delegation_preset()`
  - Implement `validate_delegation_scope()`
  - Implement `format_delegation_tree()`
  - Dependencies: None

- [ ] **Task 2.2:** Enhance `Worker.delegate_authority()` (2 hours)
  - Add self-delegation check (P0)
  - Add lifecycle validation (P0)
  - Add circular delegation check (P0)
  - Add optimistic locking with delegation_version (P0)
  - Use `create_delegation_grant()` query
  - Update to use new delegation_grants table
  - Dependencies: Task 1.2, 2.1

- [ ] **Task 2.3:** Add `Worker.revoke_authority()` (1 hour)
  - Implement revocation logic
  - Support cascade parameter
  - Use `revoke_delegation_grant()` query
  - Dependencies: Task 1.2

- [ ] **Task 2.4:** Update `Worker.can_hire()` (30 min)
  - Check delegation expiry via `expire_delegations()`
  - Return False if delegation expired
  - Dependencies: Task 1.2

- [ ] **Task 2.5:** Add delegation constants (30 min)
  - Add to `cli/core/constants.py`:
    - `DELEGATION_PRESET_TEAM_LEAD`
    - `DELEGATION_PRESET_DIRECTOR`
    - `DELEGATION_PRESET_VP`
    - `EVENT_AUTHORITY_DELEGATED`
    - `EVENT_AUTHORITY_REVOKED`
  - Dependencies: None

### Phase 3: CLI Commands (P1) - 6 hours

- [ ] **Task 3.1:** Implement `delegate-authority` command (1.5 hours)
  - Create `cli/commands/org/delegate_authority.py`
  - Support `--level` preset parameter
  - Support `--roles`, `--max-cost`, `--budget` custom parameters
  - Validation: mutually exclusive --level vs custom
  - Error handling: not direct report, insufficient budget
  - Dependencies: Task 2.2

- [ ] **Task 3.2:** Implement `revoke-authority` command (1.5 hours)
  - Create `cli/commands/org/revoke_authority.py`
  - Support `--cascade` flag
  - Interactive confirmation when cascade=True
  - Support `--force` to skip confirmation
  - Dependencies: Task 2.3

- [ ] **Task 3.3:** Implement `promote` command (1 hour)
  - Create `cli/commands/org/promote.py`
  - Support `--to` parameter (team-lead, director, vp)
  - Wrapper around `delegate-authority` with preset
  - Dependencies: Task 3.1

- [ ] **Task 3.4:** Implement `demote` command (1 hour)
  - Create `cli/commands/org/demote.py`
  - Support `--cascade` flag
  - Wrapper around `revoke-authority`
  - Dependencies: Task 3.2

- [ ] **Task 3.5:** Implement `delegations` command (1 hour)
  - Create `cli/commands/org/delegations.py`
  - Support `--worker` filter parameter
  - Support `--tree` flag for ASCII tree output
  - Default: table output with delegator, delegate, budget, scope
  - Dependencies: Task 1.2, 2.1

- [ ] **Task 3.6:** Register commands in `__init__.py` (15 min)
  - Update `cli/commands/org/__init__.py`
  - Add imports and exports for 5 new commands
  - Dependencies: Tasks 3.1-3.5

### Phase 4: Integration (P1) - 4 hours

- [ ] **Task 4.1:** Update `org status` to show delegation (1 hour)
  - Show delegation marker in worker list (e.g., "👤 Alice (delegated)")
  - Show delegation chain in verbose mode
  - Dependencies: Task 1.2

- [ ] **Task 4.2:** Update `hire` command validation (1 hour)
  - Call `expire_delegations()` before hire
  - Check delegation expiry in `can_hire()`
  - Error message if delegation expired
  - Dependencies: Task 2.4

- [ ] **Task 4.3:** Update `fire` command auto-revocation (1 hour)
  - Call `revoke_authority()` on worker termination
  - Log auto-revocation in delegation_audit
  - Support cascade parameter
  - Dependencies: Task 2.3

- [ ] **Task 4.4:** Emit delegation events (1 hour)
  - Create event beads for `EVENT_AUTHORITY_DELEGATED`
  - Create event beads for `EVENT_AUTHORITY_REVOKED`
  - Include delegation chain in event metadata
  - Dependencies: Task 2.2, 2.3

### Phase 5: Testing (P0) - 8 hours

- [ ] **Task 5.1:** Write unit tests (4 hours)
  - Create `cli/tests/test_delegation_unit.py`
  - Write all 15 unit test cases
  - Mock database and worker instances
  - Dependencies: Tasks 1.2, 2.1, 2.2, 2.3

- [ ] **Task 5.2:** Write integration tests (3 hours)
  - Create `cli/tests/test_delegation_integration.py`
  - Write all 20 integration test cases
  - Use real database and CLI runner
  - Dependencies: Tasks 3.1-3.5

- [ ] **Task 5.3:** Update existing tests (1 hour)
  - Unskip `test_hierarchical_hiring` in `test_worker.py`
  - Update test to use new delegation commands
  - Add `test_delegation_prevents_hiring_without_authority`
  - Add `test_delegation_expires`
  - Dependencies: Tasks 2.2, 3.1

### Phase 6: Documentation (P2) - 2 hours

- [ ] **Task 6.1:** Write ADR-006-delegation.md (1 hour)
  - Context: Why delegation needed
  - Decision: Hybrid commands, preset levels, block-with-interactive
  - Consequences: Security improvements, UX tradeoffs
  - Migration path for existing orgs
  - Dependencies: All implementation tasks

- [ ] **Task 6.2:** Update README.md (30 min)
  - Add delegation examples to quickstart
  - Update command reference
  - Add delegation workflow diagram
  - Dependencies: Task 6.1

- [ ] **Task 6.3:** Add command help examples (30 min)
  - Add detailed help text to each command
  - Include examples for each preset level
  - Add warnings about cascade revocation
  - Dependencies: Tasks 3.1-3.5

---

## 5. Time Estimates by Phase

| Phase | Estimated Time | Critical Path |
|-------|---------------|---------------|
| Phase 1: Database Foundation | 4 hours | Yes (P0) |
| Phase 2: Core Logic | 6 hours | Yes (P0) |
| Phase 3: CLI Commands | 6 hours | Yes (P1) |
| Phase 4: Integration | 4 hours | No (P1) |
| Phase 5: Testing | 8 hours | Yes (P0) |
| Phase 6: Documentation | 2 hours | No (P2) |
| **Total** | **30 hours** | |

**Actual Estimated Total: 32 hours** (includes 2 hours buffer for debugging/iteration)

### Critical Path Dependencies

```
1.1 Migration → 1.2 Queries → 2.2 delegate_authority() → 5.1 Unit Tests
                                     ↓
                               3.1 delegate-authority → 5.2 Integration Tests
                                     ↓
                               6.1 ADR
```

**Minimum Time to Ship (Critical Path Only):** 20 hours

---

## 6. Risk Assessment

### 6.1 Technical Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **Migration breaks existing orgs** | Medium | High | - Extensive testing on sample orgs<br>- Rollback script<br>- Backup requirement in docs |
| **Optimistic locking doesn't prevent race** | Low | High | - Use SQLite WAL mode<br>- Add delegation_version column<br>- Test concurrent modifications |
| **Circular delegation detection has bugs** | Medium | Medium | - Write comprehensive test cases<br>- Use BFS traversal (proven algorithm)<br>- Add cycle detection to migration |
| **Cascade revocation leaves orphans** | Low | High | - Use foreign key constraints<br>- Add triggers for cascade<br>- Test with deep delegation chains |
| **Performance issues with deep chains** | Low | Low | - Index delegation_grants.delegator_id<br>- Limit chain depth (recursive query)<br>- Add query timeout |

### 6.2 UX Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **Users don't understand presets** | Medium | Low | - Add help examples<br>- Include preset descriptions in CLI<br>- Show preset expansion in confirmation |
| **Accidental cascade revocation** | Medium | High | - Interactive confirmation required<br>- Show affected workers before revoke<br>- Add --force flag for automation |
| **Confusion about delegation vs hiring** | Low | Medium | - Clear command names<br>- Separate `promote` from `hire`<br>- Update README with workflow diagram |

### 6.3 Integration Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **Break existing hire command** | Low | High | - Update hire command to check delegation<br>- Write integration test<br>- Test with existing orgs |
| **Break existing fire command** | Low | High | - Auto-revoke on fire<br>- Test cascade behavior<br>- Add rollback on fire failure |
| **Conflict with beads permissions** | Low | Medium | - Delegation is separate from beads perms<br>- Document interaction<br>- Don't auto-grant beads perms on delegate |

### 6.4 Testing Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **Unit tests miss edge cases** | Medium | Medium | - Code review test cases<br>- Add property-based tests (hypothesis)<br>- Test against safety analysis scenarios |
| **Integration tests are flaky** | Low | Low | - Use fixtures for test orgs<br>- Clean up after each test<br>- Avoid timing-dependent assertions |
| **Tests don't cover P0 vulnerabilities** | Low | High | - Map each P0 to specific test<br>- Review safety analysis document<br>- Add security-focused test suite |

### 6.5 Documentation Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **ADR doesn't capture rationale** | Low | Low | - Review safety analysis<br>- Include tradeoffs section<br>- Document rejected alternatives |
| **README examples are wrong** | Low | Medium | - Test examples in real org<br>- Copy from integration tests<br>- Add "verified" marker |
| **Command help is incomplete** | Medium | Low | - Add examples to each command<br>- Show all flag combinations<br>- Include error message reference |

---

## 7. Success Criteria

### 7.1 Functional Requirements

- [ ] All P0 vulnerabilities fixed (self-delegation, circular refs, optimistic locking, lifecycle validation)
- [ ] All 5 CLI commands implemented and working
- [ ] All 35 test cases passing
- [ ] Migration successfully upgrades existing orgs
- [ ] Rollback script successfully downgrades

### 7.2 Non-Functional Requirements

- [ ] Test coverage ≥ 90% for delegation code
- [ ] No performance regression on `qn org status`
- [ ] Command response time < 1 second for delegation operations
- [ ] Migration completes in < 5 seconds for org with 100 workers

### 7.3 Documentation Requirements

- [ ] ADR published and reviewed
- [ ] README updated with examples
- [ ] All commands have help text with examples
- [ ] Migration guide written

---

## 8. Implementation Notes

### 8.1 Database Schema Notes

**Why delegation_grants instead of updating workers table?**
- Immutable audit trail (never DELETE/UPDATE, only INSERT)
- Support multiple historical delegations per worker
- Enable cascade revocation via foreign keys
- Separate delegation state from worker lifecycle state

**Why optimistic locking?**
- SQLite doesn't support row-level locking
- WAL mode provides snapshot isolation but not serializable
- Optimistic locking prevents concurrent budget over-allocation
- Implemented via `delegation_version` column

### 8.2 Command Design Notes

**Why separate promote/demote from delegate/revoke?**
- Promote is a higher-level concept (business operation)
- Delegate is a lower-level primitive (technical operation)
- Promote can evolve to include role changes, salary updates, etc.
- Demote is explicit (safer than "revoke" which sounds technical)

**Why interactive confirmation for cascade?**
- Cascade revocation affects multiple workers (potentially org-wide)
- Accidental cascade can disable entire org hierarchy
- Interactive prompt shows affected workers before confirmation
- --force flag for automation (CI/CD, scripts)

### 8.3 Testing Notes

**Why separate unit and integration tests?**
- Unit tests are fast, run in isolation, mock database
- Integration tests are slow, use real database and CLI
- Unit tests cover business logic edge cases
- Integration tests cover end-to-end workflows

**Why property-based testing?**
- Delegation has complex invariants (no cycles, budget conserved, etc.)
- Property tests generate random delegation chains
- Hypothesis library can find edge cases humans miss
- Consider adding for Phase 5

### 8.4 Documentation Notes

**What goes in ADR vs README?**
- ADR: Architecture decisions, tradeoffs, alternatives considered
- README: User-facing examples, quickstart, command reference
- ADR is for developers, README is for users

**Why include rejected alternatives?**
- Document why we didn't use other approaches
- Prevent future "why didn't we just..." questions
- Capture institutional knowledge

---

## 9. Post-Implementation Checklist

- [ ] Run full test suite (pytest cli/tests/)
- [ ] Test migration on 3 different sample orgs
- [ ] Verify no performance regression (profile qn org status)
- [ ] Update CHANGELOG.md with new features
- [ ] Create demo video/GIF for README
- [ ] Update project roadmap (mark delegation as complete)
- [ ] Close related beads (delegation feature request)

---

## 10. Future Enhancements (Not in Scope)

These are explicitly OUT OF SCOPE for this implementation but documented for future consideration:

1. **Budget pooling** - Multiple delegators contribute to shared budget
2. **Conditional delegation** - Delegate only for specific projects/teams
3. **Delegation templates** - Save custom presets beyond team-lead/director/vp
4. **Delegation analytics** - Dashboard showing delegation utilization
5. **Automatic promotion** - Auto-delegate based on tenure/performance
6. **Delegation approvals** - Require CEO approval for high-level delegations
7. **Budget carryover** - Unused budget rolls over to next period

---

## Appendix A: Example Usage

### A.1 Promote a worker to team lead

```bash
# Option 1: Use promote command (recommended)
qn org promote alice --to=team-lead

# Option 2: Use delegate-authority with preset
qn org delegate-authority alice --level=team-lead --budget=5000

# Option 3: Custom delegation
qn org delegate-authority alice \
  --roles=engineer,designer,qa \
  --max-cost=60 \
  --budget=5000
```

### A.2 Revoke delegation

```bash
# Revoke only Alice's delegation
qn org revoke-authority alice

# Revoke Alice and all her sub-delegations (cascade)
qn org revoke-authority alice --cascade

# Revoke without confirmation prompt (automation)
qn org revoke-authority alice --cascade --force
```

### A.3 View delegations

```bash
# List all delegations (table view)
qn org delegations

# Show delegations for specific worker
qn org delegations --worker=alice

# Show delegation tree (hierarchical view)
qn org delegations --tree
```

### A.4 Expected output

```
$ qn org delegations --tree

Delegation Tree:
CEO (Alice) [budget: $100K, roles: *]
├── Director (Bob) [budget: $20K, roles: engineer,manager,team-lead]
│   ├── Team Lead (Carol) [budget: $5K, roles: engineer,designer]
│   └── Team Lead (Dave) [budget: $5K, roles: engineer,qa]
└── Director (Eve) [budget: $20K, roles: engineer,manager,team-lead]
    └── Team Lead (Frank) [budget: $5K, roles: engineer]

Total: 5 active delegations
Total budget delegated: $50K
```

---

## Appendix B: Migration Script Preview

```sql
-- Migration v16 → v17: Add delegation tracking
-- Date: 2026-01-28

BEGIN TRANSACTION;

-- Create delegation_grants table
CREATE TABLE delegation_grants (
    id TEXT PRIMARY KEY,
    delegator_id TEXT NOT NULL,
    delegate_id TEXT NOT NULL,
    scope TEXT NOT NULL,
    budget_amount INTEGER NOT NULL,
    granted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME,
    revoked_at DATETIME,
    revoked_by TEXT,
    revoke_reason TEXT,
    granted_by_cli_user TEXT,
    metadata TEXT,
    FOREIGN KEY (delegator_id) REFERENCES workers(id) ON DELETE CASCADE,
    FOREIGN KEY (delegate_id) REFERENCES workers(id) ON DELETE CASCADE,
    CHECK (delegator_id != delegate_id),
    CHECK (budget_amount >= 0),
    UNIQUE(delegate_id) WHERE revoked_at IS NULL
);

CREATE INDEX idx_delegation_grants_delegator ON delegation_grants(delegator_id);
CREATE INDEX idx_delegation_grants_delegate ON delegation_grants(delegate_id);
CREATE INDEX idx_delegation_grants_active ON delegation_grants(revoked_at) WHERE revoked_at IS NULL;

-- Create delegation_audit table
CREATE TABLE delegation_audit (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL CHECK(event_type IN (
        'granted', 'revoked', 'expired', 'cascade_revoked', 'modified', 'terminated_revoked'
    )),
    delegator_id TEXT NOT NULL,
    delegate_id TEXT NOT NULL,
    delegation_grant_id TEXT,
    scope_before TEXT,
    scope_after TEXT,
    budget_before INTEGER,
    budget_after INTEGER,
    performed_by TEXT NOT NULL,
    performed_by_cli_user TEXT,
    reason TEXT,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ip_address TEXT,
    session_id TEXT
);

CREATE INDEX idx_delegation_audit_delegate ON delegation_audit(delegate_id);
CREATE INDEX idx_delegation_audit_timestamp ON delegation_audit(timestamp DESC);

-- Trigger: Auto-audit on grant creation
CREATE TRIGGER trg_delegation_grant_audit
AFTER INSERT ON delegation_grants
FOR EACH ROW
BEGIN
    INSERT INTO delegation_audit (
        id, event_type, delegator_id, delegate_id, delegation_grant_id,
        scope_after, budget_after, performed_by, timestamp
    ) VALUES (
        lower(hex(randomblob(16))),
        'granted',
        NEW.delegator_id,
        NEW.delegate_id,
        NEW.id,
        NEW.scope,
        NEW.budget_amount,
        NEW.delegator_id,
        NEW.granted_at
    );
END;

-- Update schema version
UPDATE schema_version SET version = 17, updated_at = CURRENT_TIMESTAMP;

COMMIT;
```

---

**End of Implementation Scope Document**
