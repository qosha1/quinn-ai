"""Modal screens for team-view worker actions (quinn-ai-6hn).

Three small modals:
- HireWorkerModal: form for name/role/manager. Returns dict on submit, None on cancel.
- WorkerActionsModal: pick from Fire/Promote/Demote for a worker. Returns one of those strings, or None.
- ConfirmFireModal: yes/no confirmation. Returns True on confirm, False/None on cancel.

Each is awaited via `await self.app.push_screen_wait(modal)` from the caller.
"""

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static


class HireWorkerModal(ModalScreen[Optional[dict]]):
    """Form modal that collects (name, role, manager) for `qn org hire`.

    Returns a dict with those keys on submit, or None on cancel.
    """

    DEFAULT_CSS = """
    HireWorkerModal {
        align: center middle;
    }
    HireWorkerModal > Container {
        width: 60;
        height: auto;
        padding: 1 2;
        border: round $accent;
        background: $panel;
    }
    HireWorkerModal #hire-title {
        text-style: bold;
        margin-bottom: 1;
    }
    HireWorkerModal Input {
        margin-bottom: 1;
    }
    HireWorkerModal #hire-buttons {
        height: 3;
        margin-top: 1;
        align: right middle;
    }
    HireWorkerModal Button {
        margin-left: 1;
    }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, default_manager: str = "ceo") -> None:
        super().__init__()
        self._default_manager = default_manager

    def compose(self) -> ComposeResult:
        with Container():
            yield Label("Hire worker", id="hire-title")
            yield Input(placeholder="Name (e.g. Alice)", id="hire-name")
            yield Input(placeholder="Role (e.g. Engineer)", id="hire-role")
            yield Input(
                value=self._default_manager,
                placeholder="Manager (name, role, or wrkr-id; default: ceo)",
                id="hire-manager",
            )
            with Horizontal(id="hire-buttons"):
                yield Button("Cancel", id="hire-cancel")
                yield Button("Hire", id="hire-submit", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "hire-submit":
            name = self.query_one("#hire-name", Input).value.strip()
            role = self.query_one("#hire-role", Input).value.strip()
            manager = self.query_one("#hire-manager", Input).value.strip() or self._default_manager
            if not name or not role:
                self.app.notify("Name and role are required", severity="warning")
                return
            self.dismiss({"name": name, "role": role, "manager": manager})
        elif event.button.id == "hire-cancel":
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class WorkerActionsModal(ModalScreen[Optional[str]]):
    """Action picker for a worker. Returns one of 'fire', 'promote', 'demote', or None.

    The caller passes a list of allowed actions (some workers can't be demoted, etc.)
    and only those buttons are shown.
    """

    DEFAULT_CSS = """
    WorkerActionsModal {
        align: center middle;
    }
    WorkerActionsModal > Container {
        width: 50;
        height: auto;
        padding: 1 2;
        border: round $accent;
        background: $panel;
    }
    WorkerActionsModal #actions-title {
        text-style: bold;
        margin-bottom: 1;
    }
    WorkerActionsModal #actions-buttons {
        height: 3;
        margin-top: 1;
        align: center middle;
    }
    WorkerActionsModal Button {
        margin: 0 1;
    }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, worker_name: str, actions: list[str]) -> None:
        super().__init__()
        self._worker_name = worker_name
        self._actions = actions

    def compose(self) -> ComposeResult:
        with Container():
            yield Label(f"Actions for {self._worker_name}", id="actions-title")
            with Horizontal(id="actions-buttons"):
                for action in self._actions:
                    variant = "error" if action == "fire" else "primary"
                    yield Button(action.title(), id=f"act-{action}", variant=variant)
                yield Button("Cancel", id="act-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "act-cancel":
            self.dismiss(None)
            return
        if bid.startswith("act-"):
            self.dismiss(bid[len("act-"):])

    def action_cancel(self) -> None:
        self.dismiss(None)


class ConfirmFireModal(ModalScreen[bool]):
    """Yes/no confirmation before firing a worker. Returns True on confirm, False on cancel."""

    DEFAULT_CSS = """
    ConfirmFireModal {
        align: center middle;
    }
    ConfirmFireModal > Container {
        width: 60;
        height: auto;
        padding: 1 2;
        border: round $error;
        background: $panel;
    }
    ConfirmFireModal #confirm-title {
        text-style: bold;
        color: $error;
        margin-bottom: 1;
    }
    ConfirmFireModal #confirm-body {
        margin-bottom: 1;
    }
    ConfirmFireModal #confirm-buttons {
        height: 3;
        margin-top: 1;
        align: right middle;
    }
    ConfirmFireModal Button {
        margin-left: 1;
    }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, worker_name: str) -> None:
        super().__init__()
        self._worker_name = worker_name

    def compose(self) -> ComposeResult:
        with Container():
            yield Label("Fire worker?", id="confirm-title")
            yield Static(
                f"This will terminate {self._worker_name}'s session and mark "
                f"the worker as terminated. This action cannot be undone.",
                id="confirm-body",
            )
            with Horizontal(id="confirm-buttons"):
                yield Button("Cancel", id="confirm-cancel")
                yield Button("Fire", id="confirm-yes", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-yes":
            self.dismiss(True)
        elif event.button.id == "confirm-cancel":
            self.dismiss(False)

    def action_cancel(self) -> None:
        self.dismiss(False)
