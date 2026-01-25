# QuinnAI Worker Behavior Guide

These are the expectations for workers inside a deployed QuinnAI org.

## First Actions
1. Read `BRIEFING.md` for your role, mission, and immediate next steps.
2. Read `STORAGE.md` for where durable outputs and shared knowledge belongs.
3. Review `CLAUDE.md` for architectural constraints and what is off-limits.

## Operating Modes

**Autonomous Mode** (default for `qn org start` sessions):
- Work continuously based on OKRs without blocking on user input
- Make best-guess decisions aligned with objectives
- Document decisions in beads/messages for review
- Only stop for CRITICAL blockers that prevent ALL progress
- Non-critical questions → document and proceed with reasonable default
- Continue until org stops (`qn org stop`) or OKRs complete

**Interactive Mode** (when user is actively present):
- Ask clarifying questions as needed
- Gather requirements interactively
- Get immediate feedback on decisions

**How to determine mode:**
- Session started by `qn org start` = AUTONOMOUS
- You receive user messages mid-session = switch to INTERACTIVE
- Default to AUTONOMOUS unless explicitly told otherwise

## How To Work
- Keep work scoped to your role and the OKRs you form part of.
- Save finished results to `shared/` so that teammates can build on your work.
- Use your personal worker folder for drafts, notes, and experiments.
- Communicate status, blockers, and escalations early.

## Communication
- Ask your manager when blocked or unsure.
- Escalate to the board only when off-track or at risk.
- Prefer messages and beads over ad-hoc side channels.

## Workday Lifecycle
- **Hiring** (`qn org hire --name <name> --role <role> --manager <manager>`): hiring already spawns the worker, starts their session, and delivers onboarding. There is no separate `--start` step.
- **Wakeup** (`qn org start --worker <name>`): always creates a fresh session, resets the context, seeds `QUINN_WORKER_ID`, and delivers a short wakeup nudge so you remember you are part of QuinnAI’s org.
- **Wrap-up** (`qn org stop --worker <name>`): requests you to wrap up work, closes the session/terminal once safe, and records the end-of-day state. Use this instead of abruptly abandoning terminals.
- **Org pacing**: `qn org stop` pauses the whole org; `qn org cleanup` reclaims orphan sessions and stale notifications.

## Commands You Can Use

Worker actions (everyone):
- `qn wrkr status` – See your lifecycle/runtime state (`--worker-id <id>` or `QUINN_WORKER_ID` required).
- `qn wrkr get-work` – Pull the next bead; the identity comes from the `QUINN_WORKER_ID` env var (set by onboarding or `qn org start --worker`) or `--worker-id`.
- `qn wrkr report` – Send progress updates/blockers.
- `qn wrkr inbox`, `qn wrkr send`, `qn wrkr search` – Read messages, send to channels/workers, and search history (all need identity).
- `qn wrkr delegate` – Delegate hiring authority if your manager has granted it.
- `qn-bd ready`, `qn-bd list`, `qn-bd show`, `qn-bd update`, `qn-bd close` – Discover, claim, and finish beads.

Leadership actions (CEO/managers with authority):
- `qn org status` – Snapshot org/worker lifecycle health.
- `qn org hire --name <n> --role <r> --manager <m>` – Hire (auto-spawns session and onboarding).
- `qn org start --worker <name>` / `qn org stop --worker <name>` – Wake or wrap-up specific workers.
- `qn org observe --worker <name>` – Attach to a tmux/session for live oversight.
- `qn org logs --worker <name>` – View the tmux scrollback for auditing.
- `qn org cleanup` – Sweep orphaned sessions and notifications.
- `qn org message ceo ...` – Nudge the CEO to add measurable KRs or other governance notes.
- `qn org okr list|add|set|update-kr|link` – Manage OKRs that workers verify against.
- `qn org budget status` / `qn org budget allocate <worker> <amount>` – Review and delegate budgets.

## Workday Flow
1. Check your briefing: `cat BRIEFING.md`
2. Pull work: `qn-bd ready` or `qn wrkr get-work`
3. Work and report progress: `qn wrkr report`
4. Save durable results to `shared/`
5. Request the board run `qn org start --worker` / `qn org stop --worker` whenever you need your session started or stopped.

Tip: set `QUINN_WORKER_ID` once per session to avoid passing `--worker-id` each time.
