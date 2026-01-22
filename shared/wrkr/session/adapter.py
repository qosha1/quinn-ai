"""
Adapters for converting between wrkr and pyterm types.

Task-to-Prompt: Converts wrkr Task objects into prompts for AI sessions.
Response-to-Result: Converts pyterm PromptResult into wrkr WorkerResult.
"""

from __future__ import annotations

from typing import Any, Protocol

from shared.wrkr.core.task import Task
from shared.wrkr.core.result import WorkerResult


class PromptBuilder(Protocol):
    """Protocol for building prompts from tasks."""

    def build(self, task: Task, context: dict[str, Any] | None = None) -> str:
        """Build a prompt string from a task and optional context."""
        ...


class DefaultPromptBuilder:
    """
    Default prompt builder that formats tasks as structured prompts.

    Creates prompts with clear sections for task details, context,
    and expected output format.
    """

    def __init__(
        self,
        include_metadata: bool = True,
        include_context: bool = True,
    ):
        """
        Initialize the prompt builder.

        Args:
            include_metadata: Include task metadata in prompt
            include_context: Include provided context in prompt
        """
        self._include_metadata = include_metadata
        self._include_context = include_context

    def build(self, task: Task, context: dict[str, Any] | None = None) -> str:
        """
        Build a prompt string from a task.

        Args:
            task: The task to convert to a prompt
            context: Optional context (e.g., from memory, recent history)

        Returns:
            Formatted prompt string
        """
        sections = []

        # Task header
        sections.append(f"# Task: {task.title}")
        sections.append("")

        # Description
        if task.description:
            sections.append("## Description")
            sections.append(task.description)
            sections.append("")

        # Priority indicator
        priority_labels = {
            0: "CRITICAL",
            1: "HIGH",
            2: "MEDIUM",
            3: "LOW",
            4: "BACKLOG",
        }
        priority_label = priority_labels.get(task.priority, f"P{task.priority}")
        sections.append(f"**Priority:** {priority_label}")
        sections.append("")

        # Source and linking
        if task.ask_id or task.okr_id:
            sections.append("## Context Links")
            if task.ask_id:
                sections.append(f"- **Ask:** {task.ask_id}")
            if task.okr_id:
                sections.append(f"- **OKR:** {task.okr_id}")
            sections.append("")

        # Metadata
        if self._include_metadata and task.metadata:
            sections.append("## Metadata")
            for key, value in task.metadata.items():
                sections.append(f"- **{key}:** {value}")
            sections.append("")

        # Context from memory/history
        if self._include_context and context:
            sections.append("## Additional Context")
            if "similar_tasks" in context:
                sections.append("### Similar Past Tasks")
                for similar in context["similar_tasks"][:3]:
                    title = similar.get("task_title", "Unknown")
                    succeeded = similar.get("result_succeeded", False)
                    status = "✓" if succeeded else "✗"
                    sections.append(f"- {status} {title}")
            if "guidance" in context:
                sections.append("### Guidance")
                sections.append(context["guidance"])
            sections.append("")

        # Instructions
        sections.append("## Instructions")
        sections.append("Complete this task. If you encounter issues you cannot resolve,")
        sections.append("clearly state what is blocking you so escalation can occur.")
        sections.append("")

        return "\n".join(sections)


class ResultExtractor:
    """
    Extracts WorkerResult from pyterm PromptResult.

    Analyzes the AI response to determine success/failure,
    detect escalation needs, and extract artifacts.
    """

    # Keywords that suggest the AI needs help
    ESCALATION_KEYWORDS = [
        "cannot proceed",
        "need help",
        "unable to",
        "blocked by",
        "stuck on",
        "don't have access",
        "permission denied",
        "requires approval",
        "need clarification",
        "unclear requirements",
    ]

    # Keywords that suggest success
    SUCCESS_KEYWORDS = [
        "completed",
        "done",
        "finished",
        "successfully",
        "task complete",
    ]

    def __init__(
        self,
        escalation_keywords: list[str] | None = None,
        success_keywords: list[str] | None = None,
    ):
        """
        Initialize the result extractor.

        Args:
            escalation_keywords: Custom keywords indicating escalation need
            success_keywords: Custom keywords indicating success
        """
        self._escalation_keywords = escalation_keywords or self.ESCALATION_KEYWORDS
        self._success_keywords = success_keywords or self.SUCCESS_KEYWORDS

    def extract(
        self,
        prompt_result: Any,  # PromptResult from pyterm
        task: Task,
    ) -> WorkerResult:
        """
        Extract a WorkerResult from a PromptResult.

        Args:
            prompt_result: The PromptResult from pyterm session
            task: The original task (for context)

        Returns:
            WorkerResult representing the execution outcome
        """
        # Handle cancelled execution
        if prompt_result.was_cancelled:
            return WorkerResult.failure(
                error="Execution was cancelled",
                duration_ms=prompt_result.duration_ms,
                metadata={"cancelled": True, "task_id": task.id},
            )

        # Handle explicit error
        if prompt_result.error:
            return WorkerResult.failure(
                error=prompt_result.error,
                duration_ms=prompt_result.duration_ms,
                metadata={"task_id": task.id},
            )

        # Extract response content
        response_content = ""
        if prompt_result.turn and prompt_result.turn.response:
            response_content = prompt_result.turn.response.content or ""

        # Check for escalation need
        escalation_reason = self._check_escalation(response_content)
        if escalation_reason:
            return WorkerResult.escalate(
                reason=escalation_reason,
                output=response_content,
                duration_ms=prompt_result.duration_ms,
                metadata={"task_id": task.id},
            )

        # Check for success indicators
        succeeded = self._check_success(response_content)

        # Extract tool calls as artifacts
        artifacts = []
        if prompt_result.turn:
            for tool_call in prompt_result.turn.tool_calls:
                artifacts.append({
                    "type": "tool_call",
                    "tool": tool_call.name,
                    "arguments": tool_call.arguments,
                })

        if succeeded:
            return WorkerResult.success(
                output=response_content,
                duration_ms=prompt_result.duration_ms,
                artifacts=artifacts,
                metadata={"task_id": task.id},
            )
        else:
            # Not clearly succeeded but not escalating - treat as failure
            return WorkerResult.failure(
                error="Task did not complete successfully",
                output=response_content,
                duration_ms=prompt_result.duration_ms,
                metadata={"task_id": task.id},
            )

    def _check_escalation(self, content: str) -> str | None:
        """
        Check if response indicates escalation is needed.

        Returns the escalation reason if found, None otherwise.
        """
        content_lower = content.lower()
        for keyword in self._escalation_keywords:
            if keyword in content_lower:
                # Extract surrounding context as reason
                idx = content_lower.find(keyword)
                start = max(0, idx - 50)
                end = min(len(content), idx + len(keyword) + 100)
                return content[start:end].strip()
        return None

    def _check_success(self, content: str) -> bool:
        """Check if response indicates successful completion."""
        content_lower = content.lower()
        return any(keyword in content_lower for keyword in self._success_keywords)
