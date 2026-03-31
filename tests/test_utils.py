"""Tests for json_atom._utils — json_equal and json_type_of."""

import pytest

from json_atom._utils import json_equal, json_type_of


class TestJsonEqual:
    """JSON value equality with strict type matching."""

    # --- Booleans ---

    def test_bool_true_equals_true(self) -> None:
        assert json_equal(True, True) is True

    def test_bool_false_equals_false(self) -> None:
        assert json_equal(False, False) is True

    def test_bool_true_not_equals_false(self) -> None:
        assert json_equal(True, False) is False

    def test_bool_not_equals_int(self) -> None:
        """JSON boolean and number are distinct types."""
        assert json_equal(True, 1) is False
        assert json_equal(False, 0) is False

    def test_bool_not_equals_string(self) -> None:
        assert json_equal(True, "true") is False
        assert json_equal(False, "false") is False

    # --- Numbers (int and float are both JSON "number") ---

    def test_int_equals_int(self) -> None:
        assert json_equal(42, 42) is True
        assert json_equal(0, 0) is True
        assert json_equal(-1, -1) is True

    def test_int_not_equals_different_int(self) -> None:
        assert json_equal(42, 43) is False

    def test_float_equals_float(self) -> None:
        assert json_equal(3.14, 3.14) is True

    def test_int_equals_equivalent_float(self) -> None:
        """JSON has a single number type — int 42 and float 42.0 are equal."""
        assert json_equal(42, 42.0) is True
        assert json_equal(0, 0.0) is True

    def test_int_not_equals_different_float(self) -> None:
        assert json_equal(42, 42.1) is False

    def test_negative_numbers(self) -> None:
        assert json_equal(-5, -5) is True
        assert json_equal(-5, -5.0) is True
        assert json_equal(-5, 5) is False

    # --- Numbers vs non-numbers ---

    def test_number_not_equals_string(self) -> None:
        assert json_equal(42, "42") is False

    def test_number_not_equals_none(self) -> None:
        assert json_equal(42, None) is False

    def test_number_not_equals_bool(self) -> None:
        assert json_equal(1, True) is False
        assert json_equal(0, False) is False

    # --- Strings ---

    def test_string_equals_string(self) -> None:
        assert json_equal("hello", "hello") is True
        assert json_equal("", "") is True

    def test_string_not_equals_different_string(self) -> None:
        assert json_equal("hello", "world") is False

    def test_string_not_equals_number(self) -> None:
        assert json_equal("42", 42) is False

    def test_string_not_equals_none(self) -> None:
        assert json_equal("null", None) is False

    # --- Null ---

    def test_none_equals_none(self) -> None:
        assert json_equal(None, None) is True

    def test_none_not_equals_zero(self) -> None:
        assert json_equal(None, 0) is False

    def test_none_not_equals_false(self) -> None:
        assert json_equal(None, False) is False

    def test_none_not_equals_empty_string(self) -> None:
        assert json_equal(None, "") is False

    # --- Dicts (JSON objects — unordered) ---

    def test_dict_equals_dict(self) -> None:
        assert json_equal({"a": 1, "b": 2}, {"b": 2, "a": 1}) is True

    def test_dict_not_equals_different_dict(self) -> None:
        assert json_equal({"a": 1}, {"a": 2}) is False

    def test_dict_not_equals_different_keys(self) -> None:
        assert json_equal({"a": 1}, {"b": 1}) is False

    def test_empty_dicts(self) -> None:
        assert json_equal({}, {}) is True

    def test_dict_not_equals_list(self) -> None:
        assert json_equal({}, []) is False

    # --- Lists (JSON arrays — ordered) ---

    def test_list_equals_list(self) -> None:
        assert json_equal([1, 2, 3], [1, 2, 3]) is True

    def test_list_not_equals_different_order(self) -> None:
        assert json_equal([1, 2, 3], [3, 2, 1]) is False

    def test_list_not_equals_different_length(self) -> None:
        assert json_equal([1, 2], [1, 2, 3]) is False

    def test_empty_lists(self) -> None:
        assert json_equal([], []) is True

    # --- Nested structures ---

    def test_nested_objects(self) -> None:
        a = {"user": {"name": "Alice", "age": 30}}
        b = {"user": {"name": "Alice", "age": 30}}
        assert json_equal(a, b) is True

    def test_nested_objects_different(self) -> None:
        a = {"user": {"name": "Alice"}}
        b = {"user": {"name": "Bob"}}
        assert json_equal(a, b) is False

    def test_nested_arrays_in_objects(self) -> None:
        a = {"items": [1, 2, 3]}
        b = {"items": [1, 2, 3]}
        assert json_equal(a, b) is True


class TestJsonTypeOf:
    def test_null(self) -> None:
        assert json_type_of(None) == "null"

    def test_boolean(self) -> None:
        assert json_type_of(True) == "boolean"
        assert json_type_of(False) == "boolean"

    def test_integer(self) -> None:
        assert json_type_of(42) == "number"
        assert json_type_of(0) == "number"
        assert json_type_of(-1) == "number"

    def test_float(self) -> None:
        assert json_type_of(3.14) == "number"
        assert json_type_of(0.0) == "number"

    def test_string(self) -> None:
        assert json_type_of("hello") == "string"
        assert json_type_of("") == "string"

    def test_dict(self) -> None:
        assert json_type_of({}) == "object"
        assert json_type_of({"a": 1}) == "object"

    def test_list(self) -> None:
        assert json_type_of([]) == "array"
        assert json_type_of([1, 2]) == "array"

    def test_non_json_type_raises(self) -> None:
        with pytest.raises(TypeError, match="Not a JSON type"):
            json_type_of(set())

        with pytest.raises(TypeError, match="Not a JSON type"):
            json_type_of(b"bytes")

        with pytest.raises(TypeError, match="Not a JSON type"):
            json_type_of(lambda: None)
