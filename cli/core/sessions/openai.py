"""
OpenAISession - SessionInterface implementation for OpenAI API.

Unlike ClaudeCodeSession which wraps a CLI subprocess, this adapter
communicates directly with the OpenAI API. No terminal, no tmux,
no process spawning - just API calls.

Session = Worker's Brain. One session, one worker. Unbreakable 1:1.
"""

from datetime import datetime
from typing import Optional

from core.session import (
    SessionInterface,
    SessionConfig,
    SessionOutput,
)
from providers.base import ProviderConfig
from providers.openai import OpenAIProvider, TOKEN_COSTS
from shared.core import Message


class OpenAISession(SessionInterface):
    """
    SessionInterface implementation for OpenAI API.

    This adapter uses the OpenAI API directly rather than a CLI subprocess.
    It maintains conversation history internally and tracks token usage.

    Key differences from CLI-based sessions:
    - No subprocess spawning (API calls instead)
    - No tmux session management
    - Always "ready" after start (no startup detection needed)
    - Conversation state is internal (not terminal buffer)

    Example:
        config = SessionConfig(
            worker_id="alice",
            provider="openai",
            command="",  # Not used for API sessions
            args=["--model", "gpt-4o"],  # Model selection
        )
        session = OpenAISession(config, api_key="sk-...")
        session.start()
        result = session.send_prompt("Hello!")
        session.stop()
    """

    # Provider capabilities - used by registry and CLI commands
    CAPABILITIES = [
        "file_read",
        "web_search",
        "vision",
        "function_calling",
        "multi_turn",
        "streaming",
        "code_interpreter",
    ]

    def __init__(
        self,
        config: SessionConfig,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = 60,
        default_model: str = "gpt-4o",
    ):
        """Initialize OpenAI session.

        Args:
            config: SessionConfig with provider settings
            api_key: OpenAI API key (required)
            base_url: Optional custom API base URL
            timeout: Request timeout in seconds
            default_model: Default model to use if not specified in args
        """
        super().__init__(config)

        self._api_key = api_key
        self._base_url = base_url
        self._timeout = timeout
        self._default_model = default_model

        # Extract model from args if present (--model <model>)
        self._model = self._extract_model_from_args(config.args)

        # Provider instance (created on start)
        self._provider: Optional[OpenAIProvider] = None

        # Conversation history
        self._messages: list[Message] = []

        # Token tracking
        self._total_input_tokens = 0
        self._total_output_tokens = 0

        # Last response (for _read_output)
        self._last_output: Optional[SessionOutput] = None

    def _extract_model_from_args(self, args: list[str]) -> str:
        """Extract model from args list.

        Looks for --model or -m followed by model name.

        Args:
            args: Command arguments

        Returns:
            Model ID or default model
        """
        for i, arg in enumerate(args):
            if arg in ("--model", "-m") and i + 1 < len(args):
                return args[i + 1]
        return self._default_model

    # =========================================================================
    # Abstract property implementations
    # =========================================================================

    @property
    def provider_name(self) -> str:
        """Provider name."""
        return "openai"

    @property
    def pid(self) -> Optional[int]:
        """Process ID - None for API sessions (no subprocess)."""
        return None

    @property
    def platform_session_name(self) -> Optional[str]:
        """Platform session name - None for API sessions (no tmux)."""
        return None

    # =========================================================================
    # Abstract method implementations
    # =========================================================================

    def _spawn_process(self) -> None:
        """Initialize the OpenAI provider.

        For API sessions, this creates the provider instance
        rather than spawning a subprocess.
        """
        if not self._api_key:
            from core.session import SessionSpawnError
            raise SessionSpawnError(self._id, "OpenAI API key is required")

        provider_config = ProviderConfig(
            api_key=self._api_key,
            base_url=self._base_url,
            timeout=self._timeout,
        )

        self._provider = OpenAIProvider(provider_config)

        # Clear conversation history on new session
        self._messages = []
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._last_output = None

    def _terminate_process(self, force: bool = False) -> None:
        """Clean up the provider.

        For API sessions, this just clears state - no process to kill.

        Args:
            force: Ignored for API sessions
        """
        self._provider = None
        self._last_output = None

    def _send_input(self, text: str) -> None:
        """Send a message to the conversation.

        For API sessions, this adds a user message to history
        and makes an API call.

        Args:
            text: User message text (may include trailing newline)
        """
        if not self._provider:
            return

        # Clean up newlines from prompt
        prompt = text.rstrip("\n")

        # Add user message to history
        self._messages.append(Message(role="user", content=prompt))

        try:
            # Make API call
            result = self._provider.complete(
                messages=self._messages,
                model=self._model,
            )

            # Add assistant response to history
            self._messages.append(Message(role="assistant", content=result.content))

            # Update token tracking
            self._total_input_tokens += result.usage.get("input_tokens", 0)
            self._total_output_tokens += result.usage.get("output_tokens", 0)

            # Store result for _read_output
            self._last_output = SessionOutput(
                content=result.content,
                timestamp=datetime.now(),
                is_complete=True,
                tool_calls=[],
                metadata={
                    "model": result.model,
                    "stop_reason": result.stop_reason,
                    "tokens": result.usage.get("input_tokens", 0) + result.usage.get("output_tokens", 0),
                    "input_tokens": result.usage.get("input_tokens", 0),
                    "output_tokens": result.usage.get("output_tokens", 0),
                },
            )

        except Exception as e:
            # Store error as output
            self._last_output = SessionOutput(
                content=f"Error: {e}",
                timestamp=datetime.now(),
                is_complete=True,
                metadata={"error": str(e)},
            )
            raise

    def _read_output(self, timeout_ms: Optional[int] = None) -> SessionOutput:
        """Read the last output.

        For API sessions, this returns the cached response
        from the last _send_input call.

        Args:
            timeout_ms: Ignored for API sessions (response already available)

        Returns:
            SessionOutput with last response
        """
        if self._last_output:
            return self._last_output

        return SessionOutput(
            content="",
            timestamp=datetime.now(),
            is_complete=True,
        )

    def _detect_ready(self, output: str) -> bool:
        """API sessions are always ready.

        Args:
            output: Ignored for API sessions

        Returns:
            True - API is always ready after initialization
        """
        return self._provider is not None

    def _detect_completion(self, output: str) -> bool:
        """API responses are always complete.

        Args:
            output: Ignored for API sessions

        Returns:
            True - API responses are complete when returned
        """
        return True

    def _get_context_usage(self) -> int:
        """Get current context token usage.

        Returns:
            Total tokens consumed in this session
        """
        return self._total_input_tokens + self._total_output_tokens

    def _send_interrupt(self) -> None:
        """Cancel current operation.

        For API sessions, this is a no-op since API calls are synchronous.
        The cancellation would need to happen at the HTTP client level.
        """
        pass

    # =========================================================================
    # Extended functionality
    # =========================================================================

    def get_conversation_history(self) -> list[dict]:
        """Get the conversation history.

        Returns:
            List of message dictionaries with role and content
        """
        return [
            {"role": m.role, "content": m.content}
            for m in self._messages
        ]

    def add_system_message(self, content: str) -> None:
        """Add a system message to the conversation.

        Should be called before sending any user messages.

        Args:
            content: System message content
        """
        # Insert at beginning if first message, otherwise just add
        if not self._messages:
            self._messages.append(Message(role="system", content=content))
        elif self._messages[0].role != "system":
            self._messages.insert(0, Message(role="system", content=content))
        else:
            # Update existing system message
            self._messages[0] = Message(role="system", content=content)

    def clear_history(self) -> None:
        """Clear conversation history.

        Keeps system message if present.
        """
        if self._messages and self._messages[0].role == "system":
            self._messages = [self._messages[0]]
        else:
            self._messages = []

    def get_token_usage(self) -> dict[str, int]:
        """Get detailed token usage.

        Returns:
            Dictionary with input_tokens, output_tokens, and total
        """
        return {
            "input_tokens": self._total_input_tokens,
            "output_tokens": self._total_output_tokens,
            "total": self._total_input_tokens + self._total_output_tokens,
        }

    def estimate_cost(self) -> float:
        """Estimate cost of tokens consumed.

        Returns:
            Estimated cost in USD
        """
        costs = TOKEN_COSTS.get(self._model, {"input": 0.0, "output": 0.0})
        input_cost = (self._total_input_tokens / 1000) * costs["input"]
        output_cost = (self._total_output_tokens / 1000) * costs["output"]
        return input_cost + output_cost

    @property
    def model(self) -> str:
        """Current model being used."""
        return self._model

    @model.setter
    def model(self, value: str) -> None:
        """Set the model to use.

        Args:
            value: Model ID (e.g., 'gpt-4o', 'gpt-4o-mini')
        """
        self._model = value
