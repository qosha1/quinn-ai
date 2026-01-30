# Understanding OKRs in QuinnAI

## What are OKRs?

**Objectives and Key Results** are our strategic goals for the quarter.

- **Objective:** What we want to achieve (the goal)
- **Key Results:** How we measure success (the metrics)

## Current Quarter OKRs

Run this to see all OKRs:
```bash
bd list --label=okr
```

## OKR Structure

```
Q1 2026: Beads Dashboard v1.0 (Main Objective)
├── [TEST] Testing Infrastructure Sprint
│   └── Tasks: Setup Vitest, Component tests, E2E tests...
├── [ARCH] Architecture & Performance Sprint
│   └── Tasks: Connection pooling, Caching, Virtualization...
└── [UX] UI/UX Improvements Sprint
    └── Tasks: Keyboard nav, Mobile support, Accessibility...
```

## How Tasks Relate to OKRs

When you work on a task, check what it **blocks**:

```bash
bd show quinnai-wvn
# Output shows:
# Blocks (1):
#   ← quinnai-4ur: [ARCH] Architecture & Performance Sprint
```

This means:
- Your task (connection pooling) **blocks** the Architecture OKR
- When you complete your task, the OKR gets closer to completion
- The OKR can't close until all blocking tasks are done

## Measuring Success

Each OKR has **Key Results** - measurable success criteria.

**Example OKR:**
```
[ARCH] Architecture & Performance Sprint

Key Results:
- Database connection pooling implemented ✅
- API response time < 100ms (p95) 📊
- Virtualized rendering for 1000+ rows ⏳
- Real-time updates via SSE ⏳
```

Before closing your work, verify it contributes to these metrics.

## Querying OKRs

```bash
# List all OKRs
bd list --label=okr --status=open

# Show OKR with dependencies
bd show <okr-id>

# Find work that blocks an OKR
bd list --status=open | grep "Blocks.*<okr-id>"
```

## Workflow with OKRs

1. **Pick work**
   ```bash
   bd ready  # Shows available tasks
   ```

2. **Understand impact**
   ```bash
   bd show <task-id>  # See which OKR it blocks
   bd show <okr-id>   # Read key results
   ```

3. **Do the work**
   - Keep key results in mind
   - Measure your progress

4. **Close when done**
   ```bash
   bd close <task-id> --reason="Connection pooling implemented, tested, API latency reduced to 80ms"
   ```

## Why OKRs Matter

OKRs give you:
- **Context:** Why this work matters
- **Alignment:** How it fits the bigger picture
- **Measurement:** Clear success criteria
- **Priority:** What's most important

Work without OKRs is just activity. Work aligned to OKRs is strategic impact.
