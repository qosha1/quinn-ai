"""
Provider Configuration Widget.

Allows configuring AI service providers (Anthropic, OpenAI, etc.)
with friendly labels - uses "AI Service" not "LLM Provider".
"""

from dataclasses import dataclass
from typing import Callable, Optional

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, ScrollableContainer
from textual.widgets import Static, Switch, Input, Button, Label
from textual.widget import Widget
from textual.message import Message


@dataclass
class ProviderInfo:
    """Information about an AI provider."""

    id: str
    name: str  # Friendly name like "Anthropic Claude"
    description: str
    enabled: bool = False
    api_key: Optional[str] = None
    is_valid: bool = False


class ProviderConfigWidget(Widget):
    """Widget for configuring AI service providers.

    Shows available providers with enable/disable toggles and
    masked API key inputs.
    """

    DEFAULT_CSS = """
    ProviderConfigWidget {
        height: auto;
        padding: 1;
    }

    ProviderConfigWidget .provider-header {
        text-style: bold;
        margin-bottom: 1;
    }

    ProviderConfigWidget .provider-card {
        border: solid $primary;
        padding: 1;
        margin-bottom: 1;
        height: auto;
    }

    ProviderConfigWidget .provider-card.disabled {
        border: solid $surface;
        opacity: 0.6;
    }

    ProviderConfigWidget .provider-name {
        text-style: bold;
    }

    ProviderConfigWidget .provider-description {
        color: $text-muted;
        margin-bottom: 1;
    }

    ProviderConfigWidget .api-key-row {
        height: 3;
    }

    ProviderConfigWidget .api-key-input {
        width: 1fr;
    }

    ProviderConfigWidget .status-valid {
        color: $success;
    }

    ProviderConfigWidget .status-invalid {
        color: $error;
    }
    """

    # Available providers
    PROVIDERS = [
        ProviderInfo(
            id="anthropic",
            name="Anthropic Claude",
            description="Claude models for reasoning and analysis",
        ),
        ProviderInfo(
            id="openai",
            name="OpenAI GPT",
            description="GPT models for general tasks",
        ),
        ProviderInfo(
            id="claude_code",
            name="Claude Code (CLI)",
            description="Local Claude Code CLI sessions",
            enabled=True,  # Default enabled
            is_valid=True,
        ),
    ]

    class ProviderToggled(Message):
        """Message sent when a provider is enabled/disabled."""

        def __init__(self, provider_id: str, enabled: bool) -> None:
            self.provider_id = provider_id
            self.enabled = enabled
            super().__init__()

    class ApiKeyChanged(Message):
        """Message sent when an API key is changed."""

        def __init__(self, provider_id: str, api_key: str, is_valid: bool) -> None:
            self.provider_id = provider_id
            self.api_key = api_key
            self.is_valid = is_valid
            super().__init__()

    def __init__(
        self,
        providers: Optional[list[ProviderInfo]] = None,
        id: Optional[str] = None,
    ) -> None:
        """Initialize the provider config widget.

        Args:
            providers: List of providers to show. Uses defaults if not provided.
            id: Widget ID.
        """
        super().__init__(id=id)
        self._providers = providers or self.PROVIDERS.copy()

    def compose(self) -> ComposeResult:
        """Compose the provider configuration UI."""
        yield Static("AI Services", classes="provider-header", id="provider-header")

        with ScrollableContainer(id="provider-list"):
            for provider in self._providers:
                yield self._create_provider_card(provider)

    def _create_provider_card(self, provider: ProviderInfo) -> Widget:
        """Create a card for a single provider."""
        card_classes = "provider-card"
        if not provider.enabled:
            card_classes += " disabled"

        card = Vertical(
            Horizontal(
                Static(provider.name, classes="provider-name"),
                Switch(
                    value=provider.enabled,
                    id=f"switch-{provider.id}",
                ),
            ),
            Static(provider.description, classes="provider-description"),
            Horizontal(
                Label("API Key:"),
                Input(
                    value=provider.api_key or "",
                    password=True,
                    placeholder="Enter API key...",
                    id=f"apikey-{provider.id}",
                    classes="api-key-input",
                    disabled=not provider.enabled,
                ),
                Static(
                    "Valid" if provider.is_valid else "",
                    id=f"status-{provider.id}",
                    classes="status-valid" if provider.is_valid else "status-invalid",
                ),
                classes="api-key-row",
            ),
            classes=card_classes,
            id=f"card-{provider.id}",
        )
        return card

    def on_switch_changed(self, event: Switch.Changed) -> None:
        """Handle provider toggle."""
        switch_id = event.switch.id
        if switch_id and switch_id.startswith("switch-"):
            provider_id = switch_id.replace("switch-", "")
            enabled = event.value

            # Update internal state
            for p in self._providers:
                if p.id == provider_id:
                    p.enabled = enabled
                    break

            # Update UI
            card = self.query_one(f"#card-{provider_id}", Vertical)
            if enabled:
                card.remove_class("disabled")
            else:
                card.add_class("disabled")

            # Enable/disable API key input
            api_input = self.query_one(f"#apikey-{provider_id}", Input)
            api_input.disabled = not enabled

            # Post message
            self.post_message(self.ProviderToggled(provider_id, enabled))

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle API key input."""
        input_id = event.input.id
        if input_id and input_id.startswith("apikey-"):
            provider_id = input_id.replace("apikey-", "")
            api_key = event.value

            # Validate API key format
            is_valid = self._validate_api_key(provider_id, api_key)

            # Update internal state
            for p in self._providers:
                if p.id == provider_id:
                    p.api_key = api_key
                    p.is_valid = is_valid
                    break

            # Update status indicator
            status = self.query_one(f"#status-{provider_id}", Static)
            if is_valid:
                status.update("Valid")
                status.remove_class("status-invalid")
                status.add_class("status-valid")
            else:
                status.update("Invalid" if api_key else "")
                status.remove_class("status-valid")
                if api_key:
                    status.add_class("status-invalid")

            # Post message
            self.post_message(self.ApiKeyChanged(provider_id, api_key, is_valid))

    def _validate_api_key(self, provider_id: str, api_key: str) -> bool:
        """Validate API key format for a provider.

        Args:
            provider_id: The provider to validate for.
            api_key: The API key to validate.

        Returns:
            True if the key format is valid.
        """
        # Claude Code doesn't need an API key (uses local CLI)
        if provider_id == "claude_code":
            return True

        if not api_key:
            return False

        # Basic format validation
        if provider_id == "anthropic":
            # Anthropic keys start with "sk-ant-"
            return api_key.startswith("sk-ant-") and len(api_key) > 20
        elif provider_id == "openai":
            # OpenAI keys start with "sk-"
            return api_key.startswith("sk-") and len(api_key) > 20

        return len(api_key) > 10  # Generic validation

    def get_enabled_providers(self) -> list[ProviderInfo]:
        """Get list of enabled providers."""
        return [p for p in self._providers if p.enabled]

    def get_provider(self, provider_id: str) -> Optional[ProviderInfo]:
        """Get a specific provider by ID."""
        for p in self._providers:
            if p.id == provider_id:
                return p
        return None
