# Release Bootstrap

One-time setup needed before the first PyPI publish. Re-run only if PyPI
credentials, the GitHub repo, or the trusted-publisher configuration change.

## 1. Reserve the package name on PyPI

`quinn-ai` is the single PyPI distribution (the board UI ships inside the
same wheel and is gated behind a `[board]` install extra).

- Verify availability: <https://pypi.org/project/quinn-ai/>.
- Register a PyPI account (or use an existing org account) and confirm the
  email.

## 2. Configure trusted publishing (preferred over an API token)

Trusted publishing avoids storing a long-lived `PYPI_TOKEN` secret and is the
PyPA-recommended path.

1. Go to <https://pypi.org/manage/account/publishing/>.
2. Add a pending publisher for `quinn-ai`:
   - Owner: `qosha1`
   - Repository: `quinn-ai`
   - Workflow: `release.yml`
   - Environment: `pypi` (recommended — allows per-environment review gates)
3. Optionally repeat against TestPyPI
   (<https://test.pypi.org/manage/account/publishing/>) if you want a dry-run
   target. Use environment name `testpypi` there.

## 3. Configure GitHub environments

In repo Settings → Environments:

- Create `pypi` environment.
  - Optional but recommended: require a deployment review from the maintainer
    list, so a tag push cannot publish without explicit human approval.
- Create `testpypi` environment if you want dry-run releases.

## 4. Workflow permissions

`release.yml` declares both required scopes at the workflow level:

```yaml
permissions:
  contents: write   # github-release job: create Release + upload assets
  id-token: write   # publish-pypi job: mint OIDC token PyPI verifies
```

This matches a known-working OIDC trusted-publishing pattern (same shape we
use for npm OIDC elsewhere). Per-job permission scoping was tried first but
some edge cases around id-token claim propagation make the workflow-level
declaration the safer default.

**Repo-level prerequisite:** in *Settings → Actions → General → Workflow
permissions*, ensure the default is *Read repository contents and packages
permissions* (the more restrictive option). Workflow-declared `permissions:`
still grant the named scopes regardless of the repo default — the repo-level
setting only governs jobs that don't declare permissions explicitly.

## 5. Verify with a dry run

Before tagging a real release:

1. Push a `v0.0.0-test` tag to a fork or temporary branch.
2. Watch the release workflow.
3. Confirm the wheel uploads to TestPyPI:
   ```bash
   pip install --index-url https://test.pypi.org/simple/ quinn-ai==0.0.0-test
   ```

## 6. Real release

```bash
./scripts/bump-version.sh patch    # or minor / major
git push origin main
git push origin v$(cat VERSION)
```

The tag push triggers `release.yml`, which runs tests, builds the wheel
and sdist, publishes to PyPI, and creates the GitHub Release.

## When to revisit this doc

- Repo moved or renamed (update Repository/Workflow fields in trusted publisher).
- Maintainer changes (rotate PyPI account, update environment reviewers).
- Workflow filename changes (re-pin trusted publisher to new `<name>.yml`).

---

## 7. Live LLM canary (optional, post-publish)

Tier 3 of the validation strategy runs one scenario against a real Anthropic
model after each publish to catch prompt/onboarding regressions that the
deterministic test layers can't. The canary job in `release.yml` only fires
on tag pushes and is gated on a separate GitHub environment.

### One-time setup

1. Create a PyPI-style GitHub environment named `canary` (Settings →
   Environments → New environment).
2. **Required reviewers:** add your maintainer list — every canary run will
   wait for human approval before the API key is released to the runner.
3. Add `ANTHROPIC_API_KEY` as an environment secret (NOT a repo secret) so
   it's only readable when the `canary` environment is approved.
4. Optional: add `QUINNAI_CANARY_BUDGET_USD` and `QUINNAI_CANARY_BUDGET_SECONDS`
   as environment vars to override the per-run defaults (`$0.50`, `300s`).

### Local trial run

Before relying on the CI canary, run it once locally:

```bash
export QUINNAI_RUN_CANARY=1
export ANTHROPIC_API_KEY=sk-ant-...
export QUINNAI_CANARY_BUDGET_USD=0.10  # tighten for first run
pytest -m canary tests/canary/ -v
```

A pass produces no output other than the test summary. A budget-kill is
treated as a `pytest.skip` (not a failure) so a tight budget doesn't false-
fire the suite. A real assertion failure (e.g. CEO didn't hire anyone) is a
hard test failure with the transcript captured.

### Failure modes

- **`budget exceeded (spend)`** — usage outpaced the per-run USD cap. Either
  raise the cap or investigate why the canary is making more calls than
  expected.
- **`budget exceeded (wall_clock)`** — model didn't finish within
  `budget_seconds`. Often a sign the org never reached `running`; check
  `qn org status` first.
- **assertion violation** — the model ran but the canary's expected end
  state wasn't reached. Read the transcript artifact to triage prompt vs
  onboarding-doc regressions.
