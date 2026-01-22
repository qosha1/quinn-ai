# GitHub Actions Workflows

This directory contains CI/CD workflows for QuinnAI.

## Workflows

### CI/CD Pipeline (`ci.yml`)

Main workflow handling testing, building, and releasing.

#### Triggers

- **Pull Request**: Runs tests only
- **Push to main**: Runs tests + builds beads binaries + builds Python wheel
- **Release tags (v\*)**: Full pipeline including publishing to GitHub Releases and PyPI

#### Jobs

##### 1. test
Runs on all triggers (PR, push to main, release tags).

- **Matrix**:
  - OS: ubuntu-latest, macos-latest
  - Python: 3.11, 3.12
- **Steps**:
  - Checkout code
  - Setup Python with pip caching
  - Install dependencies: `pip install -e "cli/[dev]"`
  - Run tests: `cd cli && python -m pytest tests/ -v`
  - Upload test results on failure

##### 2. build-beads
Only runs on push to main or release tags.

- **Matrix**:
  - darwin-arm64 (macOS ARM64)
  - darwin-amd64 (macOS Intel)
  - linux-amd64 (Linux x86_64)
- **Steps**:
  - Checkout with submodules
  - Setup Go 1.21
  - Run build script: `./scripts/build-beads.sh`
  - Verify binary exists and is executable
  - Upload artifact for each platform

##### 3. build-python
Only runs on push to main or release tags.
Depends on: build-beads

- **Steps**:
  - Checkout code
  - Setup Python 3.12
  - Download all beads artifacts
  - Install build tools (build, wheel, hatchling)
  - Build wheel: `python -m build --wheel`
  - Test wheel installation
  - Upload wheel artifact (30 day retention)

##### 4. publish-release
Only runs on version tags (v*).
Depends on: test, build-python

- **Steps**:
  - Download Python wheel and beads binaries
  - Create GitHub Release with auto-generated notes
  - Attach wheel and binaries to release
  - Publish to PyPI (requires PYPI_TOKEN secret)

## Configuration

### Required Secrets

- `PYPI_TOKEN`: PyPI API token for publishing packages
  - Create at: https://pypi.org/manage/account/token/
  - Scope: Entire account or specific to quinnai-cli project
  - Add to: Repository Settings > Secrets and variables > Actions

### Environment Variables

Set in workflow file:
- `PYTHON_VERSION_MIN`: 3.11
- `PYTHON_VERSION_MAX`: 3.12
- `GO_VERSION`: 1.21

## Usage

### Running Tests on PR

Tests run automatically on all pull requests. Both Ubuntu and macOS with Python 3.11 and 3.12.

```bash
# PR triggers automatically
# No manual action needed
```

### Building on Main

Builds run automatically when pushing to main.

```bash
git checkout main
git pull
# Merges to main trigger full build
```

### Creating a Release

1. Tag the commit with a version tag:
```bash
git tag -a v0.1.0 -m "Release v0.1.0"
git push origin v0.1.0
```

2. The workflow will:
   - Run all tests
   - Build beads binaries for all platforms
   - Build Python wheel
   - Create GitHub Release
   - Publish to PyPI

### Manual Workflow Dispatch

Currently not configured for manual dispatch. Add to triggers if needed:

```yaml
on:
  workflow_dispatch:
    inputs:
      version:
        description: 'Version to build'
        required: false
```

## Troubleshooting

### Tests Failing

Check test results artifact uploaded on failure:
- Go to Actions tab > Failed workflow run
- Download `test-results-{os}-py{version}` artifact

### Build Failures

**Beads binary not found**:
- Check if `cli/bin/bd` exists after build-beads.sh
- Verify Go version compatibility
- Check submodule initialization

**Wheel build fails**:
- Ensure pyproject.toml is valid
- Check hatchling configuration
- Verify beads artifacts were downloaded

### Publishing Failures

**PyPI token invalid**:
- Regenerate token at PyPI
- Update PYPI_TOKEN secret in repository settings

**Version already exists**:
- PyPI doesn't allow re-uploading same version
- Increment version tag

## Best Practices

1. **Always run tests locally first**: `cd cli && pytest tests/`
2. **Test build script locally**: `./scripts/build-beads.sh`
3. **Use semantic versioning**: v{major}.{minor}.{patch}
4. **Review auto-generated release notes** before publishing
5. **Keep workflows fast**: Current target <10 minutes for full pipeline

## Workflow Execution Time

Approximate times:
- **test**: ~5-8 minutes (parallel across 4 matrix combinations)
- **build-beads**: ~3-5 minutes (parallel across 3 platforms)
- **build-python**: ~2-3 minutes
- **publish-release**: ~1-2 minutes
- **Total**: ~10-15 minutes for full release

## Future Enhancements

Potential improvements:
- [ ] Add Docker image builds
- [ ] Implement security scanning (Snyk, Dependabot)
- [ ] Add performance benchmarking
- [ ] Create preview deployments for PRs
- [ ] Add code coverage reporting
- [ ] Implement canary releases
- [ ] Add Windows beads binary support
