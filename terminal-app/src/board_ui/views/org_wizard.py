"""
Org Init Wizard view.

Multi-step wizard for creating a new QuinnAI organization:
1. Name & Path - Basic org configuration
2. AI Services - Configure providers (Anthropic, OpenAI, etc.)
3. OKRs - Set initial objectives and key results
4. CEO Briefing - Compose initial briefing message

The wizard guides users through org setup with friendly language.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal, Center
from textual.widgets import Button, Label, Input, Static, ProgressBar
from textual.widget import Widget
from textual.message import Message

from ..widgets.provider_config import ProviderConfigWidget, ProviderInfo
from ..widgets.okr_editor import OKREditorWidget, Objective
from ..widgets.ceo_briefing import CEOBriefingWidget, BriefingContent


@dataclass
class OrgConfig:
    """Configuration collected from wizard."""

    name: str = ""
    path: Optional[Path] = None
    providers: list[ProviderInfo] = field(default_factory=list)
    objectives: list[Objective] = field(default_factory=list)
    ceo_briefing: Optional[BriefingContent] = None


class OrgInitWizard(Widget):
    """Multi-step wizard for creating a new org."""

    DEFAULT_CSS = """
    OrgInitWizard {
        layout: vertical;
        height: 100%;
    }

    #wizard-header {
        height: 5;
        border-bottom: solid $primary;
        padding: 1 2;
    }

    #wizard-title {
        text-style: bold;
        text-align: center;
    }

    #wizard-progress {
        height: 1;
        margin-top: 1;
    }

    #wizard-content {
        height: 1fr;
        padding: 1 2;
        overflow-y: auto;
    }

    #wizard-footer {
        height: 4;
        border-top: solid $primary;
        padding: 1 2;
        layout: horizontal;
        align: center middle;
    }

    #wizard-footer Button {
        margin: 0 1;
    }

    .step-title {
        text-style: bold;
        margin-bottom: 1;
    }

    .step-description {
        color: $text-muted;
        margin-bottom: 2;
    }

    /* Step 1: Name & Path */
    #step-1 .input-row {
        height: 3;
        margin-bottom: 1;
    }

    #step-1 .input-label {
        width: 15;
    }

    #step-1 Input {
        width: 1fr;
    }

    #step-1 .path-hint {
        color: $text-muted;
        text-style: italic;
        margin-left: 15;
    }
    """

    STEPS = [
        ("Name & Location", "Choose a name and location for your organization"),
        ("AI Services", "Configure which AI providers to use"),
        ("Goals", "Set initial objectives and key results"),
        ("CEO Briefing", "Write the initial briefing for your AI CEO"),
    ]

    class WizardCompleted(Message):
        """Wizard completed with configuration."""

        def __init__(self, config: OrgConfig) -> None:
            super().__init__()
            self.config = config

    class WizardCancelled(Message):
        """Wizard was cancelled."""
        pass

    def __init__(self, default_path: Optional[Path] = None, **kwargs) -> None:
        """Initialize the wizard.

        Args:
            default_path: Default path for new org
        """
        super().__init__(**kwargs)
        self._current_step = 0
        self._config = OrgConfig()
        self._default_path = default_path or Path.home() / "orgs"

    def compose(self) -> ComposeResult:
        # Header with progress
        with Container(id="wizard-header"):
            yield Label("Create New Organization", id="wizard-title")
            yield ProgressBar(
                total=len(self.STEPS),
                show_eta=False,
                id="wizard-progress",
            )

        # Content area - steps are shown/hidden
        with Container(id="wizard-content"):
            yield self._create_step_1()
            yield self._create_step_2()
            yield self._create_step_3()
            yield self._create_step_4()

        # Footer with navigation
        with Container(id="wizard-footer"):
            yield Button("Cancel", id="cancel-btn", variant="default")
            yield Button("Back", id="back-btn", variant="default", disabled=True)
            yield Button("Next", id="next-btn", variant="primary")

    def _create_step_1(self) -> Widget:
        """Create Step 1: Name & Path."""
        return Vertical(
            Label("Step 1: Name & Location", classes="step-title"),
            Label(
                "Choose a memorable name and where to store your org files.",
                classes="step-description",
            ),
            Horizontal(
                Label("Org Name:", classes="input-label"),
                Input(
                    placeholder="my-ai-company",
                    id="org-name-input",
                ),
                classes="input-row",
            ),
            Horizontal(
                Label("Location:", classes="input-label"),
                Input(
                    value=str(self._default_path),
                    placeholder="/path/to/orgs",
                    id="org-path-input",
                ),
                classes="input-row",
            ),
            Label(
                "The org folder will be created at: [location]/[name]",
                classes="path-hint",
                id="path-preview",
            ),
            id="step-1",
        )

    def _create_step_2(self) -> Widget:
        """Create Step 2: Provider Configuration."""
        return Vertical(
            Label("Step 2: AI Services", classes="step-title"),
            Label(
                "Enable the AI services your org will use. You can change this later.",
                classes="step-description",
            ),
            ProviderConfigWidget(id="provider-config"),
            id="step-2",
            classes="hidden",
        )

    def _create_step_3(self) -> Widget:
        """Create Step 3: OKRs."""
        return Vertical(
            Label("Step 3: Set Goals", classes="step-title"),
            Label(
                "Define what your organization should accomplish. Add objectives and measurable key results.",
                classes="step-description",
            ),
            OKREditorWidget(id="okr-editor"),
            id="step-3",
            classes="hidden",
        )

    def _create_step_4(self) -> Widget:
        """Create Step 4: CEO Briefing."""
        return Vertical(
            Label("Step 4: Brief Your CEO", classes="step-title"),
            Label(
                "Write the initial message for your AI CEO. This sets context and expectations.",
                classes="step-description",
            ),
            CEOBriefingWidget(id="ceo-briefing"),
            id="step-4",
            classes="hidden",
        )

    def on_mount(self) -> None:
        """Initialize wizard state."""
        self._update_progress()
        self._show_current_step()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle navigation buttons."""
        if event.button.id == "cancel-btn":
            self.post_message(self.WizardCancelled())
        elif event.button.id == "back-btn":
            self._go_back()
        elif event.button.id == "next-btn":
            self._go_next()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Update path preview when inputs change."""
        if event.input.id in ("org-name-input", "org-path-input"):
            self._update_path_preview()

    def _go_back(self) -> None:
        """Go to previous step."""
        if self._current_step > 0:
            self._save_current_step()
            self._current_step -= 1
            self._show_current_step()
            self._update_progress()
            self._update_buttons()

    def _go_next(self) -> None:
        """Go to next step or finish."""
        if not self._validate_current_step():
            return

        self._save_current_step()

        if self._current_step < len(self.STEPS) - 1:
            self._current_step += 1
            self._show_current_step()
            self._update_progress()
            self._update_buttons()
        else:
            # Wizard complete
            self._finish_wizard()

    def _show_current_step(self) -> None:
        """Show only the current step."""
        for i in range(len(self.STEPS)):
            step = self.query_one(f"#step-{i + 1}")
            if i == self._current_step:
                step.remove_class("hidden")
            else:
                step.add_class("hidden")

    def _update_progress(self) -> None:
        """Update progress bar."""
        progress = self.query_one("#wizard-progress", ProgressBar)
        progress.progress = self._current_step + 1

        # Update title with current step
        title = self.query_one("#wizard-title", Label)
        step_name, _ = self.STEPS[self._current_step]
        title.update(f"Create New Organization - {step_name}")

    def _update_buttons(self) -> None:
        """Update button states."""
        back_btn = self.query_one("#back-btn", Button)
        next_btn = self.query_one("#next-btn", Button)

        back_btn.disabled = self._current_step == 0

        if self._current_step == len(self.STEPS) - 1:
            next_btn.label = "Create Org"
            next_btn.variant = "success"
        else:
            next_btn.label = "Next"
            next_btn.variant = "primary"

    def _update_path_preview(self) -> None:
        """Update the path preview label."""
        try:
            name_input = self.query_one("#org-name-input", Input)
            path_input = self.query_one("#org-path-input", Input)
            preview = self.query_one("#path-preview", Label)

            name = name_input.value.strip() or "[name]"
            base_path = path_input.value.strip() or "[location]"

            full_path = Path(base_path) / name
            preview.update(f"Org will be created at: {full_path}")
        except Exception:
            pass

    def _validate_current_step(self) -> bool:
        """Validate current step before proceeding."""
        if self._current_step == 0:
            # Validate name and path
            name_input = self.query_one("#org-name-input", Input)
            path_input = self.query_one("#org-path-input", Input)

            name = name_input.value.strip()
            if not name:
                self.notify("Please enter an org name", severity="error")
                return False

            if not name.replace("-", "").replace("_", "").isalnum():
                self.notify(
                    "Org name should only contain letters, numbers, hyphens, and underscores",
                    severity="error",
                )
                return False

            path = path_input.value.strip()
            if not path:
                self.notify("Please enter a location", severity="error")
                return False

            return True

        # Other steps are optional
        return True

    def _save_current_step(self) -> None:
        """Save data from current step."""
        if self._current_step == 0:
            name_input = self.query_one("#org-name-input", Input)
            path_input = self.query_one("#org-path-input", Input)
            self._config.name = name_input.value.strip()
            self._config.path = Path(path_input.value.strip()) / self._config.name

        elif self._current_step == 1:
            provider_widget = self.query_one("#provider-config", ProviderConfigWidget)
            self._config.providers = provider_widget.get_enabled_providers()

        elif self._current_step == 2:
            okr_widget = self.query_one("#okr-editor", OKREditorWidget)
            self._config.objectives = okr_widget.get_objectives()

        elif self._current_step == 3:
            briefing_widget = self.query_one("#ceo-briefing", CEOBriefingWidget)
            self._config.ceo_briefing = briefing_widget.get_content()

    def _finish_wizard(self) -> None:
        """Complete the wizard and post configuration."""
        self._save_current_step()
        self.post_message(self.WizardCompleted(self._config))

    def get_config(self) -> OrgConfig:
        """Get the current configuration."""
        return self._config
