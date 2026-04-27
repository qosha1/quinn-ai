# Development Setup

## Installing Development Dependencies

QuinnAI ships as a single `quinnai` package (containing both `cli/` and
`shared/` modules) plus a separate `quinnai-board` package for the terminal UI.

### Quick Setup

From the repository root:

```bash
# Create and activate virtual environment
python3.11 -m venv .venv
source .venv/bin/activate  # On macOS/Linux
# or
.venv\Scripts\activate  # On Windows

# Install all development packages
pip install -r requirements-dev.txt
```

This installs:
- `quinnai` (editable) - CLI + shared business logic, dev extras
- `quinnai-board` (editable) - Terminal UI, dev extras

### Manual Installation

If you need to install packages individually:

```bash
# Install root package (cli + shared) with dev extras
pip install -e .[dev]

# Install terminal-app with dev extras
pip install -e ./terminal-app[dev]
```

### Package Structure

```
quinnai/
├── cli/                 # CLI module (shipped inside `quinnai` wheel)
│   ├── commands/
│   ├── core/
│   ├── providers/
│   └── tests/
├── shared/              # Business logic (shipped inside `quinnai` wheel)
│   ├── __init__.py
│   ├── state_machines.py
│   ├── exceptions.py
│   └── provider_types.py
├── terminal-app/        # quinnai-board package (separate wheel)
│   ├── src/board_ui/
│   └── pyproject.toml
├── pyproject.toml       # quinnai package definition
└── requirements-dev.txt # Development installation
```

## Running Tests

```bash
# Run all tests
systemeval test

# Run specific package tests
python -m pytest cli/tests/ -v
python -m pytest tests/ -v
```

## Verifying Installation

```bash
# Test that the cli + shared modules are importable
python -c "from shared import ORG_STATES; import cli.commands.main; print('Success!')"

# Check installed packages
pip list | grep quinnai
```

You should see something like:
```
quinnai         0.2.0
quinnai-board   0.1.0
```

## Troubleshooting

### ImportError: No module named 'shared' or 'cli'

Make sure you've installed the root package:
```bash
pip install -e .[dev]
```

### Tests failing

Ensure all packages are installed in editable mode:
```bash
pip install -r requirements-dev.txt
systemeval test
```
