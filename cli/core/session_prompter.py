"""Session prompter for worker continuation system.

Injects continuation prompts directly into worker sessions via tmux
to encourage workers to continue when they go idle.

Phase 2 of the continuation system: sends graduated prompts via tmux injection.
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional

from .db import Database
from .constants import (
    CONTINUATION_PROMPT_SOFT_CHECK,
    CONTINUATION_PROMPT_STATUS_REQUEST,
    CONTINUATION_PROMPT_FINAL_WARNING,
)
from .queries import (
    get_active_session_tmux_name,
    get_worker_continuation_context,
)

_logger = logging.getLogger(__name__)


class SessionPrompter:
    """Injects continuation prompts into worker sessions via tmux."""

    def __init__(self, db: Database, org_path: Path):
        """Initialize session prompter.

        Args:
            db: Database instance
            org_path: Path to organization directory
        """
        self.db = db
        self.org_path = org_path

    def send_soft_check(self, worker_id: str) -> bool:
        """Send gentle activity check (5 min idle).

        Args:
            worker_id: Worker ID

        Returns:
            True if prompt sent successfully, False otherwise
        """
        _logger.info(f"Sending soft check to {worker_id}")
        return self._send_prompt(worker_id, CONTINUATION_PROMPT_SOFT_CHECK)

    def send_status_request(self, worker_id: str) -> bool:
        """Send status request (15 min idle).

        Args:
            worker_id: Worker ID

        Returns:
            True if prompt sent successfully, False otherwise
        """
        _logger.info(f"Sending status request to {worker_id}")
        return self._send_prompt(worker_id, CONTINUATION_PROMPT_STATUS_REQUEST)

    def send_final_warning(self, worker_id: str) -> bool:
        """Send final warning before escalation (25 min idle).

        Args:
            worker_id: Worker ID

        Returns:
            True if prompt sent successfully, False otherwise
        """
        _logger.warning(f"Sending final warning to {worker_id}")
        return self._send_prompt(worker_id, CONTINUATION_PROMPT_FINAL_WARNING)

    def _send_prompt(self, worker_id: str, prompt_template: str) -> bool:
        """Send a continuation prompt to worker's session.

        Args:
            worker_id: Worker ID
            prompt_template: Prompt template string with format placeholders

        Returns:
            True if prompt sent successfully, False otherwise
        """
        # Get tmux session name
        tmux_name = self._get_session_tmux_name(worker_id)
        if not tmux_name:
            _logger.warning(f"No active tmux session for worker {worker_id}")
            return False

        # Get worker context for template rendering
        context = self._get_worker_context(worker_id)

        # Send prompt to tmux
        return self._send_prompt_to_tmux(tmux_name, prompt_template, context)

    def _get_session_tmux_name(self, worker_id: str) -> Optional[str]:
        """Get tmux session name for worker's active session.

        Args:
            worker_id: Worker ID

        Returns:
            Tmux session name or None if no active session
        """
        try:
            return get_active_session_tmux_name(self.db, worker_id)
        except Exception:
            _logger.exception("Error getting tmux session for %s", worker_id)
            return None

    def _get_worker_context(self, worker_id: str) -> dict:
        """Get context for prompt template rendering.

        Args:
            worker_id: Worker ID

        Returns:
            Dict with template context (worker_id, manager_id, team_channel, etc.)
        """
        try:
            return get_worker_continuation_context(self.db, worker_id)
        except Exception:
            _logger.exception("Error getting context for %s", worker_id)
            # Return minimal fallback context
            return {
                "worker_id": worker_id,
                "worker_name": "Worker",
                "manager_id": "ceo",
                "team_channel": "general",
                "current_task_id": "your-task",
            }

    def _send_prompt_to_tmux(
        self,
        tmux_name: str,
        prompt_template: str,
        context: dict,
    ) -> bool:
        """Render template and send to tmux session.

        Args:
            tmux_name: Tmux session name
            prompt_template: Template string with placeholders
            context: Dict with template values

        Returns:
            True if sent successfully, False otherwise
        """
        try:
            # Render prompt template
            prompt = prompt_template.format(**context)

            # Send to tmux using send-keys
            # We send the prompt as text that appears in the session
            result = subprocess.run(
                ["tmux", "send-keys", "-t", tmux_name, prompt, "Enter"],
                check=True,
                capture_output=True,
                text=True,
            )

            _logger.debug(
                f"Sent continuation prompt to {tmux_name}: {prompt[:50]}..."
            )
            return True

        except subprocess.CalledProcessError as e:
            _logger.error(
                f"Failed to send prompt to {tmux_name}: {e.stderr}"
            )
            return False
        except KeyError as e:
            _logger.error(
                f"Missing template key in context: {e}. Context: {context}"
            )
            return False
        except Exception:
            _logger.exception("Error sending prompt to %s", tmux_name)
            return False


__all__ = ["SessionPrompter"]
