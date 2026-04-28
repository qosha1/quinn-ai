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
