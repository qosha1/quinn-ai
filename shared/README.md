# QuinnAI Shared

Shared business logic for QuinnAI components.

This package contains:
- State machine definitions (org, worker lifecycle and runtime)
- Business exceptions
- Provider interfaces and type definitions
- `wrkr/` - Pure state machine worker abstraction (provider-agnostic)
- `pyterm/` - Terminal session management for AI workers

Used by:
- `cli/` - Command-line interface
- `backend/` - Django backend
