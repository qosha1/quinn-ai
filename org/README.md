# QuinnAI Organization

This is a **QuinnAI organization** - an AI-powered organization management system.

## Organization Structure

- **CEO:** Quinn (CEO)
- **Status:** Initialized (not yet started)
- **Database:** `live/quinn.db`

## Quick Start

### Start the Organization

```bash
qn --org-path . org start
```

This will:
1. Start the CEO worker session
2. Activate the organization
3. Begin work on OKRs

### Monitor Progress

```bash
# Check org status
qn --org-path . org status

# View OKRs
cd /path/to/org && bd list --label=okr

# See ready work
bd ready

# Watch the board
qn-board  # (if terminal-app is installed)
```

## Current OKRs

**Q1 2026: Beads Dashboard v1.0 - Production Ready**
- Testing Infrastructure Sprint (test coverage > 90%)
- Architecture & Performance Sprint (sub-100ms API responses)
- UI/UX Improvements Sprint (WCAG 2.1 AA compliance)

View details:
```bash
bd list --label=okr
bd show quinnai-3li  # Main OKR
```

## Worker Resources

All workers have access to shared resources:

- **Quickstart Guide:** `storage/shared/company/QUICKSTART.md`
- **OKR Guide:** `storage/shared/company/OKR_GUIDE.md`
- **Beads Workflow:** `storage/shared/company/BEADS_WORKFLOW.md`
- **Agent Instructions:** `AGENTS.md`

## Directory Structure

```
.
├── AGENTS.md              # Worker instructions
├── README.md              # This file
├── config/                # Provider and template configs
├── live/                  # Runtime state
│   ├── quinn.db           # Central database
│   ├── logs/              # System logs
│   └── workers/           # Worker session state
├── org-chart/             # Org structure (git-tracked)
└── storage/               # File storage
    ├── shared/            # Org-wide shared resources
    └── workers/           # Worker personal storage
```

## Commands

### Organization Management
```bash
qn --org-path . org start         # Start org (CEO session)
qn --org-path . org stop          # Stop org gracefully
qn --org-path . org status        # Check status
qn --org-path . org hire          # Hire new worker
qn --org-path . org observe       # Watch worker sessions
```

### Worker Operations (run from within worker sessions)
```bash
qn wrkr get-work        # Get assigned work
qn wrkr status          # Check worker status
qn wrkr inbox           # View messages
qn wrkr report          # Report progress
```

### Work Tracking
```bash
bd ready                # Find available work
bd show <id>            # View issue details
bd update <id> --claim  # Claim work
bd close <id>           # Complete work
bd list --label=okr     # View OKRs
bd sync                 # Sync with git
```

## Environment Setup

Required environment variables:
```bash
export ANTHROPIC_API_KEY="sk-ant-..."  # For Claude-based workers
```

Optional:
```bash
export OPENAI_API_KEY="sk-..."         # For GPT-based workers
export QUINN_ORG_PATH="$(pwd)"         # Set org path
```

## Next Steps

1. **Review OKRs:** `bd list --label=okr` - Understand strategic goals
2. **Start the org:** `qn --org-path . org start` - Activate CEO
3. **Monitor progress:** `bd ready` - See available work
4. **Hire workers:** `qn --org-path . org hire --name=Alice --role=Engineer` - Grow the team

## Documentation

- **Architecture:** See `/Users/qosha/Repos/small-bizs/agentic-tools/quinnai/README.md`
- **Development:** See `/Users/qosha/Repos/small-bizs/agentic-tools/quinnai/CLAUDE.md`
- **Worker guides:** `storage/shared/company/*.md`

## Support

This org was initialized from beads in `/Users/qosha/Repos/ceo` with the following epics:
- Beads Dashboard v1.0 - Production Ready
- Testing Infrastructure Sprint
- Architecture & Performance Sprint
- UI/UX Improvements Sprint

All operational work has been structured to serve these OKRs.
