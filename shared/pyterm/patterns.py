"""
Pattern-triggered injection rules.

Watch session output for patterns and trigger automatic responses.
Used for automating prompts like [Y/n], password prompts, etc.
"""

import re
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from shared.pyterm.protocols import ExtractedOutput, Session
from shared.pyterm.config import PytermConfig, LoopDetectionConfig


@dataclass
class PatternRule:
    """A pattern-triggered injection rule."""

    id: str
    pattern: str  # Regex pattern
    response: str  # Text to inject when matched
    once: bool = False  # Only trigger once
    delay: float = 0.0  # Delay before injecting (seconds)
    enabled: bool = True
    _triggered: bool = field(default=False, init=False)
    _compiled: re.Pattern | None = field(default=None, init=False)

    def __post_init__(self):
        self._compiled = re.compile(self.pattern)

    def matches(self, text: str) -> re.Match | None:
        """Check if text matches the pattern."""
        if not self.enabled:
            return None
        if self.once and self._triggered:
            return None
        return self._compiled.search(text) if self._compiled else None

    def mark_triggered(self) -> None:
        """Mark rule as triggered (for once rules)."""
        self._triggered = True

    def reset(self) -> None:
        """Reset triggered state."""
        self._triggered = False


RuleTriggeredCallback = Callable[[PatternRule, re.Match], None]


class PatternMatcher:
    """
    Watches session output and triggers rules.

    Attaches to a session and monitors output for pattern matches.
    When a pattern matches, injects the configured response.
    """

    def __init__(
        self,
        session: Session,
        config: PytermConfig,
    ):
        """
        Initialize the pattern matcher.

        Args:
            session: Session to watch
            config: Pyterm configuration (required - no defaults)
        """
        self._session = session
        self._config = config
        self._rules: dict[str, PatternRule] = {}
        self._callbacks: list[RuleTriggeredCallback] = []
        self._last_output = ""
        self._lock = threading.Lock()
        self._watching = False
        self._watch_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

        # Loop detection using config values
        self._trigger_counts: dict[str, int] = {}
        self._trigger_window_start = time.time()

    @property
    def _loop_config(self) -> LoopDetectionConfig:
        """Get loop detection config."""
        return self._config.loop_detection

    def add_rule(self, rule: PatternRule) -> None:
        """Add a pattern rule."""
        with self._lock:
            self._rules[rule.id] = rule

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a rule by ID."""
        with self._lock:
            if rule_id in self._rules:
                del self._rules[rule_id]
                return True
            return False

    def get_rule(self, rule_id: str) -> PatternRule | None:
        """Get a rule by ID."""
        return self._rules.get(rule_id)

    def clear_rules(self) -> None:
        """Remove all rules."""
        with self._lock:
            self._rules.clear()

    def on_triggered(self, callback: RuleTriggeredCallback) -> None:
        """Register callback for when a rule triggers."""
        self._callbacks.append(callback)

    def check_output(self, output: str) -> list[tuple[PatternRule, re.Match]]:
        """
        Check output against all rules.

        Returns list of (rule, match) tuples for matches found.
        Does NOT inject - caller is responsible for that.
        """
        matches = []

        # Only check new content
        if output == self._last_output:
            return matches

        # Get the new portion of output
        new_content = output
        if self._last_output and output.startswith(self._last_output):
            new_content = output[len(self._last_output):]

        self._last_output = output

        with self._lock:
            for rule in self._rules.values():
                match = rule.matches(new_content)
                if match:
                    # Loop detection
                    if self._is_looping(rule.id):
                        continue

                    matches.append((rule, match))
                    rule.mark_triggered()
                    self._record_trigger(rule.id)

        return matches

    def _is_looping(self, rule_id: str) -> bool:
        """Check if a rule is triggering too frequently (loop detection)."""
        now = time.time()

        # Reset window if expired
        if now - self._trigger_window_start > self._loop_config.window_duration:
            self._trigger_counts.clear()
            self._trigger_window_start = now

        count = self._trigger_counts.get(rule_id, 0)
        return count >= self._loop_config.max_triggers_per_window

    def _record_trigger(self, rule_id: str) -> None:
        """Record a rule trigger for loop detection."""
        self._trigger_counts[rule_id] = self._trigger_counts.get(rule_id, 0) + 1

    def start_watching(self) -> None:
        """Start watching session output and auto-injecting on matches."""
        if self._watching:
            return

        self._watching = True
        self._stop_event.clear()

        poll_interval = self._config.timing.poll_interval

        def watch_loop():
            while not self._stop_event.is_set():
                try:
                    output = self._session.extract()
                    matches = self.check_output(output.text)

                    for rule, match in matches:
                        # Notify callbacks
                        for cb in self._callbacks:
                            cb(rule, match)

                        # Delay if configured
                        if rule.delay > 0:
                            time.sleep(rule.delay)

                        # Inject response
                        self._session.inject(rule.response)

                except Exception:
                    pass  # Session may have stopped

                time.sleep(poll_interval)

            self._watching = False

        self._watch_thread = threading.Thread(target=watch_loop, daemon=True)
        self._watch_thread.start()

    def stop_watching(self) -> None:
        """Stop watching session output."""
        self._stop_event.set()
        self._watching = False

    @property
    def is_watching(self) -> bool:
        """Check if currently watching."""
        return self._watching
