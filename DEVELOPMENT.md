# Development Setup

## Installing Development Dependencies

The QuinnAI project uses a monorepo structure with multiple packages. The `shared/` package contains business logic used by `cli/`, `backend/`, and `wrkr/`.

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

This will install:
- `quinnai-shared` - Business logic and state machines
- `quinnai-cli` - Command-line interface with dev dependencies

### Manual Installation

If you need to install packages individually:

```bash
# Install shared package in editable mode
pip install -e ./shared

# Install CLI package in editable mode with dev dependencies
pip install -e ./cli[dev]
```

### Package Structure

```
quinnai/
├── shared/              # Business logic package (quinnai-shared)
│   ├── __init__.py
│   ├── state_machines.py
│   ├── exceptions.py
│   ├── provider_types.py
│   └── pyproject.toml
├── cli/                 # CLI package (quinnai-cli)
│   ├── commands/
│   ├── core/
│   ├── providers/
│   ├── tests/
│   └── pyproject.toml
└── requirements-dev.txt # Development installation
```

## Running Tests

```bash
# Run all tests
systemeval test

# Run specific package tests
python -m pytest cli/tests/ -v
python -m pytest wrkr/tests/ -v
python -m pytest tests/ -v
```

## Verifying Installation

```bash
# Test that shared package is importable
python -c "from shared import ORG_STATES; print('Success!')"

# Check installed packages
pip list | grep quinnai
```

You should see:
```
quinnai-cli     0.1.0
quinnai-shared  0.1.0
```

## How It Works

The `shared` package is installed as an editable package using pip's `-e` flag. This creates a `.pth` file in the virtual environment's `site-packages` directory that points to the `shared/` directory, making it importable from anywhere.

The `cli` package is also installed in editable mode, allowing you to make changes to the code without reinstalling.

## Troubleshooting

### ImportError: No module named 'shared'

Make sure you've installed the shared package:
```bash
pip install -e ./shared
```

### Tests failing

Ensure all packages are installed in editable mode:
```bash
pip install -r requirements-dev.txt
systemeval test
```
