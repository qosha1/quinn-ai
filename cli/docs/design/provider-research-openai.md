# OpenAI/Codex CLI Integration Research

## Overview

Research findings on OpenAI provider integration in QuinnAI's session abstraction layer. Two implementations exist:

1. **CodexSession** - CLI-based (similar to Claude Code)
2. **OpenAISession** - Direct API-based (no subprocess)

## 1. Codex CLI Session

### Invocation

Codex is spawned via pyterm's `AgentSession` similar to Claude Code.

**Command Structure:**
```bash
codex --dangerously-skip-permissions
```

**Session Naming:** `qn-{worker_id}`

**Key Difference from Claude Code:**
- Uses `provider="generic"` parser (no Codex-specific parser yet)
- Otherwise identical spawning flow

### Configuration

Same `SessionConfig` as Claude Code:
```python
config = SessionConfig(
    worker_id="alice",
    provider="codex",
    command="codex",
    args=["--dangerously-skip-permissions"],
    working_directory=Path("/path/to/project"),
    env_vars={"CODEX_API_KEY": "..."},
)
```

### Parser Status

Currently uses `GenericParser` which provides basic functionality but lacks:
- Codex-specific output format parsing
- Accurate tool call extraction
- Precise state detection

**TODO:** Create `CodexParser` for accurate output parsing.

## 2. OpenAI API Session

### Key Differences

Unlike CLI sessions, OpenAI API session:
- No subprocess spawning
- No tmux session
- No terminal emulation
- Direct HTTP API calls
- Always "ready" after initialization

### Configuration

```python
session = OpenAISession(
    config=SessionConfig(
        worker_id="alice",
        provider="openai",
        command="",  # Not used
        args=["--model", "gpt-4o"],  # Model selection
    ),
    api_key="sk-...",
    base_url=None,  # Optional custom endpoint
    timeout=60,
    default_model="gpt-4o",
)
```

### Model Selection

Model can be specified via:
1. `args`: `["--model", "gpt-4o"]` or `["-m", "gpt-4o"]`
2. `default_model` parameter (fallback)
3. `session.model = "gpt-4o-mini"` (runtime change)

### API Flow

1. `start()` - Creates `OpenAIProvider` instance
2. `send_prompt()` → `_send_input()`:
   - Adds user message to history
   - Calls `provider.complete(messages, model)`
   - Adds assistant response to history
   - Updates token tracking
3. `_read_output()` - Returns cached response
4. `stop()` - Clears state (no process to kill)

### Conversation Management

```python
# Get history
history = session.get_conversation_history()

# Add system message (before user messages)
session.add_system_message("You are a helpful assistant.")

# Clear history (keeps system message)
session.clear_history()
```

### Token Tracking

```python
usage = session.get_token_usage()
# {"input_tokens": 100, "output_tokens": 50, "total": 150}

cost = session.estimate_cost()
# 0.0045 (USD)
```

### Cost Estimation

Token costs defined in `cli/providers/openai.py`:
```python
TOKEN_COSTS = {
    "gpt-4o": {"input": 0.005, "output": 0.015},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    # etc.
}
```

## 3. Provider Abstraction

Both sessions implement `SessionInterface`:

| Method | CodexSession | OpenAISession |
|--------|-------------|---------------|
| `_spawn_process()` | Creates AgentSession | Creates OpenAIProvider |
| `_terminate_process()` | Stops AgentSession | Clears state |
| `_send_input()` | Sends to terminal | API call |
| `_read_output()` | Parses terminal buffer | Returns cached response |
| `_detect_ready()` | Checks idle state | Always True |
| `_detect_completion()` | Checks idle state | Always True |
| `pid` | Terminal process PID | None |
| `platform_session_name` | tmux session name | None |

## 4. Key Files

```
cli/core/sessions/codex.py    # Codex CLI adapter
cli/core/sessions/openai.py   # OpenAI API adapter
cli/providers/openai.py       # OpenAI API client
cli/providers/base.py         # Provider base classes
```

## 5. Provider Registry

```python
registry.register("codex", CodexSession, aliases=["codex-cli"])
registry.register("openai", OpenAISession, aliases=["gpt", "gpt-4", "gpt-4o"])
```

## 6. State Differences

**CLI Sessions (Codex):**
```
STOPPED → STARTING → RUNNING ⇄ IDLE → STOPPED
```
- State changes based on terminal activity
- Idle detection via parser

**API Sessions (OpenAI):**
```
STOPPED → STARTING → IDLE ⇄ RUNNING → IDLE → STOPPED
```
- Always returns to IDLE after prompt
- No actual "idle" detection needed
- Transitions managed internally

## 7. Limitations

### Codex CLI
- No Codex-specific parser (uses generic)
- Requires `codex` CLI to be installed
- Output parsing may miss Codex-specific patterns

### OpenAI API
- No streaming support (waits for full response)
- No tool use (function calling) support yet
- Interrupt is no-op (synchronous calls)

## Next Steps

This research informs the OpenAI provider specification (quinnai-4y3). Key areas to specify:

1. **For Codex CLI:**
   - Output format documentation
   - Custom parser implementation
   - CLI argument options

2. **For OpenAI API:**
   - Function calling / tool use integration
   - Streaming response support
   - Rate limiting and retries
   - Multi-modal support (vision)
