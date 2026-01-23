# Claude Code CLI Integration Research

## Overview

Research findings on how Claude Code CLI is integrated into QuinnAI's session abstraction layer.

## 1. Invocation

Claude Code is spawned via pyterm's `AgentSession` with tmux as the default spawner.

**Command Structure:**
```bash
claude --dangerously-skip-permissions
```

**Session Naming:** `qn-{worker_id}` (e.g., `qn-wrkr-alice`)

**Spawning Flow:**
1. `SessionConfig` created with explicit configuration
2. `ClaudeCodeSession._spawn_process()` creates `AgentSessionConfig`
3. `AgentSession` spawns via `TmuxSpawner` (default) or `SubprocessSpawner` (fallback)

## 2. Configuration

**SessionConfig Fields:**
- `worker_id`: Worker binding (1:1 relationship)
- `provider`: "claude_code"
- `command`: Full path to `claude` executable
- `args`: CLI arguments (e.g., `["--dangerously-skip-permissions"]`)
- `working_directory`: Process working dir
- `env_vars`: Environment variables (ANTHROPIC_API_KEY, etc.)
- `cols/rows`: Terminal dimensions (default 120x40)
- `startup_timeout_ms`: 30000 (30s)
- `idle_timeout_ms`: 300000 (5 min)
- `response_timeout_ms`: 600000 (10 min)
- `max_context_tokens`: 100000
- `persist_transcript`: true
- `transcript_db_path`: Path to transcript SQLite DB

**Environment Variables Required:**
- `ANTHROPIC_API_KEY` - Anthropic API key
- Optional: `CLAUDE_CODE_MODEL` for model override

## 3. Input/Output

**Input:**
```python
session.send_prompt(prompt: str, timeout_ms: Optional[int] = None) -> PromptResult
```

Internally sends via `AgentSession._session.send(text + "\n")`.

**Output:**
```python
@dataclass
class SessionOutput:
    content: str            # Raw output
    timestamp: datetime
    is_complete: bool       # Completion detected
    tool_calls: list[dict]  # Parsed tool invocations
    metadata: dict          # State, errors, etc.
```

**Parsing:**
- Uses `ClaudeCodeParser` specific to Claude Code output format
- Extracts tool calls, detects completion, tracks conversation state
- Detects idle state to know when response is complete

**Transcripts:**
- Stored in SQLite via `TranscriptRepository`
- Tracks turns: prompt + response pairs
- Includes metadata: tokens, duration, tool usage

## 4. Session Management

**State Machine:**
```
STOPPED → STARTING → RUNNING ⇄ IDLE → STOPPED
             ↓
          CRASHED
```

**State Transitions:**
| From | To | Trigger |
|------|-----|---------|
| STOPPED | STARTING | start() called |
| STARTING | RUNNING | Prompt sent |
| RUNNING | IDLE | Response complete |
| IDLE | RUNNING | New prompt |
| IDLE | STOPPED | stop() called |
| * | CRASHED | Error/exception |

**1:1 Binding:**
- `SessionBindingManager` enforces worker-session relationship
- One worker = one session
- Cannot bind worker to multiple sessions
- Cannot bind session to multiple workers
- Thread-safe with RLock

## 5. Provider Adapter Pattern

**Registry Pattern:**
```python
registry.register("claude_code", ClaudeCodeSession,
                  aliases=["claude", "anthropic", "claude-code"])
```

**Interface Methods (SessionInterface):**
- `start()` - Spawn and initialize session
- `stop()` - Graceful shutdown
- `terminate()` - Force kill
- `send_prompt()` - Send input, wait for response
- `interrupt()` - Cancel current operation
- `get_output()` - Get latest output
- `get_transcript()` - Get conversation history
- `is_healthy()` - Health check

**Claude-Specific Implementations:**
- `ClaudeCodeSession._spawn_process()` - pyterm spawning
- `ClaudeCodeSession._send_input()` - Write to session
- `ClaudeCodeSession._read_output()` - Parse via ClaudeCodeParser
- `ClaudeCodeSession._detect_ready()` - Idle detection

## 6. Key Files

```
cli/core/sessions/claude_code.py     # Claude Code adapter
cli/core/sessions/registry.py        # Session factory
cli/core/sessions/binding_manager.py # 1:1 binding enforcement
cli/core/session.py                  # SessionInterface ABC
shared/pyterm/parsers.py             # ClaudeCodeParser
```

## 7. Integration Points

**Worker.spawn():**
```python
session = self._session_registry.create_for_worker(
    worker_id=self.id,
    provider_name="claude_code",
    command="/path/to/claude",
    ...
)
self._session_binding.bind(self.id, session.id, session.pid, session)
```

**Command Invocation:**
```python
# In wrkr commands
worker = Worker.get(db, worker_id)
session = worker.get_session()
result = session.send_prompt("Process this task...")
```

## 8. Constants

From `cli/core/constants.py`:
```python
TMUX_SESSION_PREFIX = "qn-"
DEFAULT_STARTUP_TIMEOUT = 30
DEFAULT_RESPONSE_TIMEOUT = 600
DEFAULT_IDLE_TIMEOUT = 300
DEFAULT_HEARTBEAT_THRESHOLD = 60
```

## Next Steps

This research informs the Claude provider specification (quinnai-bvf). Key areas to specify:
1. Exact CLI arguments and their effects
2. Output format parsing rules
3. Error handling patterns
4. Resource limits (memory, tokens)
5. Graceful vs forced termination
