# QuinnAI - Project Definition

## What Is This?

RollerCoaster Tycoon, but for organizations.

You design an org. You hire AI workers. You set goals. You watch it run. You intervene only when it's going off the rails.

The org operates autonomously. Humans are the board - gutterguards, not micromanagers.

## The Physics (What Code Defines)

Code defines dynamics. Config defines behavior. Like gravity - it exists, but you can build a ball or an airplane.

### Sessions
- Session = Worker's brain (1:1, unbreakable)
- Session ON → Worker awake
- Session OFF → Worker asleep

### Workers
- Every agent is a worker (CEO, manager, junior - same base unit)
- Workers differ by: Role, Team, Hierarchy, Authority
- Authority = Scope × Domain (configurable per org)

### Work
Four independent dimensions:
- **Ask**: Who requested, what, why? (the trigger - a related object)
- **Flow**: Where in lifecycle? (configurable states + transitions)
- **Ownership**: Who's responsible? (single owner + deadline)
- **OKR**: What strategic goal does it serve? (alignment to cascading objectives)

### Communication
- One protocol for everything (no special cases)
- Message types: work-handoff, work-request, information-request, status-report, etc.
- Extensible over time

### OKRs
- Objectives cascade: Board → CEO → Directors → Managers → Workers
- Key Results: singular, calculable, not subjective
- Every work item links to lowest-level OKR

## What Config Defines

Everything behavioral:
- Org structure (teams, hierarchy, authority levels)
- Work flow states and transitions
- Communication rules
- Review requirements
- Escalation paths

## Success Criteria

The org runs. Workers wake, work, communicate, complete. Goals cascade. Board intervenes rarely.
