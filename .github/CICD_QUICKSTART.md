# CI/CD Quick Start Guide

## What Happens Automatically?

### On Pull Request
- Tests run on Ubuntu and macOS with Python 3.11 and 3.12
- Results posted to PR checks
- Must pass before merge

### On Push to Main
- All tests run
- Beads binaries built for darwin-arm64, darwin-amd64, linux-amd64
- Python wheel built with bundled beads binaries
- Artifacts stored for 30 days

### On Release Tag (v*)
- All tests run
- All builds complete
- GitHub Release created with auto-generated notes
- Wheel and binaries attached to release
- Package published to PyPI

## Quick Commands

### Test Locally Before Pushing
```bash
cd cli
python -m pytest tests/ -v
```

### Build Beads Binary Locally
```bash
./scripts/build-beads.sh
# Or for specific platform:
PLATFORM=darwin ARCH=arm64 ./scripts/build-beads.sh
```

### Build Python Wheel Locally
```bash
pip install build
python -m build --wheel        # builds quinnai wheel from repo root
python -m build --wheel terminal-app  # builds quinnai-board wheel
```

### Create a Release
```bash
# 1. Update VERSION (single source of truth) and root pyproject.toml
# 2. Commit changes
git add VERSION pyproject.toml
git commit -m "Bump version to 0.2.0"

# 3. Create and push tag
git tag -a v0.2.0 -m "Release v0.2.0"
git push origin main
git push origin v0.2.0

# 4. Workflow runs automatically
# 5. Check Actions tab for progress
```

## Required Secrets

Add these in GitHub Settings > Secrets and variables > Actions:

### PYPI_TOKEN
1. Go to https://pypi.org/manage/account/token/
2. Create new API token
3. Scope: Entire account or quinnai-cli project
4. Copy token (starts with `pypi-`)
5. Add to GitHub secrets as `PYPI_TOKEN`

## Monitoring Workflows

### View Running Workflows
```bash
gh workflow list
gh run list --workflow=ci.yml
gh run watch
```

### Download Artifacts
```bash
# List recent runs
gh run list --limit 5

# Download artifacts from specific run
gh run download <run-id>
```

### View Logs
```bash
# View logs for latest run
gh run view --log

# View specific job logs
gh run view <run-id> --job=<job-id> --log
```

## Troubleshooting

### Tests Failing in CI but Pass Locally
- Different Python version (test both 3.11 and 3.12)
- Different OS (test on Ubuntu if using macOS)
- Missing dependencies in pyproject.toml

### Build Failing
- Check Go version (needs 1.21+)
- Verify build-beads.sh has execute permissions
- Ensure submodules are initialized

### PyPI Publishing Fails
- Verify PYPI_TOKEN secret is set
- Check version doesn't already exist on PyPI
- Ensure version in pyproject.toml matches tag

## Best Practices

1. Always test locally before pushing
2. Use semantic versioning (vMAJOR.MINOR.PATCH)
3. Review auto-generated release notes before publishing
4. Keep workflow fast (currently ~10-15 min for full release)
5. Use draft releases for testing release process
6. Tag commits on main, never feature branches

## Workflow Files

- `.github/workflows/ci.yml` - Main CI/CD pipeline
- `.github/workflows/validate.yml` - Workflow syntax validation
- `.github/workflows/README.md` - Detailed workflow documentation

## Future Improvements

When needed, we can add:
- Docker image builds and publishing
- Security scanning (Dependabot, Snyk)
- Code coverage reporting
- Performance benchmarking
- Preview deployments for PRs
- Canary/staged releases
- Windows beads binary support
