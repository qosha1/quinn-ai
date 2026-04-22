"""
Settings view - provider configuration interface.

Shows:
- Current default provider
- List of available providers with capabilities
- Ability to change default provider
- Test connectivity for providers
- Worker-specific provider overrides (future)
"""

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal, VerticalScroll
from textual.widgets import Button, Label, Static, Select
from textual.widget import Widget
from textual.message import Message


class ProviderChangeRequested(Message):
    """Posted when user wants to change the default provider."""

    def __init__(self, provider_name: str) -> None:
        self.provider_name = provider_name
        super().__init__()


class ProviderTestRequested(Message):
    """Posted when user wants to test a provider."""

    def __init__(self, provider_name: str) -> None:
        self.provider_name = provider_name
        super().__init__()


class SettingsView(VerticalScroll):
    """Settings view for provider configuration."""

    DEFAULT_CSS = """
    SettingsView {
        height: 100%;
        padding: 1 2;
    }

    #settings-header {
        height: auto;
        margin-bottom: 1;
    }

    .section {
        border: solid $primary;
        padding: 1 2;
        margin-bottom: 1;
        height: auto;
    }

    .section-title {
        text-style: bold;
        color: $text;
        margin-bottom: 1;
    }

    .provider-row {
        height: auto;
        margin-bottom: 1;
    }

    .provider-name {
        width: 20;
    }

    .provider-capabilities {
        width: 1fr;
        color: $text-muted;
    }

    .provider-enabled {
        color: $success;
    }

    .provider-disabled {
        color: $error;
    }

    #default-provider-row {
        height: auto;
        margin-bottom: 1;
    }

    #change-provider-btn {
        margin-left: 2;
    }

    #provider-select {
        width: 30;
        margin-top: 1;
    }

    .hidden {
        display: none;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._current_default: Optional[str] = None
        self._providers: dict[str, dict] = {}
        self._show_provider_select = False

    def compose(self) -> ComposeResult:
        # Header
        with Container(id="settings-header"):
            yield Label("Settings", classes="panel-title")
            yield Label("Configure provider settings for the organization", classes="metric-label")

        # Default Provider Section
        with Container(classes="section", id="default-provider-section"):
            yield Label("Default Provider", classes="section-title")
            with Horizontal(id="default-provider-row"):
                yield Label("Current:", classes="metric-label")
                yield Label("--", id="current-default-label")
                yield Button("Change", id="change-provider-btn", variant="primary")

            # Provider select (initially hidden)
            yield Select(
                options=[],
                id="provider-select",
                classes="hidden",
                prompt="Select provider..."
            )

        # Available Providers Section
        with Container(classes="section", id="providers-section"):
            yield Label("Available Providers", classes="section-title")
            yield Container(id="providers-list")

        # Save/Refresh Section
        with Horizontal(id="actions-row"):
            yield Button("Refresh", id="refresh-btn", variant="default")

    async def on_mount(self) -> None:
        """Initialize the view."""
        await self.refresh_settings()

    async def refresh_settings(self) -> None:
        """Refresh provider settings from the org connection."""
        try:
            # Get org connection from app
            app = self.app
            if not hasattr(app, 'org_connection') or not app.org_connection:
                self.notify("Not connected to org", severity="error")
                return

            org_connection = app.org_connection

            # Fetch provider configuration
            result = await self._fetch_provider_config(org_connection)
            if result:
                self._current_default = result["default"]
                self._providers = result["providers"]
                self._update_ui()
        except Exception as e:
            self.notify(f"Failed to load settings: {e}", severity="error")

    async def _fetch_provider_config(self, org_connection) -> Optional[dict]:
        """Fetch provider configuration from org."""
        import subprocess
        import yaml
        from pathlib import Path

        try:
            org_path = org_connection.org_path

            # Read providers.yaml
            config_path = org_path / "config" / "providers.yaml"
            if not config_path.exists():
                return None

            with open(config_path) as f:
                config = yaml.safe_load(f) or {}

            default_provider = config.get("default", "claude_code")

            # Get available providers from CLI registry
            result = subprocess.run(
                ["qn", "--org-path", str(org_path), "org", "provider", "list"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                return None

            # Parse provider list output
            providers = self._parse_provider_list(result.stdout)

            return {
                "default": default_provider,
                "providers": providers,
            }

        except Exception as e:
            self.log(f"Error fetching provider config: {e}")
            return None

    def _parse_provider_list(self, output: str) -> dict[str, dict]:
        """Parse output from 'qn org provider list' command."""
        providers = {}
        current_provider = None

        for line in output.split("\n"):
            line = line.strip()
            if not line or line.startswith("Available") or line.startswith("Total"):
                continue

            # Provider name (no leading spaces)
            if line and not line.startswith(" "):
                current_provider = line
                providers[current_provider] = {
                    "enabled": True,
                    "capabilities": [],
                    "aliases": [],
                }
            # Indented lines are metadata
            elif current_provider and line.startswith(" "):
                if "Aliases:" in line:
                    aliases_str = line.split("Aliases:", 1)[1].strip()
                    providers[current_provider]["aliases"] = [
                        a.strip() for a in aliases_str.split(",")
                    ]
                elif "Capabilities:" in line:
                    caps_str = line.split("Capabilities:", 1)[1].strip()
                    providers[current_provider]["capabilities"] = [
                        c.strip() for c in caps_str.split(",")
                    ]

        return providers

    def _update_ui(self) -> None:
        """Update UI with current settings."""
        # Update current default label
        default_label = self.query_one("#current-default-label", Label)
        default_label.update(self._current_default or "(not set)")

        # Update providers list
        providers_list = self.query_one("#providers-list", Container)
        providers_list.remove_children()

        for name, info in sorted(self._providers.items()):
            # Create provider row
            provider_row = Horizontal(classes="provider-row")

            # Provider name
            name_label = Label(
                name,
                classes="provider-name provider-enabled" if info["enabled"] else "provider-name provider-disabled"
            )
            provider_row.compose_add_child(name_label)

            # Capabilities
            caps_str = ", ".join(info.get("capabilities", [])[:5])  # Show first 5
            if len(info.get("capabilities", [])) > 5:
                caps_str += "..."
            caps_label = Label(caps_str, classes="provider-capabilities")
            provider_row.compose_add_child(caps_label)

            providers_list.mount(provider_row)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        if button_id == "change-provider-btn":
            await self._show_provider_selector()
        elif button_id == "refresh-btn":
            await self.refresh_settings()
            self.notify("Settings refreshed")

    async def _show_provider_selector(self) -> None:
        """Show provider selection dropdown."""
        # Build options from providers
        options = [(name, name) for name in sorted(self._providers.keys())]

        # Update select widget
        select = self.query_one("#provider-select", Select)
        select.set_options(options)
        select.remove_class("hidden")
        select.focus()

    async def on_select_changed(self, event: Select.Changed) -> None:
        """Handle provider selection."""
        if event.select.id == "provider-select":
            new_provider = str(event.value)
            if new_provider and new_provider != self._current_default:
                await self._change_default_provider(new_provider)

    async def _change_default_provider(self, provider_name: str) -> None:
        """Change the default provider."""
        try:
            # Get org connection
            app = self.app
            if not hasattr(app, 'org_connection') or not app.org_connection:
                self.notify("Not connected to org", severity="error")
                return

            org_connection = app.org_connection
            org_path = org_connection.org_path

            # Call CLI command to set default
            import subprocess
            result = subprocess.run(
                ["qn", "--org-path", str(org_path), "org", "provider", "default", provider_name],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                self._current_default = provider_name
                self.notify(f"Default provider set to {provider_name}", severity="information")

                # Hide select and refresh UI
                select = self.query_one("#provider-select", Select)
                select.add_class("hidden")
                self._update_ui()
            else:
                error_msg = result.stderr.strip() or "Unknown error"
                self.notify(f"Failed to set provider: {error_msg}", severity="error")

        except Exception as e:
            self.notify(f"Error changing provider: {e}", severity="error")

    def export_as_text(self) -> str:
        """Export settings view content as plain text.

        Returns:
            Formatted text representation of settings
        """
        lines = []
        lines.append("=" * 60)
        lines.append("QUINNAI BOARD - SETTINGS")
        lines.append("=" * 60)
        lines.append("")

        # Default provider
        lines.append("Default Provider:")
        lines.append(f"  {self._current_default or '(not set)'}")
        lines.append("")

        # Available providers
        if not self._providers:
            lines.append("No providers configured")
        else:
            lines.append(f"Available Providers ({len(self._providers)}):")
            lines.append("")

            for name, info in sorted(self._providers.items()):
                lines.append(f"  {name}:")
                lines.append(f"    Status: {'Enabled' if info['enabled'] else 'Disabled'}")

                if info.get("aliases"):
                    aliases_str = ", ".join(info["aliases"])
                    lines.append(f"    Aliases: {aliases_str}")

                if info.get("capabilities"):
                    caps_str = ", ".join(info["capabilities"])
                    lines.append(f"    Capabilities: {caps_str}")

                lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)
