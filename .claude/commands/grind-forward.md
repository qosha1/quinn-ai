---
description: Inch up the canary mountain — take the next harder canary from red/flaky to green via a TDD beads loop, then advance.
argument-hint: "[canary spec stem or number, e.g. 04 or 08_incident_under_pressure] (optional — omit to auto-pick the next rung)"
---

# /grind-forward — push the envelope, one rung at a time

The live canaries in `tests/canary/specs/*.yml` are ordered roughly by difficulty
(01 = CEO hires one worker … 10 = operational platform under changing reqs …
host-mode 11/12). They are a real-LLM proving ground that finds bugs unit tests
structurally can't (tmux delivery races, model-refusal behavior, budget chains).

**The discipline: take the next canary that isn't reliably green, drive it green
through a TDD beads loop, then move to the next slightly-harder one.** Don't skip
rungs; each green canary is a load-bearing step.

Target this run: **$ARGUMENTS** (if empty, auto-pick the lowest-numbered canary
that fails or flakes).

## The loop

1. **Pick the rung.** Run canaries in difficulty order; the first that fails or
   flakes is the target. (If `$ARGUMENTS` names one, start there.)

2. **Watch it fail.** Run it live and observe — capture the worker tmux panes
   (`qn-wrkr-*`) while it runs. Read the verdict + transcript. Classify the
   failure precisely:
   - **Platform bug** → fix the code.
   - **Spec bug** (e.g. canary text trips a real guard) → fix the spec.
   - **LLM variance** (inherent multi-agent nondeterminism) → grade it, don't "fix" it.

3. **Bead it first.** `bd create` (or `bd update <id> --claim`) BEFORE writing
   code. One bead per distinct finding — file side-findings immediately, don't
   bury them. Convert relative dates to absolute.

4. **TDD the fix.** Write a test that reproduces the bug **deterministically at
   $0** (no live LLM) and watch it FAIL. Then fix the root cause. Same test now
   PASSES. Never fix a bug you can't reproduce in a test.

5. **Turn it green — live.** Re-run the canary against the real model; confirm
   the deliverable lands AND the bug-class signal is gone (grep the transcript:
   no `does not report`, `issue_prefix`, `Insufficient`, idle CEO, refusals…).

6. **Close the loop.** `bd close <id> --reason "…"`, commit (plain message, NO AI
   attribution), run the relevant regression suite, then **push** (`git pull
   --rebase` → `bd dolt push` → `git push`). Work isn't done until pushed.

7. **Next rung.** Move to the next slightly-harder canary. Repeat.

## Running & watching a canary

```bash
# One canary, live + budget-bounded (isolated; self-cleaning):
QUINNAI_RUN_CANARY=1 QUINNAI_CANARY_BUDGET_SECONDS=900 \
  .venv/bin/python -m pytest \
  "tests/canary/test_run_canaries.py::test_canary[<spec_stem>]" -v

# Watch live in a second shell — sessions exist only during the run:
tmux ls | grep qn-                     # workers appear as they spawn
tmux capture-pane -pt qn-wrkr-XXXX -S - # snapshot a worker's scrollback
```

## Grade variance, don't chase it

Inherently non-deterministic multi-agent canaries get a `scoring:` block instead
of strict all-pass (see `shared/testing/canary/scoring.py`):

```yaml
scoring:
  samples: 2            # run N independent times
  pass_threshold: 0.8   # a run passes when >= this fraction of weighted assertions hold
  consistency_threshold: 0.5  # canary passes when >= this fraction of runs pass
```

Per-assertion `weight:` / `critical:` tune partial credit. The bar is
deterministic; the LLM supplies the variance. `< threshold === fail`.

## Guardrails

- **Isolation:** canaries run in throwaway tmpdirs / local bare remotes — never
  real repos or networked remotes. Keep it that way.
- **Cost:** budget-bound every run (`QUINNAI_CANARY_BUDGET_SECONDS`). Use credits,
  but don't let it spiral.
- **Sessions:** clean up leaked `qn-wrkr-*` tmux sessions after live runs.
- **Never run the full-suite gate while editing** — concurrent edits contaminate
  it with half-applied imports (false failures). Edit, *then* gate.
- **Prompts are files, not magic strings** — agent-facing prompts live in
  `cli/config/templates/*.jinja2`, and must NOT use injection-shaped /
  anti-confirmation language (aligned models refuse it).
