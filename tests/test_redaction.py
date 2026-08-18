"""No secret may reach a log line, by any route."""

from __future__ import annotations

import json
import logging

from duvo_fde.log import REDACTED, JsonFormatter, RedactionFilter, secret_registry


def _render(record: logging.LogRecord) -> str:
    """Push a record through the filter and formatter and return the output."""
    RedactionFilter().filter(record)
    return JsonFormatter().format(record)


def _record(msg: str, *args: object, **fields: object) -> logging.LogRecord:
    """Build a log record with optional structured fields."""
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=args,
        exc_info=None,
    )
    if fields:
        record.fields = fields
    return record


def test_a_registered_secret_is_removed_from_the_message() -> None:
    secret_registry.register("super-secret-value-123")

    output = _render(_record("connecting with super-secret-value-123"))

    assert "super-secret-value-123" not in output
    assert REDACTED in output


def test_a_registered_secret_is_removed_from_interpolated_arguments() -> None:
    secret_registry.register("super-secret-value-123")

    output = _render(_record("connecting with %s", "super-secret-value-123"))

    assert "super-secret-value-123" not in output


def test_a_registered_secret_is_removed_from_structured_fields() -> None:
    secret_registry.register("super-secret-value-123")

    output = _render(_record("call", request={"header": "super-secret-value-123"}))

    assert "super-secret-value-123" not in output


def test_sensitive_field_names_are_removed_regardless_of_value() -> None:
    """Catches credentials that were never registered."""
    output = _render(_record("call", request={"authorization": "anything-at-all", "store": "7"}))
    payload = json.loads(output)

    assert payload["request"]["authorization"] == REDACTED
    assert payload["request"]["store"] == "7"


def test_bearer_tokens_are_removed_by_pattern() -> None:
    output = _render(_record("header was Bearer abcdef0123456789"))

    assert "abcdef0123456789" not in output


def test_api_key_shaped_strings_are_removed_by_pattern() -> None:
    output = _render(_record("using sk-abcdefghijklmnop for the call"))

    assert "sk-abcdefghijklmnop" not in output


def test_nested_structures_are_redacted() -> None:
    secret_registry.register("super-secret-value-123")

    output = _render(
        _record("call", payload={"items": [{"token": "x", "k": "super-secret-value-123"}]})
    )
    payload = json.loads(output)

    assert payload["payload"]["items"][0]["token"] == REDACTED
    assert "super-secret-value-123" not in output


def test_exception_text_is_redacted() -> None:
    secret_registry.register("super-secret-value-123")
    record = _record("failed")
    record.exc_text = "ValueError: bad credential super-secret-value-123"

    output = _render(record)

    assert "super-secret-value-123" not in output


def test_short_values_are_not_registered() -> None:
    """Redacting very short strings would corrupt unrelated log text."""
    secret_registry.register("ab")

    output = _render(_record("about to abort"))

    assert REDACTED not in output


def test_output_is_a_single_json_line() -> None:
    output = _render(_record("hello", store="7"))

    assert "\n" not in output
    assert json.loads(output)["message"] == "hello"
