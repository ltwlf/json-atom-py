"""Tests for json_atom.invert — delta inversion and reversion."""

import pytest

from json_atom.apply import apply_delta
from json_atom.errors import InvertError
from json_atom.invert import invert_delta, revert_delta

from tests.conftest import deep_clone


class TestInvertDeltaOperations:
    def test_add_becomes_remove(self) -> None:
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "add", "path": "$.role", "value": "admin"}
            ],
        }
        inverse = invert_delta(delta)
        assert len(inverse["operations"]) == 1
        op = inverse["operations"][0]
        assert op["op"] == "remove"
        assert op["path"] == "$.role"
        assert op["oldValue"] == "admin"
        assert "value" not in op

    def test_remove_becomes_add(self) -> None:
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "remove", "path": "$.legacy", "oldValue": True}
            ],
        }
        inverse = invert_delta(delta)
        op = inverse["operations"][0]
        assert op["op"] == "add"
        assert op["path"] == "$.legacy"
        assert op["value"] is True
        assert "oldValue" not in op

    def test_replace_swaps_values(self) -> None:
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "replace", "path": "$.name", "value": "Bob", "oldValue": "Alice"}
            ],
        }
        inverse = invert_delta(delta)
        op = inverse["operations"][0]
        assert op["op"] == "replace"
        assert op["path"] == "$.name"
        assert op["value"] == "Alice"
        assert op["oldValue"] == "Bob"

    def test_operation_order_reversed(self) -> None:
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "replace", "path": "$.name", "value": "Bob", "oldValue": "Alice"},
                {"op": "add", "path": "$.role", "value": "admin"},
            ],
        }
        inverse = invert_delta(delta)
        assert len(inverse["operations"]) == 2
        # First in inverse was last in original
        assert inverse["operations"][0]["op"] == "remove"
        assert inverse["operations"][0]["path"] == "$.role"
        # Second in inverse was first in original
        assert inverse["operations"][1]["op"] == "replace"
        assert inverse["operations"][1]["path"] == "$.name"

    def test_empty_operations(self) -> None:
        delta = {"format": "json-atom", "version": 1, "operations": []}
        inverse = invert_delta(delta)
        assert inverse["operations"] == []


class TestInvertDeltaErrors:
    def test_missing_old_value_on_replace_raises(self) -> None:
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "replace", "path": "$.name", "value": "Bob"}
            ],
        }
        with pytest.raises(InvertError, match="oldValue"):
            invert_delta(delta)

    def test_missing_old_value_on_remove_raises(self) -> None:
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "remove", "path": "$.legacy"}
            ],
        }
        with pytest.raises(InvertError, match="oldValue"):
            invert_delta(delta)

    def test_invalid_delta_raises(self) -> None:
        with pytest.raises(InvertError, match="Invalid delta"):
            invert_delta({"not": "a-delta"})

    def test_non_dict_delta_raises(self) -> None:
        with pytest.raises(InvertError):
            invert_delta("string")  # type: ignore[arg-type]

    def test_error_identifies_operation_index(self) -> None:
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "add", "path": "$.a", "value": 1},
                {"op": "replace", "path": "$.b", "value": 2},  # missing oldValue
            ],
        }
        with pytest.raises(InvertError, match="operations\\[1\\]"):
            invert_delta(delta)


class TestRevertDelta:
    def test_full_round_trip(self) -> None:
        """apply(source, delta) == target AND revert(target, delta) == source."""
        source = {"name": "Alice", "role": "user"}
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "replace", "path": "$.name", "value": "Bob", "oldValue": "Alice"},
                {"op": "replace", "path": "$.role", "value": "admin", "oldValue": "user"},
            ],
        }
        target = apply_delta(deep_clone(source), delta)
        assert target == {"name": "Bob", "role": "admin"}

        recovered = revert_delta(deep_clone(target), delta)
        assert recovered == source

    def test_round_trip_with_add_and_remove(self) -> None:
        source = {"name": "Alice"}
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "add", "path": "$.role", "value": "admin"},
            ],
        }
        target = apply_delta(deep_clone(source), delta)
        assert target == {"name": "Alice", "role": "admin"}

        recovered = revert_delta(deep_clone(target), delta)
        assert recovered == source

    def test_double_inversion_is_identity(self) -> None:
        """invert(invert(delta)) == delta for all operation types."""
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "add", "path": "$.role", "value": "admin"},
                {"op": "remove", "path": "$.legacy", "oldValue": True},
                {"op": "replace", "path": "$.name", "value": "Bob", "oldValue": "Alice"},
            ],
        }
        double_inverted = invert_delta(invert_delta(delta))
        assert double_inverted["operations"] == delta["operations"]
        assert double_inverted["format"] == delta["format"]
        assert double_inverted["version"] == delta["version"]

    def test_non_reversible_delta_raises(self) -> None:
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "replace", "path": "$.name", "value": "Bob"}
            ],
        }
        with pytest.raises(InvertError):
            revert_delta({"name": "Bob"}, delta)
