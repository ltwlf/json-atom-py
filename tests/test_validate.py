"""Tests for json_atom.validate — delta document structural validation."""

import pytest

from json_atom.validate import validate_delta


class TestValidDelta:
    def test_minimal_valid_delta(self) -> None:
        delta = {"format": "json-atom", "version": 1, "operations": []}
        result = validate_delta(delta)
        assert result.valid is True
        assert result.errors == ()

    def test_valid_delta_with_replace(self) -> None:
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "replace", "path": "$.name", "value": "Bob", "oldValue": "Alice"}
            ],
        }
        result = validate_delta(delta)
        assert result.valid is True

    def test_valid_delta_with_all_ops(self) -> None:
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "add", "path": "$.role", "value": "admin"},
                {"op": "remove", "path": "$.legacy"},
                {"op": "replace", "path": "$.name", "value": "Bob"},
            ],
        }
        result = validate_delta(delta)
        assert result.valid is True

    def test_valid_delta_with_extensions(self) -> None:
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "replace", "path": "$.name", "value": "Bob", "x_reason": "rename"}
            ],
            "x_author": "test",
        }
        result = validate_delta(delta)
        assert result.valid is True

    def test_remove_without_old_value_is_valid(self) -> None:
        """Per spec, oldValue is OPTIONAL on remove."""
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [{"op": "remove", "path": "$.legacy"}],
        }
        result = validate_delta(delta)
        assert result.valid is True

    def test_replace_without_old_value_is_valid(self) -> None:
        """Per spec, oldValue is OPTIONAL on replace."""
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [{"op": "replace", "path": "$.name", "value": "Bob"}],
        }
        result = validate_delta(delta)
        assert result.valid is True


class TestInvalidDelta:
    def test_not_a_dict_none(self) -> None:
        result = validate_delta(None)
        assert result.valid is False
        assert any("JSON object" in e for e in result.errors)

    def test_not_a_dict_string(self) -> None:
        result = validate_delta("hello")
        assert result.valid is False

    def test_not_a_dict_list(self) -> None:
        result = validate_delta([1, 2, 3])
        assert result.valid is False

    def test_not_a_dict_number(self) -> None:
        result = validate_delta(42)
        assert result.valid is False

    def test_missing_format(self) -> None:
        delta = {"version": 1, "operations": []}
        result = validate_delta(delta)
        assert result.valid is False
        assert any("format" in e for e in result.errors)

    def test_wrong_format(self) -> None:
        delta = {"format": "json-patch", "version": 1, "operations": []}
        result = validate_delta(delta)
        assert result.valid is False
        assert any("json-atom" in e for e in result.errors)

    def test_missing_version(self) -> None:
        delta = {"format": "json-atom", "operations": []}
        result = validate_delta(delta)
        assert result.valid is False
        assert any("version" in e for e in result.errors)

    def test_version_is_bool(self) -> None:
        """bool is not a valid version even though bool subclasses int in Python."""
        delta = {"format": "json-atom", "version": True, "operations": []}
        result = validate_delta(delta)
        assert result.valid is False
        assert any("version" in e for e in result.errors)

    def test_version_is_string(self) -> None:
        delta = {"format": "json-atom", "version": "1", "operations": []}
        result = validate_delta(delta)
        assert result.valid is False

    def test_missing_operations(self) -> None:
        delta = {"format": "json-atom", "version": 1}
        result = validate_delta(delta)
        assert result.valid is False
        assert any("operations" in e for e in result.errors)

    def test_operations_not_array(self) -> None:
        delta = {"format": "json-atom", "version": 1, "operations": "not-array"}
        result = validate_delta(delta)
        assert result.valid is False

    def test_multiple_errors(self) -> None:
        delta = {"version": "bad"}
        result = validate_delta(delta)
        assert result.valid is False
        assert len(result.errors) >= 2


class TestInvalidOperations:
    def _make_delta(self, *ops: dict[str, object]) -> dict[str, object]:
        return {"format": "json-atom", "version": 1, "operations": list(ops)}

    def test_operation_not_dict(self) -> None:
        result = validate_delta(self._make_delta("not-a-dict"))  # type: ignore[arg-type]
        assert result.valid is False
        assert any("JSON object" in e for e in result.errors)

    def test_missing_op_field(self) -> None:
        result = validate_delta(self._make_delta({"path": "$.name", "value": "x"}))
        assert result.valid is False
        assert any("'op'" in e for e in result.errors)

    def test_unknown_op(self) -> None:
        result = validate_delta(self._make_delta({"op": "move", "path": "$.name"}))
        assert result.valid is False
        assert any("move" in e for e in result.errors)

    def test_missing_path(self) -> None:
        result = validate_delta(self._make_delta({"op": "replace", "value": "x"}))
        assert result.valid is False
        assert any("'path'" in e for e in result.errors)

    def test_path_not_string(self) -> None:
        result = validate_delta(self._make_delta({"op": "replace", "path": 123, "value": "x"}))
        assert result.valid is False
        assert any("string" in e for e in result.errors)

    def test_add_missing_value(self) -> None:
        result = validate_delta(self._make_delta({"op": "add", "path": "$.name"}))
        assert result.valid is False
        assert any("'value'" in e for e in result.errors)

    def test_add_with_old_value(self) -> None:
        result = validate_delta(
            self._make_delta({"op": "add", "path": "$.name", "value": "x", "oldValue": "y"})
        )
        assert result.valid is False
        assert any("oldValue" in e for e in result.errors)

    def test_remove_with_value(self) -> None:
        result = validate_delta(
            self._make_delta({"op": "remove", "path": "$.name", "value": "x"})
        )
        assert result.valid is False
        assert any("'value'" in e for e in result.errors)

    def test_replace_missing_value(self) -> None:
        result = validate_delta(
            self._make_delta({"op": "replace", "path": "$.name", "oldValue": "x"})
        )
        assert result.valid is False
        assert any("'value'" in e for e in result.errors)

    def test_error_includes_index(self) -> None:
        """Error messages should identify the operation by index."""
        result = validate_delta(
            self._make_delta(
                {"op": "replace", "path": "$.a", "value": "ok"},
                {"op": "badop", "path": "$.b"},
            )
        )
        assert result.valid is False
        assert any("operations[1]" in e for e in result.errors)
