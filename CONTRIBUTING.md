# Contributing to QuinnAI

## Development Setup

### Prerequisites

- Python 3.11+
- tmux (for worker session management)
- At least one provider API key (Anthropic or OpenAI)

### Getting Started

```bash
# Clone the repository
git clone https://github.com/qosha1/quinnai.git
cd quinnai

# Run the setup script (creates venv, installs dependencies)
make setup

# Or manually:
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pip install -e "./terminal-app[dev]"
```

### Environment Configuration

Copy the example environment file and add your API keys:

```bash
cp .envs/.local/.django.example .envs/.local/.django
```

Edit `.envs/.local/.django` with your keys:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."
```

Load environment before running:

```bash
source .venv/bin/activate
source .envs/.local/.django
```

## Code Style

### Python

- **Formatter**: black (line-length: 100)
- **Linter**: ruff
- **Type hints**: Required for all public functions
- **Target**: Python 3.11+

Run linters:

```bash
make lint      # Check for issues
make format    # Auto-fix issues
```

Configuration is in `backend/pyproject.toml`:
- ruff: E, W, F, I, B, C4, UP rules enabled
- black: 100 character line length
- isort: black profile

### Type Hints

All public functions must have type hints:

```python
def create_worker(name: str, skills: dict[str, int]) -> Worker:
    ...
```

## Testing

### Running Tests

```bash
# Required before every code change
systemeval test

# Or using make
make test

# Or directly with pytest
pytest
```

Tests must pass before submitting PRs. No exceptions.

### Adding Tests

- Place tests in `cli/tests/` or component-specific `tests/` directories
- Use pytest conventions: `test_*.py` files, `test_*` functions
- Follow existing test patterns in the codebase

Example:

```python
# cli/tests/test_worker.py
def test_worker_creation():
    worker = Worker(name="dev-1", skills={"coding": 80})
    assert worker.name == "dev-1"
    assert worker.skills["coding"] == 80
```

## Pull Request Process

### Branch Naming

Use descriptive branch names:

```
feature/worker-session-management
fix/org-init-path-validation
refactor/provider-abstraction
```

### Commit Format

- Atomic commits: one logical change per commit
- Clear, concise messages describing the "why" not just "what"
- No "critical fix" or hyperbolic language
- No `Co-Authored-By` lines

Good:
```
Add worker lifecycle state transitions

Workers now move through: pending -> onboarding -> active -> offboarding -> terminated
```

Bad:
```
CRITICAL FIX: Fixed the super important bug!!!
```

### Before Submitting

1. **Run tests**: `systemeval test` must pass
2. **Run linters**: `make lint` should be clean
3. **Check types**: Ensure type hints are present
4. **Update relevant docs**: If you changed behavior

### Review Process

1. Open a PR against `main`
2. Describe what changed and why
3. Link any related issues
4. Wait for review
5. Address feedback
6. Merge once approved

## Issue Reporting

### Bug Reports

Include:

1. **What happened**: Clear description of the bug
2. **What you expected**: Expected behavior
3. **Steps to reproduce**: Minimal steps to trigger the issue
4. **Environment**: Python version, OS, relevant config
5. **Logs/errors**: Full error messages or stack traces

### Feature Requests

Include:

1. **Problem**: What problem does this solve?
2. **Proposed solution**: How should it work?
3. **Alternatives considered**: Other approaches you thought about
4. **Additional context**: Mockups, examples, related issues

### Issue Labels

- `bug`: Something isn't working
- `feature`: New functionality
- `docs`: Documentation improvements
- `refactor`: Code improvements without behavior change

## Architecture Notes

Before contributing, review `CLAUDE.md` for core principles:

- **Code = Physics, Config = Behavior**: Don't hardcode behavioral decisions
- **No provider lock-in**: Design interfaces, not implementations
- **No magic values**: All config explicit, no discovery
- **Interface-first**: Build for 10 providers even with 1

## Questions?

Open an issue with the `question` label or check existing issues for answers.
