.PHONY: help setup test board lint clean

# QuinnAI Project Makefile
# RollerCoaster Tycoon for AI Organizations

help:
	@echo "QuinnAI - Development Commands"
	@echo ""
	@echo "Setup & Development:"
	@echo "  make setup              - Run development environment setup"
	@echo "  make test               - Run CLI test suite"
	@echo "  make test-terminal-app  - Run terminal-app test suite"
	@echo "  make test-all           - Run ALL test suites (CLI + terminal-app)"
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

# Run terminal-app tests (separate due to sys.path requirements)
test-terminal-app:
	cd terminal-app && ../.venv/bin/pytest

# Run all tests (CLI + terminal-app)
test-all:
	@echo "Running CLI tests..."
	@.venv/bin/pytest; CLI_EXIT=$$?; \
	echo ""; \
	echo "Running terminal-app tests..."; \
	cd terminal-app && ../.venv/bin/pytest; TERM_EXIT=$$?; \
	echo ""; \
	if [ $$CLI_EXIT -eq 0 ] && [ $$TERM_EXIT -eq 0 ]; then \
		echo "✓ All test suites passed"; \
		exit 0; \
	else \
		echo "✗ Some tests failed (CLI exit: $$CLI_EXIT, terminal-app exit: $$TERM_EXIT)"; \
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
