"""
Conversation model for AI agent sessions.

Structured representation of agent conversations:
- Message: single message with role (user/assistant/tool_call/tool_result)
- Turn: one exchange (prompt + response + tool calls)
- Transcript: ordered conversation history

Note: Message, MessageRole, ToolCall, ToolResult are imported from shared.core.message
for canonical source. ConversationMessage is aliased as Message for backward compatibility.
"""

from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from typing import Any

# Import canonical types from shared.core.message
from shared.core.message import (
    MessageRole,
    ToolCall,
    ToolResult,
    ConversationMessage as Message,
)


@dataclass
class Turn:
    """
    A single turn in the conversation.

    A turn represents one exchange: user prompt -> assistant response.
    May include multiple tool calls/results within the assistant's response.

    Thread Safety:
        All state-modifying methods are protected by an internal lock.
        complete() can only be called once per turn.

    Work Dimensions:
        ask_id: Links to Ask bead (who requested, what, why)
        okr_id: Links to OKR for strategic alignment
    """

    id: str
    prompt: Message  # User message that started this turn
    response: Message | None = None  # Assistant's final response
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    # Work dimensions
    ask_id: str | None = None  # Link to Ask bead
    okr_id: str | None = None  # Link to OKR for alignment
    # Thread safety
    _lock: Lock = field(default_factory=Lock, repr=False, compare=False)

    @property
    def is_complete(self) -> bool:
        """Turn is complete when we have a response."""
        return self.response is not None

    @property
    def duration_ms(self) -> int | None:
        """Duration in milliseconds, if complete."""
        if not self.completed_at:
            return None
        delta = self.completed_at - self.started_at
        return int(delta.total_seconds() * 1000)

    def add_tool_call(self, tool_call: ToolCall) -> None:
        """Add a tool call to this turn. Thread-safe."""
        with self._lock:
            self.tool_calls.append(tool_call)

    def add_tool_result(self, tool_result: ToolResult) -> None:
        """Add a tool result to this turn. Thread-safe."""
        with self._lock:
            self.tool_results.append(tool_result)

    def complete(self, response: Message) -> None:
        """Mark turn as complete with final response.

        Thread-safe. Can only be called once per turn.

        Raises:
            RuntimeError: If the turn has already been completed.
        """
        with self._lock:
            if self.response is not None:
                raise RuntimeError(
                    f"Turn {self.id} already completed. Cannot complete twice."
                )
            self.response = response
            self.completed_at = datetime.now()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "prompt": self.prompt.to_dict(),
            "response": self.response.to_dict() if self.response else None,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "tool_results": [tr.to_dict() for tr in self.tool_results],
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "is_complete": self.is_complete,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
            # Work dimensions
            "ask_id": self.ask_id,
            "okr_id": self.okr_id,
        }

    def get_messages(self) -> list[Message]:
        """Get all messages in this turn in order."""
        messages = [self.prompt]

        # Interleave tool calls and results by timestamp
        tool_events: list[tuple[datetime, Message]] = []
        for tc in self.tool_calls:
            tool_events.append((tc.timestamp, Message.from_tool_call(tc)))
        for tr in self.tool_results:
            tool_events.append((tr.timestamp, Message.from_tool_result(tr)))

        tool_events.sort(key=lambda x: x[0])
        messages.extend(msg for _, msg in tool_events)

        if self.response:
            messages.append(self.response)

        return messages


class Transcript:
    """
    Complete conversation transcript.

    Maintains ordered history of turns and provides query methods.

    Thread Safety:
        All state-modifying methods are protected by an internal lock.
        Read operations return copies to prevent external modification races.
    """

    def __init__(self):
        self._turns: list[Turn] = []
        self._turn_counter = 0
        self._lock = Lock()

    def new_turn(
        self,
        prompt: str,
        ask_id: str | None = None,
        okr_id: str | None = None,
        **metadata,
    ) -> Turn:
        """Start a new turn with a user prompt. Thread-safe.

        Args:
            prompt: The user's prompt text.
            ask_id: Optional link to Ask bead (work dimension).
            okr_id: Optional link to OKR (work dimension).
            **metadata: Additional metadata for the turn.

        Returns:
            The new Turn instance.
        """
        with self._lock:
            self._turn_counter += 1
            turn = Turn(
                id=f"turn-{self._turn_counter}",
                prompt=Message.user(prompt),
                metadata=metadata,
                ask_id=ask_id,
                okr_id=okr_id,
            )
            self._turns.append(turn)
            return turn

    def current_turn(self) -> Turn | None:
        """Get the current (most recent) turn. Thread-safe."""
        with self._lock:
            return self._turns[-1] if self._turns else None

    def get_turn(self, turn_id: str) -> Turn | None:
        """Get a specific turn by ID. Thread-safe."""
        with self._lock:
            for turn in self._turns:
                if turn.id == turn_id:
                    return turn
            return None

    @property
    def turns(self) -> list[Turn]:
        """All turns in order. Returns a copy for thread safety."""
        with self._lock:
            return list(self._turns)

    def __len__(self) -> int:
        with self._lock:
            return len(self._turns)

    def __iter__(self):
        # Return iterator over a copy for thread safety
        with self._lock:
            return iter(list(self._turns))

    def get_messages(self) -> list[Message]:
        """Get all messages across all turns. Thread-safe."""
        with self._lock:
            messages = []
            for turn in self._turns:
                messages.extend(turn.get_messages())
            return messages

    def get_user_messages(self) -> list[Message]:
        """Get only user messages. Thread-safe."""
        return [m for m in self.get_messages() if m.role == MessageRole.USER]

    def get_assistant_messages(self) -> list[Message]:
        """Get only assistant messages. Thread-safe."""
        return [m for m in self.get_messages() if m.role == MessageRole.ASSISTANT]

    def get_tool_calls(self) -> list[ToolCall]:
        """Get all tool calls. Thread-safe."""
        with self._lock:
            calls = []
            for turn in self._turns:
                calls.extend(turn.tool_calls)
            return calls

    def get_tool_results(self) -> list[ToolResult]:
        """Get all tool results. Thread-safe."""
        with self._lock:
            results = []
            for turn in self._turns:
                results.extend(turn.tool_results)
            return results

    def to_dict(self) -> dict:
        """Convert to dictionary. Thread-safe."""
        with self._lock:
            return {
                "turns": [t.to_dict() for t in self._turns],
                "total_turns": len(self._turns),
                "total_messages": sum(len(t.get_messages()) for t in self._turns),
                "total_tool_calls": sum(len(t.tool_calls) for t in self._turns),
            }

    def to_text(self, include_tools: bool = True) -> str:
        """Convert to human-readable text format. Thread-safe."""
        with self._lock:
            lines = []
            for turn in self._turns:
                lines.append(f"User: {turn.prompt.content}")
                if include_tools:
                    for tc in turn.tool_calls:
                        lines.append(f"  [Tool Call] {tc.name}({tc.arguments})")
                    for tr in turn.tool_results:
                        status = "OK" if tr.success else "ERROR"
                        lines.append(f"  [Tool Result: {status}] {tr.output[:50]}...")
                if turn.response:
                    lines.append(f"Assistant: {turn.response.content}")
                lines.append("")
            return "\n".join(lines)

    def clear(self) -> None:
        """Clear all turns. Thread-safe."""
        with self._lock:
            self._turns.clear()
            self._turn_counter = 0
