# Board Interface Design

## Overview

The Board Interface is the human oversight layer for QuinnAI organizations. Following the core principle that "Board = Gutterguards," the board intervenes only when the organization is off-track. The interface is designed to provide visibility without enabling micromanagement.

**Core Philosophy**: The ball keeps rolling. The board only bumps it back when it's heading for the gutter.

## Design Questions Answered

### 1. CLI-only MVP? Web Dashboard Later?

**Decision: CLI-first for MVP, web dashboard as future enhancement.**

**Rationale:**
- CLI aligns with current architecture (`qn org` / `qn wrkr` pattern)
- Board members can use existing terminal tools
- Enables scripting and automation of oversight tasks
- Web dashboard adds complexity without core value in MVP
- CLI provides all necessary views and actions

**Future Web Dashboard:**
- Real-time org-chart visualization
- Interactive budget graphs
- OKR progress dashboards
- Activity timeline views
- Will consume same underlying data as CLI

### 2. What Does Board Need to See?

The board needs visibility into four key areas, reflecting the "intervene only when off-track" philosophy:

| Area | What Board Sees | Why It Matters |
|------|-----------------|----------------|
| **Org-Chart** | Who's hired, hierarchy, team structure | Understand org shape, spot imbalances |
| **OKRs** | Objectives, key results, progress % | Track strategic alignment |
| **Budget** | Spend vs allocation, burn rate, projections | Financial health check |
| **Activity** | Recent decisions, communications, anomalies | Detect concerning patterns |

### 3. What Actions Can Board Take?

Actions follow the intervention level model:

| Level | Action | Effect |
|-------|--------|--------|
| **Soft** | Set/adjust OKR | Add objectives, modify key results |
| **Soft** | Add guidance note | Non-binding direction to CEO |
| **Medium** | Direct feedback | Formal feedback requiring acknowledgment |
| **Medium** | Adjust budget | Increase/decrease pool allocation |
| **Hard** | Fire CEO | Replace CEO (nuclear option) |
| **Hard** | Pause org | Stop all worker sessions |

### 4. How Does Board Monitor Without Micromanaging?

**Design Principles for Non-Invasive Oversight:**

1. **Summary-First Views**: Show aggregates and trends, not individual tasks
2. **Drill-Down Optional**: Details available but not default
3. **Anomaly Highlighting**: Surface outliers automatically
4. **Passive Observation**: `qn board status` is read-only by default
5. **Rate-Limited Actions**: Some actions require confirmation or cooldown

**Anti-Micromanagement Patterns:**
- Cannot assign individual beads to workers
- Cannot modify worker-level tasks directly
- Cannot send messages to non-CEO workers
- Budget visible but not modifiable at worker level

### 5. What Alerts/Notifications Does Board Get?

**Alert Categories:**

| Priority | Category | Trigger | Example |
|----------|----------|---------|---------|
| **P0** | Budget | >90% spend, overage | "Org at 95% of monthly budget" |
| **P0** | Org Health | CEO terminated/stuck | "CEO session inactive 2+ hours" |
| **P1** | OKR | Key result deadline missed | "Q1 revenue target overdue" |
| **P1** | Growth | Rapid hiring, unusual pattern | "3 workers hired in 1 hour" |
| **P2** | Performance | Worker metrics below threshold | "Team velocity down 40% this week" |
| **P2** | Communication | Escalation from CEO | "CEO escalated issue: budget request" |

---

## CLI Command Specification

### Command Structure

```
qn board <command> [options]
```

The `board` namespace sits alongside `org` and `wrkr`:
- `qn org` = system manages org lifecycle
- `qn wrkr` = workers run from sessions
- `qn board` = humans oversee the org

### View Commands (Read-Only)

#### `qn board status`

Show high-level org health dashboard.

```bash
$ qn board status

QuinnAI Organization: my-startup
Status: running (3h 24m uptime)
Last Board Review: 2026-01-20 14:30

Health Indicators:
  Budget:     [####----] 48% spent (14 days remaining)
  OKRs:       [######--] 67% on track (2/3 objectives)
  Workers:    8 active, 2 idle, 0 stuck
  Activity:   Normal (no alerts)

Quick Stats:
  CEO:        alice (active, last action: 12m ago)
  Teams:      3 (Engineering, Product, Marketing)
  Open Work:  47 beads across all teams

Alerts (1):
  [P2] Engineering velocity down 15% vs last week

Run 'qn board alerts' for details.
```

**Options:**
- `--json`: Output as JSON for scripting
- `--watch`: Refresh every N seconds (default: 30)

#### `qn board org-chart`

Display current organizational structure.

```bash
$ qn board org-chart

my-startup Organization Chart (as of 2026-01-21 09:15)

Board (You)
    |
    +-- CEO: alice (active)
        Budget: 500,000 cr | Spent: 125,000 cr | Delegated: 300,000 cr
        |
        +-- Engineering (dir-eng-001: bob)
        |   Budget: 200,000 cr | Spent: 85,000 cr | Workers: 4
        |   |
        |   +-- Backend Team (mgr-001: charlie)
        |   |   +-- dev-001: sarah (active) - 45,230 cr spent
        |   |   +-- dev-002: mike (idle)    - 12,100 cr spent
        |   |
        |   +-- Frontend Team (mgr-002: diana)
        |       +-- dev-003: james (active) - 18,500 cr spent
        |
        +-- Product (dir-prod-001: eve)
        |   Budget: 100,000 cr | Spent: 28,000 cr | Workers: 2
        |   |
        |   +-- pm-001: frank (active) - 15,000 cr spent
        |   +-- design-001: grace (idle) - 13,000 cr spent
        |
        +-- Marketing (dir-mkt-001: henry)
            Budget: 75,000 cr | Spent: 12,000 cr | Workers: 1
            |
            +-- mkt-001: iris (active) - 12,000 cr spent

Total Workers: 11 | Total Budget: 500,000 cr | Total Spent: 218,830 cr (44%)
```

**Options:**
- `--depth N`: Limit tree depth (default: unlimited)
- `--team TEAM`: Show only specific team subtree
- `--budget`: Show budget details (default: on)
- `--status`: Show worker status (default: on)
- `--json`: Output as JSON

#### `qn board okrs`

Display OKR hierarchy and progress.

```bash
$ qn board okrs

Q1 2026 OKRs - my-startup

[OKR-001] Establish market presence
  Status: on_track | Due: 2026-03-31 | Owner: alice (CEO)
  |
  +-- [KR-001] Launch MVP to 100 users
  |   Progress: [########--] 78% (78/100 users)
  |   Owner: eve (Product)
  |
  +-- [KR-002] Achieve $10K MRR
  |   Progress: [####------] 42% ($4,200 MRR)
  |   Owner: henry (Marketing)
  |
  +-- [KR-003] Ship core platform features
      Progress: [######----] 63% (19/30 features)
      Owner: bob (Engineering)
      |
      +-- [KR-003-A] Complete authentication system
      |   Progress: [##########] 100% (done)
      |   Owner: charlie (Backend)
      |
      +-- [KR-003-B] Build dashboard UI
          Progress: [####------] 40% (in progress)
          Owner: diana (Frontend)

[OKR-002] Build engineering excellence
  Status: at_risk | Due: 2026-03-31 | Owner: alice (CEO)
  |
  +-- [KR-004] 80% test coverage
  |   Progress: [###-------] 32% (currently 32%)
  |   Owner: bob (Engineering)
  |   [!] Behind schedule - needs attention
  |
  +-- [KR-005] <1hr deployment time
      Progress: [########--] 85% (currently 45min)
      Owner: charlie (Backend)

Summary: 2 Objectives | 5 Key Results | 67% on track | 1 at risk
```

**Options:**
- `--objective OKR-ID`: Show specific objective tree
- `--owner WORKER`: Filter by owner
- `--status STATUS`: Filter by status (on_track, at_risk, behind, completed)
- `--json`: Output as JSON

#### `qn board budget`

Display budget overview and spend tracking.

```bash
$ qn board budget

Budget Overview - my-startup
Period: 2026-01-01 to 2026-01-31 (10 days remaining)

Pool Status:
  Total Credits:     1,000,000 cr
  Allocated to CEO:    500,000 cr (50%)
  Unallocated:         500,000 cr (50%)
  Pool Available:      500,000 cr

Org Spend Summary:
  Total Spent:         218,830 cr (44% of allocated)
  Burn Rate:           10,420 cr/day
  Projected Month End: 323,030 cr (65% of allocated)
  Status:              On track

Spend by Team:
  Engineering:   85,000 cr (39% of spend) [####------]
  Product:       28,000 cr (13% of spend) [#---------]
  Marketing:     12,000 cr ( 5% of spend) [-----------]
  CEO Direct:    93,830 cr (43% of spend) [####------]

Top Spenders (this period):
  1. alice (CEO):           93,830 cr
  2. sarah (dev-001):       45,230 cr
  3. james (dev-003):       18,500 cr
  4. frank (pm-001):        15,000 cr
  5. grace (design-001):    13,000 cr

Alerts:
  None

Run 'qn board budget --transactions' for detailed ledger.
```

**Options:**
- `--worker WORKER`: Show specific worker budget
- `--team TEAM`: Show specific team budget
- `--tree`: Hierarchical budget cascade view
- `--transactions`: Show recent transactions
- `--since DATE`: Filter transactions by date
- `--json`: Output as JSON

#### `qn board activity`

Display recent organizational activity.

```bash
$ qn board activity

Recent Activity - my-startup (last 24 hours)

Time        Actor     Action                              Details
─────────────────────────────────────────────────────────────────────────
09:15:23    alice     hired                               New worker: iris (mkt-001)
09:14:02    alice     delegated_budget                    75,000 cr to Marketing
08:45:11    bob       completed_bead                      auth-system-v2 (KR-003-A)
08:30:00    eve       updated_okr                         KR-001 progress: 78%
07:22:33    sarah     started_bead                        api-refactor-001
06:15:00    [system]  session_idle                        mike (dev-002) idle 2h
05:00:00    [system]  daily_budget_snapshot               218,830 cr spent
─────────────────────────────────────────────────────────────────────────

Activity Summary:
  Hiring:        1 new worker
  Beads:         3 started, 2 completed, 0 blocked
  Budget:        1 delegation
  Communications: 12 messages (8 work-related, 4 status updates)

Patterns Detected:
  [INFO] Normal activity levels for this time of day
```

**Options:**
- `--since DURATION`: Filter by time (e.g., "2h", "1d", "1w")
- `--actor WORKER`: Filter by actor
- `--type TYPE`: Filter by action type (hire, fire, budget, bead, message)
- `--limit N`: Limit results (default: 50)
- `--json`: Output as JSON

#### `qn board alerts`

Display and manage board alerts.

```bash
$ qn board alerts

Active Alerts - my-startup

[P2] #alert-001 - Engineering velocity down 15% vs last week
     Detected: 2026-01-21 06:00
     Category: performance
     Details:  Team completed 12 beads vs 14 last week
     Suggested: Review with CEO, check for blockers

No P0 or P1 alerts.

Alert History (last 7 days):
  2026-01-20  [P1] Budget warning: 80% threshold (resolved)
  2026-01-18  [P2] Worker idle: grace (design-001) 4h (resolved)
  2026-01-15  [P0] CEO session crash (resolved, auto-restart)

Run 'qn board alerts ack <alert-id>' to acknowledge.
```

**Options:**
- `--priority P0|P1|P2`: Filter by priority
- `--unresolved`: Show only unresolved alerts
- `--history`: Include resolved alerts
- `--json`: Output as JSON

#### `qn board observe [worker]`

Observe a worker's session (read-only stream).

```bash
$ qn board observe alice

Observing: alice (CEO) - Session qn-ceo-001
Attached read-only. Worker cannot see you.
Press Ctrl+C to stop.

─────────────────────────────────────────────────────────────────────────
[alice's session output streams here...]
─────────────────────────────────────────────────────────────────────────
```

**Options:**
- `--stream`: Stream output without attaching (default if non-interactive)
- `--poll-interval N`: Seconds between polls when streaming

### Action Commands (Write)

#### `qn board set-okr`

Create or update an objective or key result.

```bash
# Create new objective
$ qn board set-okr --objective "Expand to enterprise market" \
    --due 2026-06-30 \
    --owner alice

Created OKR-003: "Expand to enterprise market"
  Due: 2026-06-30
  Owner: alice (CEO)
  Status: draft

# Add key result to existing objective
$ qn board set-okr --parent OKR-003 \
    --key-result "Sign 5 enterprise customers" \
    --metric "enterprise_customers" \
    --target 5 \
    --owner henry

Created KR-006: "Sign 5 enterprise customers"
  Parent: OKR-003
  Target: 5 enterprise_customers
  Owner: henry (Marketing)

# Update existing OKR
$ qn board set-okr OKR-001 --status on_track --notes "Q1 looking good"

Updated OKR-001: "Establish market presence"
  Status: on_track
  Notes: "Q1 looking good"
```

**Options:**
- `--objective TEXT`: Objective description (for creating)
- `--key-result TEXT`: Key result description (for creating)
- `--parent OKR-ID`: Parent objective for key results
- `--due DATE`: Due date
- `--owner WORKER`: Owner worker ID
- `--metric NAME`: Metric name for key result
- `--target NUMBER`: Target value for key result
- `--status STATUS`: Update status
- `--notes TEXT`: Add notes

#### `qn board feedback`

Send formal feedback to CEO (requires acknowledgment).

```bash
$ qn board feedback "Rebalance engineering/sales ratio. \
    Engineering is 60% of spend but sales pipeline is thin. \
    Consider hiring a sales lead before next sprint."

Feedback sent to alice (CEO)

Feedback ID: fb-001
Priority: medium
Content: "Rebalance engineering/sales ratio..."
Sent: 2026-01-21 10:30
Status: pending_ack

CEO will see this on next session resume.
Acknowledgment required within 24 hours.

Track with: qn board feedback --status fb-001
```

**Options:**
- `--priority soft|medium|hard`: Feedback urgency (default: medium)
- `--deadline DURATION`: Acknowledgment deadline (default: 24h)
- `--status FB-ID`: Check feedback status
- `--list`: List all feedback

#### `qn board budget-adjust`

Adjust the organization budget pool.

```bash
# Add credits to pool
$ qn board budget-adjust --add 100000 --reason "Q1 expansion budget"

Budget pool adjusted:
  Previous: 1,000,000 cr
  Added:    +100,000 cr
  New:      1,100,000 cr
  Reason:   "Q1 expansion budget"

# Reduce pool (with warning if already allocated)
$ qn board budget-adjust --remove 200000 --reason "Cost reduction"

Warning: Removing 200,000 cr would affect CEO allocation.
  Currently allocated to CEO: 500,000 cr
  After removal, pool total: 800,000 cr
  This may require CEO to reduce delegations.

Proceed? [y/N] y

Budget pool adjusted:
  Previous: 1,000,000 cr
  Removed:  -200,000 cr
  New:      800,000 cr
  Reason:   "Cost reduction"
```

**Options:**
- `--add AMOUNT`: Add credits to pool
- `--remove AMOUNT`: Remove credits from pool
- `--reason TEXT`: Required reason for audit trail
- `--force`: Skip confirmation prompts

#### `qn board fire`

Terminate the CEO (nuclear option).

```bash
$ qn board fire alice --reason "Strategic misalignment"

WARNING: Firing the CEO is a major action that will:
  1. Terminate alice's session immediately
  2. Freeze all active work owned by alice
  3. Require appointing a new CEO
  4. Create organization disruption

Current org impact:
  - 10 direct/indirect reports will lose manager
  - 47 open beads will need reassignment
  - 375,000 cr delegated budget will return to pool

This action cannot be undone.

Type 'FIRE ALICE' to confirm: FIRE ALICE

Terminating CEO...
  Session qn-ceo-001 terminated
  Worker alice status: offboarding
  Budget returned to pool: 375,000 cr
  Beads frozen: 12 direct, 35 delegated

CEO terminated.

Next steps:
  1. Run 'qn board hire-ceo' to appoint new CEO
  2. Review frozen beads with 'qn org beads --frozen'
  3. New CEO will inherit org on appointment
```

**Options:**
- `--reason TEXT`: Required termination reason
- `--force`: Skip interactive confirmation (for scripts)

#### `qn board hire-ceo`

Appoint a new CEO (only when no CEO exists).

```bash
$ qn board hire-ceo --name "Bob Chen" \
    --cost 100 \
    --skills strategy:90,management:85,reasoning:80

Creating new CEO...
  Worker ID: ceo-002
  Name: Bob Chen
  Cost: 100 (premium models)
  Skills: strategy(90), management(85), reasoning(80)

Initializing CEO session...
  Session: qn-ceo-002
  Status: starting

CEO appointed successfully.
  Run 'qn board observe bob' to watch onboarding.
  CEO will receive board OKRs and begin planning.
```

**Options:**
- `--name TEXT`: CEO name
- `--cost NUMBER`: Cost level (0-100)
- `--skills SPEC`: Skill specification (skill:level,skill:level)
- `--from-template TEMPLATE`: Use worker template

#### `qn board pause`

Pause the organization (stop all worker sessions).

```bash
$ qn board pause --reason "Emergency maintenance"

Pausing organization...

Workers to pause: 11
  - alice (CEO): active -> pausing
  - bob (dir-eng-001): active -> pausing
  - charlie (mgr-001): active -> pausing
  ... [8 more]

Pause complete.
  Organization status: paused
  All sessions suspended
  In-flight work preserved
  Resume with: qn board resume

Reason logged: "Emergency maintenance"
```

**Options:**
- `--reason TEXT`: Required pause reason
- `--workers WORKERS`: Pause specific workers only (comma-separated)
- `--team TEAM`: Pause specific team only

#### `qn board resume`

Resume a paused organization.

```bash
$ qn board resume

Resuming organization...

Workers to resume: 11
  - alice (CEO): paused -> starting
  - bob (dir-eng-001): paused -> starting
  - charlie (mgr-001): paused -> starting
  ... [8 more]

Resume complete.
  Organization status: running
  All sessions restarted
  Workers will pick up where they left off

Paused duration: 2h 15m
```

**Options:**
- `--workers WORKERS`: Resume specific workers only
- `--team TEAM`: Resume specific team only

---

## Alert/Notification System Design

### Alert Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Alert Sources                                   │
├──────────────┬────────────────┬─────────────────┬────────────────────┤
│    Budget    │   OKR Tracker  │  Session Monitor │  Activity Analyzer │
│   Monitor    │                │                  │                    │
└──────┬───────┴───────┬────────┴────────┬─────────┴──────────┬─────────┘
       │               │                 │                    │
       └───────────────┴────────┬────────┴────────────────────┘
                                │
                                ▼
                   ┌────────────────────────┐
                   │    Alert Aggregator    │
                   │  - Deduplication       │
                   │  - Priority assignment │
                   │  - Correlation         │
                   └───────────┬────────────┘
                               │
                               ▼
                   ┌────────────────────────┐
                   │    Alert Storage       │
                   │  (alerts table in DB)  │
                   └───────────┬────────────┘
                               │
           ┌───────────────────┼───────────────────┐
           │                   │                   │
           ▼                   ▼                   ▼
    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
    │  CLI Alerts │    │  Webhooks   │    │   Email     │
    │  (polling)  │    │  (future)   │    │  (future)   │
    └─────────────┘    └─────────────┘    └─────────────┘
```

### Alert Schema

```sql
CREATE TABLE IF NOT EXISTS board_alerts (
    id TEXT PRIMARY KEY,
    priority TEXT NOT NULL CHECK(priority IN ('P0', 'P1', 'P2')),
    category TEXT NOT NULL CHECK(category IN (
        'budget', 'okr', 'session', 'growth', 'performance', 'escalation'
    )),
    title TEXT NOT NULL,
    details TEXT,  -- JSON with alert-specific data
    detected_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at DATETIME,
    acknowledged_at DATETIME,
    acknowledged_by TEXT,  -- board member who acked
    resolution TEXT,  -- how it was resolved
    source TEXT NOT NULL,  -- which monitor generated it
    related_entity_type TEXT,  -- 'worker', 'team', 'okr', 'budget'
    related_entity_id TEXT,
    metadata TEXT  -- JSON for extensibility
);

CREATE INDEX idx_alerts_priority ON board_alerts(priority);
CREATE INDEX idx_alerts_unresolved ON board_alerts(resolved_at) WHERE resolved_at IS NULL;
CREATE INDEX idx_alerts_detected ON board_alerts(detected_at);
```

### Alert Definitions

```yaml
# Alert configuration (in org config.yaml)
alerts:
  # Budget Alerts
  budget_warning:
    priority: P1
    trigger: spend_percentage >= 80
    message: "Budget at {percentage}% - {remaining} credits remaining"

  budget_critical:
    priority: P0
    trigger: spend_percentage >= 95
    message: "Budget nearly exhausted at {percentage}%"

  budget_overage:
    priority: P0
    trigger: spend_percentage > 100
    message: "Budget exceeded by {overage} credits"

  # Session Alerts
  ceo_inactive:
    priority: P0
    trigger: ceo_idle_duration > 2h
    message: "CEO session inactive for {duration}"

  worker_stuck:
    priority: P1
    trigger: worker_on_same_bead > 4h
    message: "Worker {name} stuck on bead {bead_id} for {duration}"

  session_crash:
    priority: P0
    trigger: session_unexpected_exit
    message: "Session {session_id} crashed unexpectedly"

  # OKR Alerts
  okr_deadline_missed:
    priority: P1
    trigger: okr_due_date < now AND okr_status != 'completed'
    message: "OKR {okr_id} deadline missed: {title}"

  okr_at_risk:
    priority: P2
    trigger: okr_progress_rate < expected_rate * 0.7
    message: "OKR {okr_id} at risk - progress below expected"

  # Growth Alerts
  rapid_hiring:
    priority: P1
    trigger: hires_in_period > 3 AND period < 2h
    message: "{count} workers hired in {duration} - review hiring pattern"

  # Performance Alerts
  velocity_drop:
    priority: P2
    trigger: team_velocity < previous_period * 0.8
    message: "{team} velocity down {percentage}% vs last period"

  # Escalation Alerts
  ceo_escalation:
    priority: P1
    trigger: ceo_escalation_message
    message: "CEO escalated: {subject}"
```

### Alert Monitor Implementation

```python
# Pseudocode for alert monitoring

class AlertMonitor:
    """Monitors org health and generates alerts."""

    def __init__(self, db: Database, config: AlertConfig):
        self.db = db
        self.config = config
        self.monitors = [
            BudgetMonitor(db, config),
            SessionMonitor(db, config),
            OKRMonitor(db, config),
            ActivityMonitor(db, config),
        ]

    def check_all(self) -> List[Alert]:
        """Run all monitors and return new alerts."""
        alerts = []
        for monitor in self.monitors:
            new_alerts = monitor.check()
            alerts.extend(new_alerts)

        # Deduplicate and correlate
        alerts = self._deduplicate(alerts)
        alerts = self._correlate(alerts)

        # Store new alerts
        for alert in alerts:
            self._store_alert(alert)

        return alerts

    def run_continuous(self, interval_seconds: int = 60):
        """Run monitors continuously."""
        while True:
            self.check_all()
            time.sleep(interval_seconds)


class BudgetMonitor:
    """Monitor budget health."""

    def check(self) -> List[Alert]:
        alerts = []

        # Check org-level budget
        pool = self._get_budget_pool()
        spend_pct = (pool.spent / pool.total) * 100

        if spend_pct >= 95:
            alerts.append(Alert(
                priority='P0',
                category='budget',
                title=f'Budget nearly exhausted at {spend_pct:.1f}%',
                details={'percentage': spend_pct, 'remaining': pool.total - pool.spent}
            ))
        elif spend_pct >= 80:
            alerts.append(Alert(
                priority='P1',
                category='budget',
                title=f'Budget at {spend_pct:.1f}%',
                details={'percentage': spend_pct, 'remaining': pool.total - pool.spent}
            ))

        return alerts
```

### Alert Delivery (MVP)

For MVP, alerts are delivered through CLI polling:

```bash
# In .bashrc or shell profile, poll alerts periodically
alias qn-alerts='qn board alerts --unresolved'

# Or use watch for continuous monitoring
watch -n 60 'qn board alerts --unresolved --priority P0,P1'
```

**Future Delivery Channels:**
- Webhooks (Slack, Discord, custom)
- Email notifications
- Desktop notifications (for local daemon)
- SMS for P0 alerts

---

## Future Web Dashboard Considerations

The web dashboard will provide visual representations of the same data CLI exposes:

### Dashboard Views

1. **Overview Dashboard**
   - Health indicators as gauges/meters
   - Real-time worker activity graph
   - Budget burn rate chart
   - Alert ticker

2. **Org-Chart View**
   - Interactive tree visualization
   - Click to expand/collapse teams
   - Worker status indicators (color-coded)
   - Budget overlay option

3. **OKR Dashboard**
   - Progress bars for each key result
   - Gantt-style timeline view
   - Dependency graph between OKRs
   - Historical progress trends

4. **Budget Dashboard**
   - Spend over time chart
   - Burn rate projections
   - Team-by-team comparison
   - Individual transaction drill-down

5. **Activity Feed**
   - Real-time activity stream
   - Filterable by actor, type, team
   - Expandable details
   - Direct links to related entities

### API Requirements for Dashboard

```
GET /api/board/status          -> StatusResponse
GET /api/board/org-chart       -> OrgChartResponse
GET /api/board/okrs            -> OKRTreeResponse
GET /api/board/budget          -> BudgetResponse
GET /api/board/activity        -> ActivityStreamResponse
GET /api/board/alerts          -> AlertsResponse

POST /api/board/okrs           -> Create OKR
PUT /api/board/okrs/{id}       -> Update OKR
POST /api/board/feedback       -> Send feedback
POST /api/board/budget/adjust  -> Adjust budget
POST /api/board/pause          -> Pause org
POST /api/board/resume         -> Resume org
DELETE /api/board/ceo          -> Fire CEO
POST /api/board/ceo            -> Hire CEO
```

---

## Database Schema Additions

```sql
-- ===================
-- BOARD TABLES
-- ===================

-- Board feedback to CEO
CREATE TABLE IF NOT EXISTS board_feedback (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    priority TEXT NOT NULL CHECK(priority IN ('soft', 'medium', 'hard')),
    sent_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ack_deadline DATETIME NOT NULL,
    acknowledged_at DATETIME,
    acknowledged_by TEXT,
    ceo_response TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN (
        'pending', 'acknowledged', 'responded', 'escalated', 'expired'
    )),
    FOREIGN KEY (acknowledged_by) REFERENCES workers(id)
);

CREATE INDEX idx_board_feedback_status ON board_feedback(status);
CREATE INDEX idx_board_feedback_deadline ON board_feedback(ack_deadline);

-- Board action audit log
CREATE TABLE IF NOT EXISTS board_actions (
    id TEXT PRIMARY KEY,
    action TEXT NOT NULL CHECK(action IN (
        'set_okr', 'update_okr', 'feedback', 'budget_adjust',
        'fire_ceo', 'hire_ceo', 'pause', 'resume', 'ack_alert'
    )),
    details TEXT NOT NULL,  -- JSON
    performed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    performed_by TEXT,  -- Optional board member identifier
    result TEXT NOT NULL CHECK(result IN ('success', 'failed', 'cancelled'))
);

CREATE INDEX idx_board_actions_action ON board_actions(action);
CREATE INDEX idx_board_actions_performed ON board_actions(performed_at);
```

---

## Integration with Existing Systems

### Budget Integration

The board commands integrate with the budget tracking system:
- `qn board budget` reads from `budget_pools`, `budget_allocations`, `budget_transactions`
- `qn board budget-adjust` modifies `budget_pools`
- Budget alerts trigger from `budget_balances`

### OKR Integration

OKRs are stored as beads with type `okr`:
- `qn board okrs` queries beads with `type='okr'` and `type='key_result'`
- `qn board set-okr` creates/updates these beads
- OKR hierarchy uses `spawned-from` and `serves` dependencies

### Worker Integration

The board observes workers through existing infrastructure:
- `qn board observe` uses same tmux integration as `qn org observe`
- `qn board fire` triggers worker lifecycle transition
- `qn board hire-ceo` uses worker creation flow

### Permission Model

Board has implicit admin permissions on all beads (role-based grant):
```sql
INSERT INTO permissions (id, bead_id, grantee_type, grantee_id, level, granted_by)
SELECT
    'board-' || id,
    id,
    'role',
    'board',
    5,  -- ADMIN
    'system'
FROM beads;
```

---

## Implementation Order

1. **Phase 1: View Commands**
   - `qn board status` (health dashboard)
   - `qn board org-chart` (hierarchy view)
   - `qn board okrs` (OKR view)
   - `qn board budget` (budget view)

2. **Phase 2: Alert System**
   - Alert schema and storage
   - Budget monitor
   - Session monitor
   - `qn board alerts` command

3. **Phase 3: Soft Actions**
   - `qn board set-okr`
   - `qn board feedback`
   - `qn board budget-adjust`

4. **Phase 4: Hard Actions**
   - `qn board pause/resume`
   - `qn board fire`
   - `qn board hire-ceo`

5. **Phase 5: Activity & Observability**
   - `qn board activity`
   - `qn board observe`
   - OKR/Performance monitors

6. **Phase 6: Web Dashboard**
   - API endpoints
   - Dashboard UI
   - Real-time updates

---

## Summary

The Board Interface provides human oversight for QuinnAI organizations through:

1. **Views**: Status, org-chart, OKRs, budget, activity, alerts
2. **Actions**: Set OKRs, send feedback, adjust budget, pause/resume, fire/hire CEO
3. **Alerts**: P0-P2 priority alerts for budget, session, OKR, and performance issues
4. **Philosophy**: Visibility without micromanagement, intervention only when off-track

The CLI-first approach enables immediate implementation while preserving the path to a web dashboard. All commands follow the existing QuinnAI patterns and integrate with budget tracking, permission enforcement, and worker lifecycle systems.
