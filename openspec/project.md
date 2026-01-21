# QuinnAI - Project Definition

## Vision

QuinnAI is a self-managed agentic AI organization.

- **AI CEO** manages day-to-day operations, resource allocation, task prioritization
- **Humans are the Board** - provide strategic direction, approve major decisions, course-correct
- **AI Workers** execute tasks autonomously within their domains

This is not a chatbot. This is not an assistant. This is an autonomous organization that happens to be made of AI agents.

## Core Premise

Merge the scattered functionality from previous projects (quinn, brain, dev-hq, bottas) into one cohesive, well-architected system that can:

1. **Observe** - Watch any coding CLI session (terminal-agnostic)
2. **Understand** - Parse context, detect state, identify needs
3. **Decide** - CEO determines if/how to act
4. **Execute** - Workers perform tasks within their capabilities
5. **Report** - Surface results to the board (humans) when needed

## Organizational Structure

```
┌─────────────────────────────────────────────────────────┐
│                    THE BOARD (Humans)                   │
│  • Strategic direction                                  │
│  • Major decision approval                              │
│  • Course correction                                    │
│  • Capability expansion approval                        │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│                      CEO (AI Agent)                     │
│  • Task prioritization                                  │
│  • Resource allocation                                  │
│  • Worker coordination                                  │
│  • Escalation decisions                                 │
│  • Organizational memory                                │
└─────────────────────────────────────────────────────────┘
                            │
            ┌───────────────┼───────────────┐
            ▼               ▼               ▼
     ┌───────────┐   ┌───────────┐   ┌───────────┐
     │  Worker   │   │  Worker   │   │  Worker   │
     │  (domain) │   │  (domain) │   │  (domain) │
     └───────────┘   └───────────┘   └───────────┘
```

## Capabilities (from merged projects)

### From quinn
- Session watching and transcript parsing
- Message queue and processing pipeline
- Terminal injection via IPC

### From brain
- Neural reasoning / lattice computation
- Memory and context management
- Learning from interactions

### From dev-hq
- Project management and task tracking
- Multi-agent orchestration
- Activity streaming

### From bottas
- Worker unit protocol
- Provider abstraction patterns (to be fixed)
- Queue-based task distribution

## Architecture Principles

See CLAUDE.md for full details. Summary:

1. **We define interfaces, providers implement our contracts**
2. **No magic strings/values/numbers - everything in config**
3. **No provider lock-in - swap via config, not code**
4. **Explicit injection, no discovery magic**
5. **No module-level side effects**
6. **Interface-first design (shaped by our needs, not implementations)**

## Technology Stack

TBD - to be decided based on component needs:
- Core orchestration: ?
- AI providers: abstracted (Claude, OpenAI, Ollama, etc.)
- Storage: ?
- IPC/Communication: ?
- Frontend (board dashboard): ?

## Success Criteria

1. **Single entry point** - One command to start the organization
2. **Provider swappable** - Change AI provider via config only
3. **Terminal agnostic** - Works with any CLI, not just Claude Code
4. **Self-managing** - CEO handles routine operations without human intervention
5. **Board escalation** - Humans only involved for strategic decisions
6. **Tests pass** - `systemeval test` returns 0 before any milestone

## Open Questions

1. What triggers board involvement vs CEO autonomy?
2. How do workers register capabilities?
3. What's the memory/state persistence model?
4. How does the CEO learn and improve?
5. What are the initial worker domains?
