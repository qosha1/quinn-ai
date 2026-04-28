.PHONY: help setup test test-board test-e2e test-all board lint clean

# QuinnAI Project Makefile
# RollerCoaster Tycoon for AI Organizations

help:
	@echo "QuinnAI - Development Commands"
	@echo ""
	@echo "Setup & Development:"
	@echo "  make setup              - Run development environment setup"
	@echo "  make test               - Run CLI test suite"
	@echo "  make test-board         - Run board UI test suite (tests/board_ui/)"
	@echo "  make test-e2e           - Run end-to-end CLI tests (real qn + bd, ~3 min)"
	@echo "  make test-all           - Run ALL test suites (CLI + board + e2e)"
	@echo "  make lint               - Run ruff and black linters"
	@echo ""
	@echo "Running QuinnAI:"
	@echo "  make board      - Launch the board terminal UI"
	@echo ""
	@echo "Maintenance:"
	@echo "  make clean      - Clean up generated files (.pyc, __pycache__, etc.)"
	@echo ""

# Development setup
setup:
	@chmod +x scripts/setup-dev.sh
	./scripts/setup-dev.sh

# Run tests
test:
	.venv/bin/pytest

# Run board UI tests (Textual TUI — lives under tests/board_ui/ post-merge)
test-board:
	.venv/bin/pytest tests/board_ui/

# Run end-to-end tests (real qn binary + real bd binary against tmp_path orgs)
# Requires bd on PATH or in cli/bin/{platform}/bd. Skips entire suite if missing.
test-e2e:
	.venv/bin/pytest tests/e2e/ -v --timeout=180

# Run all tests (CLI + board UI + e2e)
test-all:
	@echo "Running CLI tests..."
	@.venv/bin/pytest --ignore=tests/e2e --ignore=tests/board_ui; CLI_EXIT=$$?; \
	echo ""; \
	echo "Running board UI tests..."; \
	.venv/bin/pytest tests/board_ui/; BOARD_EXIT=$$?; \
	echo ""; \
	echo "Running e2e tests..."; \
	.venv/bin/pytest tests/e2e/ --timeout=180; E2E_EXIT=$$?; \
	echo ""; \
	if [ $$CLI_EXIT -eq 0 ] && [ $$BOARD_EXIT -eq 0 ] && [ $$E2E_EXIT -eq 0 ]; then \
		echo "✓ All test suites passed (CLI + board + e2e)"; \
		exit 0; \
	else \
		echo "✗ Some tests failed (CLI: $$CLI_EXIT, board: $$BOARD_EXIT, e2e: $$E2E_EXIT)"; \
		exit 1; \
	fi

# Launch board UI
board:
	@chmod +x scripts/run-board.sh
	./scripts/run-board.sh

# Linting
lint:
	@echo "Running ruff..."
	-ruff check .
	@echo ""
	@echo "Running black..."
	-black --check .

# Format code (fix lint issues)
format:
	ruff check --fix .
	black .

# Clean up generated files
clean:
	@echo "Cleaning up generated files..."
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name ".coverage" -delete
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	@echo "Clean complete."
