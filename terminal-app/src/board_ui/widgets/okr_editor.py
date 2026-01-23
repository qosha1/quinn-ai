"""
OKR Editor Widget.

Allows creating and editing OKRs with objectives and measurable key results.
Key results must be calculable (number, percentage, yes/no) - rejects subjective KRs.
"""

import re
from dataclasses import dataclass, field
from typing import Optional
from uuid import uuid4

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, ScrollableContainer
from textual.widgets import Static, Input, Button, Label, Select
from textual.widget import Widget
from textual.message import Message


@dataclass
class KeyResult:
    """A measurable key result."""

    id: str = field(default_factory=lambda: str(uuid4())[:8])
    metric: str = ""
    target: float = 0
    current: float = 0
    unit: str = ""  # "count", "percent", "boolean", "currency"

    @property
    def progress(self) -> float:
        """Calculate progress as percentage."""
        if self.unit == "boolean":
            return 100.0 if self.current >= 1 else 0.0
        if self.target == 0:
            return 0.0
        return min(100.0, (self.current / self.target) * 100)


@dataclass
class Objective:
    """An objective with key results."""

    id: str = field(default_factory=lambda: str(uuid4())[:8])
    title: str = ""
    key_results: list[KeyResult] = field(default_factory=list)


# Common objective templates
OBJECTIVE_TEMPLATES = [
    Objective(
        title="Increase Revenue",
        key_results=[
            KeyResult(metric="Monthly recurring revenue", target=100000, unit="currency"),
            KeyResult(metric="New customers acquired", target=50, unit="count"),
        ],
    ),
    Objective(
        title="Improve Product Quality",
        key_results=[
            KeyResult(metric="Bug count reduced", target=10, unit="count"),
            KeyResult(metric="Test coverage", target=80, unit="percent"),
        ],
    ),
    Objective(
        title="Enhance Customer Satisfaction",
        key_results=[
            KeyResult(metric="NPS score", target=50, unit="count"),
            KeyResult(metric="Support ticket resolution time (hours)", target=4, unit="count"),
        ],
    ),
    Objective(
        title="Launch New Feature",
        key_results=[
            KeyResult(metric="Feature shipped", target=1, unit="boolean"),
            KeyResult(metric="User adoption rate", target=25, unit="percent"),
        ],
    ),
]

# Subjective phrases to reject
SUBJECTIVE_PATTERNS = [
    r"\bimprove\b",
    r"\bbetter\b",
    r"\benhance\b",
    r"\bincrease\s+quality\b",
    r"\bmore\s+efficient\b",
    r"\bstronger\b",
    r"\bfaster\b",
    r"\beasier\b",
]


class OKREditorWidget(Widget):
    """Widget for creating and editing OKRs.

    Enforces measurable key results - rejects subjective language.
    """

    DEFAULT_CSS = """
    OKREditorWidget {
        height: auto;
        padding: 1;
    }

    OKREditorWidget .editor-header {
        text-style: bold;
        margin-bottom: 1;
    }

    OKREditorWidget .objective-card {
        border: solid $primary;
        padding: 1;
        margin-bottom: 1;
        height: auto;
    }

    OKREditorWidget .objective-title-row {
        height: 3;
        margin-bottom: 1;
    }

    OKREditorWidget .objective-title-input {
        width: 1fr;
    }

    OKREditorWidget .kr-section {
        margin-left: 2;
        height: auto;
    }

    OKREditorWidget .kr-row {
        height: 3;
        margin-bottom: 1;
    }

    OKREditorWidget .kr-metric-input {
        width: 2fr;
    }

    OKREditorWidget .kr-target-input {
        width: 10;
    }

    OKREditorWidget .kr-unit-select {
        width: 15;
    }

    OKREditorWidget .validation-error {
        color: $error;
        margin-top: 1;
    }

    OKREditorWidget .add-button {
        margin-top: 1;
    }

    OKREditorWidget .template-section {
        margin-bottom: 1;
    }
    """

    class ObjectiveAdded(Message):
        """Message sent when an objective is added."""

        def __init__(self, objective: Objective) -> None:
            self.objective = objective
            super().__init__()

    class KeyResultAdded(Message):
        """Message sent when a key result is added."""

        def __init__(self, objective_id: str, key_result: KeyResult) -> None:
            self.objective_id = objective_id
            self.key_result = key_result
            super().__init__()

    class ValidationError(Message):
        """Message sent when validation fails."""

        def __init__(self, message: str) -> None:
            self.message = message
            super().__init__()

    def __init__(
        self,
        objectives: Optional[list[Objective]] = None,
        id: Optional[str] = None,
    ) -> None:
        """Initialize the OKR editor.

        Args:
            objectives: Initial objectives to display.
            id: Widget ID.
        """
        super().__init__(id=id)
        self._objectives = objectives or []
        self._validation_error: Optional[str] = None

    def compose(self) -> ComposeResult:
        """Compose the OKR editor UI."""
        yield Static("OKR Editor", classes="editor-header", id="okr-header")

        # Template selection
        with Horizontal(classes="template-section"):
            yield Label("Start from template:")
            yield Select(
                [(t.title, i) for i, t in enumerate(OBJECTIVE_TEMPLATES)],
                prompt="Select template...",
                id="template-select",
            )

        # Objectives container
        with ScrollableContainer(id="objectives-container"):
            for obj in self._objectives:
                yield self._create_objective_card(obj)

        # Add objective button
        yield Button("+ Add Objective", id="add-objective-btn", classes="add-button")

        # Validation error display
        yield Static("", id="validation-error", classes="validation-error")

    def _create_objective_card(self, objective: Objective) -> Widget:
        """Create a card for a single objective."""
        kr_widgets = []
        for kr in objective.key_results:
            kr_widgets.append(self._create_kr_row(objective.id, kr))

        return Vertical(
            Horizontal(
                Input(
                    value=objective.title,
                    placeholder="Objective title...",
                    id=f"obj-title-{objective.id}",
                    classes="objective-title-input",
                ),
                Button("Move Up", id=f"move-up-{objective.id}"),
                Button("Move Down", id=f"move-down-{objective.id}"),
                Button("Delete", id=f"delete-obj-{objective.id}"),
                classes="objective-title-row",
            ),
            Vertical(
                Static("Key Results:", classes="kr-header"),
                *kr_widgets,
                Button(
                    "+ Add Key Result",
                    id=f"add-kr-{objective.id}",
                    classes="add-button",
                ),
                classes="kr-section",
            ),
            classes="objective-card",
            id=f"obj-card-{objective.id}",
        )

    def _create_kr_row(self, objective_id: str, kr: KeyResult) -> Widget:
        """Create a row for a single key result."""
        return Horizontal(
            Input(
                value=kr.metric,
                placeholder="Measurable metric...",
                id=f"kr-metric-{kr.id}",
                classes="kr-metric-input",
            ),
            Input(
                value=str(kr.target) if kr.target else "",
                placeholder="Target",
                id=f"kr-target-{kr.id}",
                classes="kr-target-input",
            ),
            Select(
                [
                    ("Count", "count"),
                    ("Percent", "percent"),
                    ("Yes/No", "boolean"),
                    ("Currency", "currency"),
                ],
                value=kr.unit or "count",
                id=f"kr-unit-{kr.id}",
                classes="kr-unit-select",
            ),
            Button("X", id=f"delete-kr-{kr.id}"),
            classes="kr-row",
            id=f"kr-row-{kr.id}",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id
        if not button_id:
            return

        if button_id == "add-objective-btn":
            self._add_objective()
        elif button_id.startswith("add-kr-"):
            obj_id = button_id.replace("add-kr-", "")
            self._add_key_result(obj_id)
        elif button_id.startswith("delete-obj-"):
            obj_id = button_id.replace("delete-obj-", "")
            self._delete_objective(obj_id)
        elif button_id.startswith("delete-kr-"):
            kr_id = button_id.replace("delete-kr-", "")
            self._delete_key_result(kr_id)
        elif button_id.startswith("move-up-"):
            obj_id = button_id.replace("move-up-", "")
            self._reorder_objective(obj_id, -1)
        elif button_id.startswith("move-down-"):
            obj_id = button_id.replace("move-down-", "")
            self._reorder_objective(obj_id, 1)

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle select changes."""
        select_id = event.select.id
        if select_id == "template-select" and event.value is not None:
            template_idx = event.value
            self._apply_template(template_idx)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes and validate."""
        input_id = event.input.id
        if not input_id:
            return

        if input_id.startswith("kr-metric-"):
            # Validate key result metric
            error = self._validate_kr_metric(event.value)
            self._show_validation_error(error)

    def _add_objective(self) -> None:
        """Add a new empty objective."""
        obj = Objective()
        self._objectives.append(obj)

        # Add card to UI
        container = self.query_one("#objectives-container", ScrollableContainer)
        card = self._create_objective_card(obj)
        container.mount(card)

        self.post_message(self.ObjectiveAdded(obj))

    def _add_key_result(self, objective_id: str) -> None:
        """Add a key result to an objective."""
        for obj in self._objectives:
            if obj.id == objective_id:
                kr = KeyResult()
                obj.key_results.append(kr)

                # Add row to UI
                kr_section = self.query_one(f"#obj-card-{objective_id} .kr-section", Vertical)
                add_btn = self.query_one(f"#add-kr-{objective_id}", Button)
                kr_row = self._create_kr_row(objective_id, kr)
                kr_section.mount(kr_row, before=add_btn)

                self.post_message(self.KeyResultAdded(objective_id, kr))
                break

    def _delete_objective(self, objective_id: str) -> None:
        """Delete an objective."""
        self._objectives = [o for o in self._objectives if o.id != objective_id]

        # Remove from UI
        try:
            card = self.query_one(f"#obj-card-{objective_id}", Vertical)
            card.remove()
        except Exception:
            pass

    def _delete_key_result(self, kr_id: str) -> None:
        """Delete a key result."""
        for obj in self._objectives:
            obj.key_results = [kr for kr in obj.key_results if kr.id != kr_id]

        # Remove from UI
        try:
            row = self.query_one(f"#kr-row-{kr_id}", Horizontal)
            row.remove()
        except Exception:
            pass

    def _reorder_objective(self, objective_id: str, direction: int) -> None:
        """Move an objective up or down in the list."""
        for i, obj in enumerate(self._objectives):
            if obj.id == objective_id:
                new_idx = i + direction
                if 0 <= new_idx < len(self._objectives):
                    self._objectives[i], self._objectives[new_idx] = (
                        self._objectives[new_idx],
                        self._objectives[i],
                    )
                    self._refresh_objectives_ui()
                break

    def _refresh_objectives_ui(self) -> None:
        """Refresh the objectives display."""
        container = self.query_one("#objectives-container", ScrollableContainer)
        container.remove_children()
        for obj in self._objectives:
            container.mount(self._create_objective_card(obj))

    def _apply_template(self, template_idx: int) -> None:
        """Apply a template to create new objectives."""
        if 0 <= template_idx < len(OBJECTIVE_TEMPLATES):
            template = OBJECTIVE_TEMPLATES[template_idx]
            # Create a copy of the template
            obj = Objective(
                title=template.title,
                key_results=[
                    KeyResult(
                        metric=kr.metric,
                        target=kr.target,
                        unit=kr.unit,
                    )
                    for kr in template.key_results
                ],
            )
            self._objectives.append(obj)

            # Add to UI
            container = self.query_one("#objectives-container", ScrollableContainer)
            container.mount(self._create_objective_card(obj))

            self.post_message(self.ObjectiveAdded(obj))

    def _validate_kr_metric(self, metric: str) -> Optional[str]:
        """Validate a key result metric is measurable, not subjective.

        Args:
            metric: The metric description to validate.

        Returns:
            Error message if invalid, None if valid.
        """
        if not metric:
            return None

        metric_lower = metric.lower()
        for pattern in SUBJECTIVE_PATTERNS:
            if re.search(pattern, metric_lower):
                return f"Key results must be measurable. '{metric}' contains subjective language. Use specific numbers instead."

        return None

    def _show_validation_error(self, error: Optional[str]) -> None:
        """Show or hide validation error."""
        self._validation_error = error
        error_widget = self.query_one("#validation-error", Static)
        error_widget.update(error or "")

        if error:
            self.post_message(self.ValidationError(error))

    def get_objectives(self) -> list[Objective]:
        """Get all objectives."""
        return self._objectives

    def get_templates(self) -> list[Objective]:
        """Get available templates."""
        return OBJECTIVE_TEMPLATES
