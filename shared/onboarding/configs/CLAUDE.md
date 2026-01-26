# QuinnAI Worker Architecture Rules

These rules apply inside a deployed QuinnAI organization. Follow them in all work.

## QuinnAI Physics
- Session = worker brain (1:1, unbreakable)
- Every agent is a worker (CEO, manager, IC share the same lifecycle)
- One protocol for everything (messages are permanent, notifications are beads)
- Storage mirrors org-chart (shared/ for org, workers/ for individuals)
- Lifecycles = state determines behavior (org, worker, work)

## Architectural Laws
1. Code = physics, config = behavior
2. We define interfaces; providers implement our contracts
3. No magic values (config drives behavior)
4. No config discovery (explicit injection)
5. No module side effects
6. No string dispatch (use polymorphism)
7. Interface-first design

## Operating Constraints
- Use `shared/` for durable knowledge; keep drafts in your worker folder.
- Never assume a single provider or CLI; stay provider-agnostic.
- If you need context, read `BRIEFING.md`, `STORAGE.md`, and `AGENTS.md`.
