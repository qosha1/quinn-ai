"""Worker detail panel — shows tools, storage, active beads, messages, briefing."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static
from textual.widget import Widget

from ..interfaces.org_connection import WorkerDetail


class WorkerDetailPanel(Widget):
    """Right-side panel showing rich context for the selected worker."""

    DEFAULT_CSS = """
    WorkerDetailPanel {
        width: 40%;
        border: solid $primary;
        padding: 1 2;
        overflow-y: auto;
    }
    WorkerDetailPanel .detail-empty {
        color: $text-muted;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._detail: WorkerDetail | None = None

    def compose(self) -> ComposeResult:
        yield Static("Select a worker to see details", classes="detail-empty", id="detail-content")

    def update_worker(self, detail: WorkerDetail) -> None:
        """Update the panel with new worker detail data."""
        self._detail = detail
        try:
            content = self.query_one("#detail-content", Static)
            content.update(self.render_detail_text(detail))
        except Exception:
            # Widget not yet mounted — detail stored, will render on mount
            pass

    def clear(self) -> None:
        """Clear the panel (no worker selected)."""
        self._detail = None
        content = self.query_one("#detail-content", Static)
        content.update("Select a worker to see details")

    def render_detail_text(self, detail: WorkerDetail) -> str:
        """Render worker detail as plain text for display."""
        lines: list[str] = []

        # Tools
        lines.append("─── CLI Tools ───────────────────────")
        if detail.tools:
            for t in detail.tools:
                desc = f" — {t['description']}" if t.get("description") else ""
                lines.append(f"  {t['name']}{desc}")
        else:
            lines.append("  (none configured)")
        lines.append("")

        # Storage tree
        lines.append("─── Storage ──────────────────────────")
        if detail.storage_tree:
            _render_tree(detail.storage_tree, lines, prefix="  ")
        else:
            lines.append("  (no storage found)")
        lines.append("")

        # Active beads
        lines.append("─── Active Work ──────────────────────")
        if detail.active_beads:
            for b in detail.active_beads:
                status = b.get("status", "")
                title = b.get("title", b.get("id", "?"))
                lines.append(f"  [{status}] {title}")
        else:
            lines.append("  (no active beads)")
        lines.append("")

        # Recent messages
        lines.append("─── Recent Messages ──────────────────")
        if detail.recent_messages:
            for m in detail.recent_messages:
                ts = m.get("ts", "")[:10]
                sender = m.get("sender", "?")
                body = m.get("body", "")[:80]
                lines.append(f"  {ts} {sender}: {body}")
        else:
            lines.append("  (no recent messages)")
        lines.append("")

        # Briefing excerpt
        lines.append("─── Briefing ─────────────────────────")
        if detail.briefing_excerpt:
            for line in detail.briefing_excerpt.splitlines()[:12]:
                lines.append(f"  {line}")
            lines.append("  …")
        else:
            lines.append("  (no briefing)")

        return "\n".join(lines)


def _render_tree(tree: dict, lines: list[str], prefix: str, _depth: int = 0) -> None:
    for name, subtree in tree.items():
        lines.append(f"{prefix}{name}")
        if subtree and _depth < 1:
            _render_tree(subtree, lines, prefix + "  ", _depth + 1)
