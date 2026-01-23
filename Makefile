.PHONY: help setup test board lint clean verify

# QuinnAI Project Makefile
# RollerCoaster Tycoon for AI Organizations

help:
	@echo "QuinnAI - Development Commands"
	@echo ""
	@echo "Setup & Development:"
	@echo "  make setup      - Run development environment setup"
	@echo "  make test       - Run pytest test suite"
	@echo "  make lint       - Run ruff and black linters"
	@echo "  make verify     - Verify installation is working"
	@echo ""
	@echo "Running QuinnAI:"
	@echo "  make board      - Launch the board terminal UI"
	@echo ""
	@echo "Maintenance:"
	@echo "  make clean      - Clean up generated files (.pyc, __pycache__, etc.)"
	@echo ""
	@echo "Template Sync (from upstream b2b-saas-template):"
	@echo "  make template-fetch  - Fetch latest from template repo"
	@echo "  make template-diff   - Show changes since last sync"
	@echo "  make template-merge  - Merge template updates"
	@echo ""

# Development setup
setup:
	@chmod +x scripts/setup-dev.sh
	./scripts/setup-dev.sh

# Run tests
test:
	pytest

# Launch board UI
board:
	@chmod +x scripts/run-board.sh
	./scripts/run-board.sh

# Verify installation
verify:
	@chmod +x scripts/verify-setup.sh
	./scripts/verify-setup.sh

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

# Template sync commands
# Remote 'template' points to: https://github.com/qosha1/b2b-saas-template.git
template-fetch:
	@echo "Fetching latest from template repo..."
	git fetch template

template-diff:
	@echo "Changes in template since last sync:"
	git log HEAD..template/main --oneline
	@echo ""
	@echo "Files changed:"
	git diff HEAD..template/main --stat

template-merge:
	@echo "Merging template updates..."
	@echo "This will open an editor for conflict resolution if needed."
	git merge template/main --no-commit --no-ff
	@echo ""
	@echo "Review changes with 'git status' and 'git diff --staged'"
	@echo "Then commit with: git commit -m 'Merge template updates'"
	@echo "Or abort with: git merge --abort"

template-cherry:
	@echo "Usage: make template-cherry COMMIT=<sha>"
	@echo "Cherry-pick a specific commit from template"
	@if [ -n "$(COMMIT)" ]; then git cherry-pick $(COMMIT) --no-commit; fi
