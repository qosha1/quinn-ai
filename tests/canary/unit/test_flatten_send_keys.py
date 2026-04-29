"""Regression tests for _flatten_for_send_keys (quinn-ai-wbgv).

tmux send-keys types each character literally; embedded \n submits the
partial input on claude_code's TUI. Multi-line kickstart messages must be
flattened to a single line before delivery.
"""
from shared.testing.canary.canary_ops import _flatten_for_send_keys


def test_single_line_message_is_unchanged():
    msg = "Run: msgr send @bob 'hi'"
    assert _flatten_for_send_keys(msg) == msg


def test_newlines_become_spaces():
    msg = "Hi Eve.\nPlease do X.\nThen do Y."
    assert _flatten_for_send_keys(msg) == "Hi Eve. Please do X. Then do Y."


def test_yaml_block_scalar_indented_content_collapses():
    # Mimics what 'message: |' produces in YAML: leading indent, blank lines.
    msg = (
        "Hi Diana — please run:\n"
        "\n"
        "  qn org hire --name Eve --role engineer --manager x\n"
        "  qn org hire --name Frank --role engineer --manager x\n"
    )
    out = _flatten_for_send_keys(msg)
    assert "\n" not in out
    # Whitespace runs squeezed
    assert "  " not in out
    # All commands and the greeting survive
    assert "Hi Diana" in out
    assert "qn org hire --name Eve" in out
    assert "qn org hire --name Frank" in out


def test_crlf_normalized():
    msg = "first\r\nsecond\r\nthird"
    assert _flatten_for_send_keys(msg) == "first second third"


def test_lone_carriage_return_handled():
    msg = "first\rsecond"
    assert _flatten_for_send_keys(msg) == "first second"


def test_no_newlines_short_circuits():
    # Performance-adjacent: the no-\n path should not allocate.
    msg = "x" * 10_000
    assert _flatten_for_send_keys(msg) is msg
