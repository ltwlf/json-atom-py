"""Tests for extension property preservation across all operations."""

from json_atom.apply import apply_delta
from json_atom.invert import invert_delta
from json_atom.validate import validate_delta

from tests.conftest import deep_clone


class TestValidateExtensions:
    def test_accepts_envelope_extensions(self) -> None:
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [],
            "x_author": "jane@example.com",
            "x_timestamp": "2025-01-15T10:30:00Z",
        }
        result = validate_delta(delta)
        assert result.valid is True

    def test_accepts_operation_extensions(self) -> None:
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {
                    "op": "replace",
                    "path": "$.name",
                    "value": "Bob",
                    "x_comparison": {"strategy": "semantic-embedding", "similarity": 0.42},
                    "x_changeId": "abc-123",
                }
            ],
        }
        result = validate_delta(delta)
        assert result.valid is True

    def test_accepts_non_x_prefix_unknown_properties(self) -> None:
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [],
            "metadata": {"source": "test"},
        }
        result = validate_delta(delta)
        assert result.valid is True


class TestApplyExtensions:
    def test_ignores_envelope_extensions(self) -> None:
        obj = {"name": "Alice"}
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "replace", "path": "$.name", "value": "Bob"}
            ],
            "x_author": "test",
        }
        result = apply_delta(obj, delta)
        assert result["name"] == "Bob"

    def test_ignores_operation_extensions(self) -> None:
        obj = {"name": "Alice"}
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {
                    "op": "replace",
                    "path": "$.name",
                    "value": "Bob",
                    "x_reason": "rename",
                }
            ],
        }
        result = apply_delta(obj, delta)
        assert result["name"] == "Bob"


class TestInvertExtensions:
    def test_preserves_envelope_extensions(self) -> None:
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "replace", "path": "$.name", "value": "Bob", "oldValue": "Alice"}
            ],
            "x_author": "jane@example.com",
            "x_timestamp": "2025-01-15T10:30:00Z",
        }
        inverse = invert_delta(delta)
        assert inverse["x_author"] == "jane@example.com"
        assert inverse["x_timestamp"] == "2025-01-15T10:30:00Z"
        assert inverse["format"] == "json-atom"
        assert inverse["version"] == 1

    def test_preserves_operation_extensions(self) -> None:
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {
                    "op": "replace",
                    "path": "$.summary",
                    "value": "New text",
                    "oldValue": "Old text",
                    "x_comparison": {"strategy": "semantic-embedding", "similarity": 0.42},
                    "x_changeId": "abc-123",
                }
            ],
        }
        inverse = invert_delta(delta)
        inv_op = inverse["operations"][0]
        assert inv_op["x_comparison"] == {"strategy": "semantic-embedding", "similarity": 0.42}
        assert inv_op["x_changeId"] == "abc-123"
        # Core fields should be inverted
        assert inv_op["value"] == "Old text"
        assert inv_op["oldValue"] == "New text"

    def test_preserves_extensions_on_all_op_types(self) -> None:
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "add", "path": "$.role", "value": "admin", "x_tag": "a"},
                {"op": "remove", "path": "$.old", "oldValue": 1, "x_tag": "b"},
                {"op": "replace", "path": "$.x", "value": 2, "oldValue": 1, "x_tag": "c"},
            ],
        }
        inverse = invert_delta(delta)
        # Order is reversed
        assert inverse["operations"][0]["x_tag"] == "c"
        assert inverse["operations"][1]["x_tag"] == "b"
        assert inverse["operations"][2]["x_tag"] == "a"
