# Validation Tiers — Status Report

Generated 2026-04-28 after completing all three tier epics.

## TL;DR

| Tier | Epic ID | Children Closed | Tests | Outcome |
|---|---|---:|---:|---|
| 1 — State-machine sequences | quinn-ai-anse | 12/12 | 50 pass | shipped, sub-second, modularity proven |
| 2 — FakeSpawner scenarios | quinn-ai-u6e0 | 12/12 | 18 unit + 4 integration pass / 3 xfail | shipped; xfails linked to bug beads |
| 3 — Live LLM canary | quinn-ai-yimo | 12/12 | 15 unit pass + 1 canary skipped | shipped; live run is operator-gated |

Total new code: ~1340 LoC across `shared/testing/{state_machines,scenarios,canary}/` + ~770 LoC of tests.
Total test count delta: +88 (+87 currently green, +1 skipped, +3 xfail).

Combined commits:
- `05db0f0` — Tier 1
- `568f01a` — Tier 2
- `2b1fc82` — Tier 3

All pushed to `main`.

## Open bugs surfaced by Tier 2 (file → fix later)

These are real QuinnAI bugs the scenario suite caught when written against the documented interface. Each is a separate bead with reproduction notes.

| Bead | Severity | What |
|---|---|---|
| quinn-ai-tk8n | P3 | README + CLAUDE.md reference `qn org init --ceo-role` but the option doesn't exist. |
| quinn-ai-cvpg | P3 | `qn org promote --to team-lead` requires a manager to have non-zero `delegated_budget`; chain-hire scenarios need a `delegate_authority` op first. |
| quinn-ai-4zgi | P3 | `pred_okr_owner` queries non-existent `okrs` SQL table; OKRs are stored as beads of type `okr`. Need to read via `qn-bd show --json`. |
| quinn-ai-dccb | P3 | `qn org okr set` doesn't expose the generated bead id, so chained KR ops can't reference the OKR they just created. |
| quinn-ai-772u | P3 | `qn-bd update --assignee` subcommand surface is unverified against the bd 1.x binary. Scenario 06 currently xfailed pending real-bd verification. |

Plus pre-existing bugs from earlier sessions still open:
- quinn-ai-652 was closed during the publishing work (bd integration fixture fix)
- quinn-ai-xsv was closed earlier (board UI install message)

Run `bd ready --priority 3` to surface the next wave.

## Open questions for the human

1. **Scenario 03 chain_3_levels** — should we add a `delegate_authority` op + auto-budget-grant before any chain-hire test? Or leave 03 xfailed until the underlying authority cascade is reworked?
2. **Tier 3 canary scenario design** — the current `01_ceo_hires_one_worker.yml` assumes the CEO will obey a one-shot directive sent via `msgr`. If the real CEO prompt is doing something fancier (e.g. needs a planning step), the canary will time out. Worth a quick local trial run with `QUINNAI_RUN_CANARY=1` + `QUINNAI_CANARY_BUDGET_USD=0.10` to see what actually happens before adding more scenarios.
3. **Tier 2 brutality scenarios** — the "complex_reorg_lite" demo proved the harness is data-driven; should we ship it as a permanent scenario in `tests/scenarios/specs/` or keep it as a one-off proof?
4. **CI integration** — Tier 1+2 currently only run when invoked manually. Worth adding to a non-release workflow (e.g. `test-integration.yml`) so they gate PRs?
5. **Pricing.yaml drift** — Anthropic's published prices change roughly quarterly. Worth a calendar reminder / scheduled bd to check pricing every 90 days?

## How to run each tier locally

```bash
# Tier 1 (sub-second, no deps)
pytest tests/state_sequences/

# Tier 2 (~22s, in-process Click + FakeSpawner)
pytest tests/scenarios/

# Tier 3 unit tests (no LLM spend)
pytest tests/canary/unit/

# Tier 3 actual canary (costs ~$0.10 per run)
QUINNAI_RUN_CANARY=1 ANTHROPIC_API_KEY=sk-ant-... \
  QUINNAI_CANARY_BUDGET_USD=0.10 \
  pytest -m canary tests/canary/

# Everything except live canary
pytest tests/state_sequences/ tests/scenarios/ tests/canary/unit/
# 87 passed, 3 xfailed, ~50s
```

## Next pass — suggested order

1. Knock out quinn-ai-tk8n (one-line option add OR docs strip).
2. Fix quinn-ai-4zgi + quinn-ai-dccb together — both touch the OKR-as-bead path.
3. Fix quinn-ai-cvpg (delegate_authority op for the scenario harness).
4. Run a real Tier 3 canary locally with $0.10 cap; iterate the scenario YAML if the real CEO behavior diverges.
5. Once the 3 xfails go green, remove them from EXPECTED_FAILURES in `tests/scenarios/conftest.py`.
