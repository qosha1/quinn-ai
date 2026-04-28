"""
CEO Briefing Composer Widget.

Allows composing structured briefing messages for the CEO with sections:
- Context: Background information
- Requirements: What needs to be accomplished
- Constraints: Limitations and boundaries
- Success Criteria: How success is measured

Supports markdown editing with preview and templates.
"""

from dataclasses import dataclass, field
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, ScrollableContainer
from textual.widgets import Static, TextArea, Button, Label, Select, TabbedContent, TabPane
from textual.widget import Widget
from textual.message import Message


@dataclass
class BriefingContent:
    """Content of a CEO briefing."""

    context: str = ""
    requirements: str = ""
    constraints: str = ""
    success_criteria: str = ""

    def to_markdown(self) -> str:
        """Convert briefing to markdown format."""
        sections = []

        if self.context:
            sections.append(f"## Context\n\n{self.context}")

        if self.requirements:
            sections.append(f"## Requirements\n\n{self.requirements}")

        if self.constraints:
            sections.append(f"## Constraints\n\n{self.constraints}")

        if self.success_criteria:
            sections.append(f"## Success Criteria\n\n{self.success_criteria}")

        return "\n\n".join(sections)

    @classmethod
    def from_markdown(cls, markdown: str) -> "BriefingContent":
        """Parse briefing from markdown."""
        content = cls()
        current_section = None
        current_text = []

        for line in markdown.split("\n"):
            if line.startswith("## Context"):
                if current_section and current_text:
                    setattr(content, current_section, "\n".join(current_text).strip())
                current_section = "context"
                current_text = []
            elif line.startswith("## Requirements"):
                if current_section and current_text:
                    setattr(content, current_section, "\n".join(current_text).strip())
                current_section = "requirements"
                current_text = []
            elif line.startswith("## Constraints"):
                if current_section and current_text:
                    setattr(content, current_section, "\n".join(current_text).strip())
                current_section = "constraints"
                current_text = []
            elif line.startswith("## Success Criteria"):
                if current_section and current_text:
                    setattr(content, current_section, "\n".join(current_text).strip())
                current_section = "success_criteria"
                current_text = []
            elif current_section:
                current_text.append(line)

        if current_section and current_text:
            setattr(content, current_section, "\n".join(current_text).strip())

        return content


# Briefing templates for common org types
BRIEFING_TEMPLATES = {
    "software_dev": BriefingContent(
        context="""We are building [PROJECT NAME], a [DESCRIPTION].

Target users: [WHO]
Tech stack: [TECHNOLOGIES]
Timeline: [DEADLINE]""",
        requirements="""1. Implement core functionality for [FEATURE]
2. Ensure code quality with tests
3. Deploy to [ENVIRONMENT]
4. Document the implementation""",
        constraints="""- Budget: $[AMOUNT] for compute costs
- No external services beyond [APPROVED LIST]
- Must be compatible with [SYSTEMS]
- Follow security best practices""",
        success_criteria="""- All tests passing
- Feature deployed and accessible
- Documentation complete
- Performance meets [METRICS]""",
    ),
    "research": BriefingContent(
        context="""Research topic: [TOPIC]

Background: [WHAT WE KNOW]
Gap: [WHAT WE DON'T KNOW]""",
        requirements="""1. Survey existing literature
2. Identify key insights
3. Synthesize findings
4. Recommend next steps""",
        constraints="""- Focus on [SPECIFIC AREA]
- Time limit: [HOURS]
- Sources: [TYPES OF SOURCES]""",
        success_criteria="""- Comprehensive literature review
- Clear summary of findings
- Actionable recommendations
- All sources cited""",
    ),
    "content_creation": BriefingContent(
        context="""Content type: [BLOG/DOCS/MARKETING]

Audience: [TARGET AUDIENCE]
Tone: [FORMAL/CASUAL/TECHNICAL]
Purpose: [EDUCATE/PERSUADE/INFORM]""",
        requirements="""1. Research topic thoroughly
2. Create outline
3. Write draft
4. Edit and polish""",
        constraints="""- Word count: [MIN]-[MAX]
- Style guide: [REFERENCE]
- Deadline: [DATE]""",
        success_criteria="""- Meets word count requirements
- Follows style guide
- Approved by [REVIEWER]
- Published on time""",
    ),
    "data_analysis": BriefingContent(
        context="""Dataset: [DESCRIPTION]

Question: [WHAT WE WANT TO LEARN]
Stakeholders: [WHO NEEDS THIS]""",
        requirements="""1. Clean and validate data
2. Perform exploratory analysis
3. Run statistical tests
4. Create visualizations
5. Write report""",
        constraints="""- Tools: [APPROVED TOOLS]
- Privacy: [DATA HANDLING RULES]
- Timeline: [DEADLINE]""",
        success_criteria="""- Data quality validated
- Key insights identified
- Visualizations clear
- Report delivered""",
    ),
}


class CEOBriefingWidget(Widget):
    """Widget for composing CEO briefing messages.

    Provides structured sections with markdown editing and preview.
    """

    DEFAULT_CSS = """
    CEOBriefingWidget {
        height: auto;
        padding: 1;
    }

    CEOBriefingWidget .briefing-header {
        text-style: bold;
        margin-bottom: 1;
    }

    CEOBriefingWidget .template-row {
        height: 3;
        margin-bottom: 1;
    }

    CEOBriefingWidget .section-container {
        height: auto;
        margin-bottom: 1;
    }

    CEOBriefingWidget .section-label {
        text-style: bold;
        margin-bottom: 1;
    }

    CEOBriefingWidget .section-editor {
        height: 8;
        border: solid $primary;
    }

    CEOBriefingWidget .preview-container {
        border: solid $surface;
        padding: 1;
        height: auto;
        min-height: 10;
    }

    CEOBriefingWidget .button-row {
        height: 3;
        margin-top: 1;
    }

    CEOBriefingWidget .preview-content {
        height: auto;
    }
    """

    class BriefingSaved(Message):
        """Message sent when briefing is saved."""

        def __init__(self, content: BriefingContent, markdown: str) -> None:
            self.content = content
            self.markdown = markdown
            super().__init__()

    class BriefingQueued(Message):
        """Message sent when briefing is queued for CEO."""

        def __init__(self, content: BriefingContent) -> None:
            self.content = content
            super().__init__()

    def __init__(
        self,
        initial_content: Optional[BriefingContent] = None,
        id: Optional[str] = None,
    ) -> None:
        """Initialize the briefing widget.

        Args:
            initial_content: Initial briefing content.
            id: Widget ID.
        """
        super().__init__(id=id)
        self._content = initial_content or BriefingContent()

    def compose(self) -> ComposeResult:
        """Compose the briefing editor UI."""
        yield Static("CEO Briefing Composer", classes="briefing-header", id="briefing-header")

        # Template selector
        with Horizontal(classes="template-row"):
            yield Label("Load template:")
            yield Select(
                [(name.replace("_", " ").title(), name) for name in BRIEFING_TEMPLATES.keys()],
                prompt="Select template...",
                id="template-select",
            )

        # Tabbed interface for edit/preview
        with TabbedContent(id="briefing-tabs"):
            with TabPane("Edit", id="edit-tab"):
                yield self._create_edit_sections()

            with TabPane("Preview", id="preview-tab"):
                yield ScrollableContainer(
                    Static("", id="preview-content", classes="preview-content"),
                    classes="preview-container",
                )

        # Action buttons
        with Horizontal(classes="button-row"):
            yield Button("Save Draft", id="save-btn")
            yield Button("Queue for CEO", id="queue-btn", variant="primary")

    def _create_edit_sections(self) -> Widget:
        """Create the editing sections."""
        return Vertical(
            # Context section
            Vertical(
                Static("Context", classes="section-label", id="context-label"),
                TextArea(
                    self._content.context,
                    id="context-editor",
                    classes="section-editor",
                ),
                classes="section-container",
                id="context-section",
            ),
            # Requirements section
            Vertical(
                Static("Requirements", classes="section-label", id="requirements-label"),
                TextArea(
                    self._content.requirements,
                    id="requirements-editor",
                    classes="section-editor",
                ),
                classes="section-container",
                id="requirements-section",
            ),
            # Constraints section
            Vertical(
                Static("Constraints", classes="section-label", id="constraints-label"),
                TextArea(
                    self._content.constraints,
                    id="constraints-editor",
                    classes="section-editor",
                ),
                classes="section-container",
                id="constraints-section",
            ),
            # Success Criteria section
            Vertical(
                Static("Success Criteria", classes="section-label", id="success-criteria-label"),
                TextArea(
                    self._content.success_criteria,
                    id="success-criteria-editor",
                    classes="section-editor",
                ),
                classes="section-container",
                id="success-criteria-section",
            ),
            id="edit-sections",
        )

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle template selection."""
        if event.select.id == "template-select" and event.value:
            template_name = event.value
            if template_name in BRIEFING_TEMPLATES:
                template = BRIEFING_TEMPLATES[template_name]
                self._apply_template(template)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        if button_id == "save-btn":
            self._save_briefing()
        elif button_id == "queue-btn":
            self._queue_briefing()

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """Handle tab switching to update preview."""
        if event.tab.id == "preview-tab":
            self._update_preview()

    def _apply_template(self, template: BriefingContent) -> None:
        """Apply a template to the editors."""
        self._content = BriefingContent(
            context=template.context,
            requirements=template.requirements,
            constraints=template.constraints,
            success_criteria=template.success_criteria,
        )

        # Update editors
        self.query_one("#context-editor", TextArea).text = self._content.context
        self.query_one("#requirements-editor", TextArea).text = self._content.requirements
        self.query_one("#constraints-editor", TextArea).text = self._content.constraints
        self.query_one("#success-criteria-editor", TextArea).text = self._content.success_criteria

    def _collect_content(self) -> BriefingContent:
        """Collect content from editors."""
        return BriefingContent(
            context=self.query_one("#context-editor", TextArea).text,
            requirements=self.query_one("#requirements-editor", TextArea).text,
            constraints=self.query_one("#constraints-editor", TextArea).text,
            success_criteria=self.query_one("#success-criteria-editor", TextArea).text,
        )

    def _update_preview(self) -> None:
        """Update the preview pane with rendered markdown."""
        content = self._collect_content()
        markdown = content.to_markdown()

        preview = self.query_one("#preview-content", Static)
        preview.update(markdown)

    def _save_briefing(self) -> None:
        """Save the current briefing."""
        content = self._collect_content()
        self._content = content
        markdown = content.to_markdown()

        self.post_message(self.BriefingSaved(content, markdown))

    def _queue_briefing(self) -> None:
        """Queue the briefing for delivery to CEO."""
        content = self._collect_content()
        self._content = content

        self.post_message(self.BriefingQueued(content))

    def get_content(self) -> BriefingContent:
        """Get the current briefing content."""
        return self._collect_content()

    def get_markdown(self) -> str:
        """Get briefing as markdown."""
        return self._collect_content().to_markdown()

    def get_templates(self) -> dict[str, BriefingContent]:
        """Get available templates."""
        return BRIEFING_TEMPLATES
