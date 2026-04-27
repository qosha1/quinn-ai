"""
pyterm - Terminal session management for AI workers.

Wraps tmux to provide session control for CLI-based AI providers
(Claude, Codex, Gemini, etc.)

Core concepts:
- Session = Worker's brain (1:1, unbreakable)
- Session ON = awake, Session OFF = asleep
- Provider = CLI tool abstraction
"""

from shared.pyterm.protocols import (
    ExtractedOutput,
    Provider,
    PytermProviderConfig,
    PytermSessionConfig,
    PytermSessionState,
    Session,
)
from shared.pyterm.config import (
    PytermConfig,
    TimingConfig,
    LoopDetectionConfig,
    TerminalSessionConfig,
    validate_config,
    validate_timing_config,
)
from shared.pyterm.tmux_session import TmuxSession
from shared.pyterm.lifecycle import LifecycleHooks, VALID_TRANSITIONS
from shared.pyterm.patterns import PatternRule, PatternMatcher
from shared.pyterm.manager import SessionManager, ManagedSession
from shared.pyterm.conversation import (
    Message,
    MessageRole,
    ToolCall,
    ToolResult,
    Turn,
    Transcript,
)
from shared.pyterm.persistence import TranscriptStore, TRANSCRIPT_SCHEMA_SQL
from shared.pyterm.tools import (
    TrackedCall,
    ToolCallTracker,
    ToolParameter,
    ToolDefinition,
    ToolRegistry,
    ToolConfig,
    CLAUDE_CODE_TOOLS,
    create_claude_code_registry,
    get_standard_tool_config,
    # Individual tool exports
    BASH_TOOL,
    READ_TOOL,
    WRITE_TOOL,
    EDIT_TOOL,
    GLOB_TOOL,
    GREP_TOOL,
    WEB_FETCH_TOOL,
    WEB_SEARCH_TOOL,
    NOTEBOOK_EDIT_TOOL,
    TODO_WRITE_TOOL,
    SKILL_TOOL,
)
from shared.pyterm.parsers import (
    OutputParser,
    ParsedOutput,
    ClaudeCodeParser,
    GenericParser,
    get_parser,
    ParserRegistry,
    get_default_registry,
    create_default_registry,
)
from shared.pyterm.agent_state import AgentState, AgentStateMachine, VALID_AGENT_TRANSITIONS
from shared.pyterm.control import (
    AgentController,
    ControlConfig,
    PytermPromptResult,
    TimeoutError,
    CancelledError,
)
from shared.pyterm.agent_session import (
    AgentSession,
    AgentSessionConfig,
)
# WorkerBridge moved to cli.core.pyterm.worker_bridge — it bridges pyterm
# sessions to cli.core (Worker, bd_wrapper, permissions, queries,
# notifications) so it lives on the cli side, not in shared.

__all__ = [
    # Configuration
    "PytermConfig",
    "TimingConfig",
    "LoopDetectionConfig",
    "TerminalSessionConfig",
    "validate_config",
    "validate_timing_config",
    # Protocols
    "Session",
    "PytermSessionConfig",
    "PytermSessionState",
    "ExtractedOutput",
    "Provider",
    "PytermProviderConfig",
    # Implementation
    "TmuxSession",
    # Lifecycle
    "LifecycleHooks",
    "VALID_TRANSITIONS",
    # Patterns
    "PatternRule",
    "PatternMatcher",
    # Manager
    "SessionManager",
    "ManagedSession",
    # Conversation
    "Message",
    "MessageRole",
    "ToolCall",
    "ToolResult",
    "Turn",
    "Transcript",
    # Persistence
    "TranscriptStore",
    "TRANSCRIPT_SCHEMA_SQL",
    # Tools
    "TrackedCall",
    "ToolCallTracker",
    "ToolParameter",
    "ToolDefinition",
    "ToolRegistry",
    "ToolConfig",
    "CLAUDE_CODE_TOOLS",
    "create_claude_code_registry",
    "get_standard_tool_config",
    "BASH_TOOL",
    "READ_TOOL",
    "WRITE_TOOL",
    "EDIT_TOOL",
    "GLOB_TOOL",
    "GREP_TOOL",
    "WEB_FETCH_TOOL",
    "WEB_SEARCH_TOOL",
    "NOTEBOOK_EDIT_TOOL",
    "TODO_WRITE_TOOL",
    "SKILL_TOOL",
    # Parsers
    "OutputParser",
    "ParsedOutput",
    "ClaudeCodeParser",
    "GenericParser",
    "get_parser",
    "ParserRegistry",
    "get_default_registry",
    "create_default_registry",
    # Agent State
    "AgentState",
    "AgentStateMachine",
    "VALID_AGENT_TRANSITIONS",
    # Control
    "AgentController",
    "ControlConfig",
    "PytermPromptResult",
    "TimeoutError",
    "CancelledError",
    # AgentSession
    "AgentSession",
    "AgentSessionConfig",
]
