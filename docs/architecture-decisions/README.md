# Architecture Decision Records

Each ADR documents a significant architectural choice with its context,
the decision, and the consequences. Follow the existing structure when
adding a new one (status / date / context / decision / consequences).

## Index

| ADR | Topic |
|-----|-------|
| [ADR-003](ADR-003-onboarding-session-modification.md) | Onboarding system modifies session spawn |
| [ADR-004](ADR-004-absolute-paths-in-env-vars.md)      | Use absolute paths in environment variables |
| [ADR-005](ADR-005-delegation-authority.md)            | Delegation authority system |
| ADR-006                                                | *(skipped — delegation work originally planned for 006 was merged into ADR-005)* |
| [ADR-007](ADR-007-enhanced-logging-architecture.md)   | Enhanced logging architecture for log-viewer UI |
| [ADR-008](ADR-008-systemeval-integration-testing.md)  | Systemeval integration testing architecture |

ADR-001 and ADR-002 predate this directory and exist only in commit
history; the foundational decisions they documented have since been
absorbed into CLAUDE.md and the package-level docstrings.

## Adding a new ADR

1. Pick the next free number (currently ADR-009).
2. Create `ADR-NNN-short-slug.md` with the standard sections.
3. Link it from the table above.
