"""Cross-module edge cases and error conditions."""

import pytest

from json_atom.apply import apply_delta
from json_atom.diff import diff_delta
from json_atom.errors import ApplyError, PathError
from json_atom.invert import invert_delta
from json_atom.path import parse_path

from tests.conftest import deep_clone


# ---------------------------------------------------------------------------
# Filter edge cases
# ---------------------------------------------------------------------------


class TestFilterEdgeCases:
    def test_key_filter_match_zero_on_replace(self) -> None:
        with pytest.raises(ApplyError, match="zero"):
            apply_delta({"items": [{"id": 1}]}, {
                "format": "json-atom",
                "version": 1,
                "operations": [{"op": "replace", "path": "$.items[?(@.id==99)].name", "value": "x"}],
            })

    def test_key_filter_match_zero_on_remove(self) -> None:
        with pytest.raises(ApplyError, match="zero"):
            apply_delta({"items": [{"id": 1}]}, {
                "format": "json-atom",
                "version": 1,
                "operations": [{"op": "remove", "path": "$.items[?(@.id==99)]"}],
            })

    def test_key_filter_multiple_matches(self) -> None:
        with pytest.raises(ApplyError, match="2 elements"):
            apply_delta({"items": [{"id": 1}, {"id": 1}]}, {
                "format": "json-atom",
                "version": 1,
                "operations": [{"op": "replace", "path": "$.items[?(@.id==1)].name", "value": "x"}],
            })

    def test_value_filter_multiple_matches(self) -> None:
        with pytest.raises(ApplyError):
            apply_delta({"tags": ["a", "a"]}, {
                "format": "json-atom",
                "version": 1,
                "operations": [{"op": "remove", "path": "$.tags[?(@=='a')]"}],
            })


# ---------------------------------------------------------------------------
# Property existence
# ---------------------------------------------------------------------------


class TestPropertyExistence:
    def test_add_existing_property_raises(self) -> None:
        with pytest.raises(ApplyError, match="already exists"):
            apply_delta({"name": "Alice"}, {
                "format": "json-atom",
                "version": 1,
                "operations": [{"op": "add", "path": "$.name", "value": "Bob"}],
            })

    def test_remove_nonexistent_property_raises(self) -> None:
        with pytest.raises(ApplyError, match="does not exist"):
            apply_delta({"name": "Alice"}, {
                "format": "json-atom",
                "version": 1,
                "operations": [{"op": "remove", "path": "$.missing"}],
            })

    def test_replace_nonexistent_property_raises(self) -> None:
        with pytest.raises(ApplyError, match="does not exist"):
            apply_delta({"name": "Alice"}, {
                "format": "json-atom",
                "version": 1,
                "operations": [{"op": "replace", "path": "$.missing", "value": "x"}],
            })


# ---------------------------------------------------------------------------
# Null vs absent
# ---------------------------------------------------------------------------


class TestNullVsAbsent:
    def test_null_property_is_present(self) -> None:
        """A property with null value is not the same as an absent property."""
        old = {"val": None}
        new = {"val": "hello"}
        delta = diff_delta(old, new)
        op = delta["operations"][0]
        assert op["op"] == "replace"
        assert op["oldValue"] is None

    def test_absent_property_is_add(self) -> None:
        old: dict[str, object] = {}
        new = {"val": None}
        delta = diff_delta(old, new)
        op = delta["operations"][0]
        assert op["op"] == "add"
        assert op["value"] is None


# ---------------------------------------------------------------------------
# Empty operations (no-op delta)
# ---------------------------------------------------------------------------


class TestNoOpDelta:
    def test_empty_operations_is_valid(self) -> None:
        delta = {"format": "json-atom", "version": 1, "operations": []}
        obj = {"name": "Alice"}
        result = apply_delta(deep_clone(obj), delta)
        assert result == obj

    def test_empty_operations_inversion(self) -> None:
        delta = {"format": "json-atom", "version": 1, "operations": []}
        inverse = invert_delta(delta)
        assert inverse["operations"] == []


# ---------------------------------------------------------------------------
# Deeply nested paths
# ---------------------------------------------------------------------------


class TestDeepNesting:
    def test_deeply_nested_diff_and_apply(self) -> None:
        """10+ levels of nesting."""
        old: dict[str, object] = {"a": {"b": {"c": {"d": {"e": {"f": {"g": {"h": {"i": {"j": "old"}}}}}}}}}}
        new: dict[str, object] = {"a": {"b": {"c": {"d": {"e": {"f": {"g": {"h": {"i": {"j": "new"}}}}}}}}}}
        delta = diff_delta(old, new)
        assert len(delta["operations"]) == 1
        assert delta["operations"][0]["path"] == "$.a.b.c.d.e.f.g.h.i.j"
        result = apply_delta(deep_clone(old), delta)
        assert result == new


# ---------------------------------------------------------------------------
# Unicode
# ---------------------------------------------------------------------------


class TestUnicode:
    def test_unicode_in_property_names(self) -> None:
        old = {"name": "Alice"}
        new = {"name": "Alice"}
        # Bracket-notation property with unicode
        old2 = {}
        old2["café"] = 1
        new2 = {}
        new2["café"] = 2
        delta = diff_delta(old2, new2)
        assert len(delta["operations"]) == 1
        result = apply_delta(deep_clone(old2), delta)
        assert result == new2

    def test_unicode_in_string_values(self) -> None:
        old = {"greeting": "hello"}
        new = {"greeting": "こんにちは"}
        delta = diff_delta(old, new)
        result = apply_delta(deep_clone(old), delta)
        assert result == new


# ---------------------------------------------------------------------------
# Large arrays
# ---------------------------------------------------------------------------


class TestLargeArrays:
    def test_large_index_array(self) -> None:
        old = {"items": list(range(100))}
        new = {"items": list(range(100))}
        new["items"][50] = 999
        delta = diff_delta(old, new)
        assert len(delta["operations"]) == 1
        result = apply_delta(deep_clone(old), delta)
        assert result == new

    def test_large_keyed_array(self) -> None:
        old = {"items": [{"id": i, "val": i} for i in range(100)]}
        new = {"items": [{"id": i, "val": i} for i in range(100)]}
        new["items"][50]["val"] = 999
        delta = diff_delta(old, new, array_identity_keys={"items": "id"})
        result = apply_delta(deep_clone(old), delta)
        assert result == new


# ---------------------------------------------------------------------------
# Malformed paths
# ---------------------------------------------------------------------------


class TestMalformedPaths:
    def test_missing_dollar_sign(self) -> None:
        with pytest.raises(PathError):
            parse_path("name")

    def test_empty_path(self) -> None:
        with pytest.raises(PathError):
            parse_path("")

    def test_malformed_path_in_delta_raises_apply_error(self) -> None:
        with pytest.raises(ApplyError):
            apply_delta({"x": 1}, {
                "format": "json-atom",
                "version": 1,
                "operations": [{"op": "replace", "path": "invalid", "value": 2}],
            })


# ---------------------------------------------------------------------------
# Keyed-array consistency edge cases
# ---------------------------------------------------------------------------


class TestKeyedArrayConsistencyEdgeCases:
    def test_bool_vs_int_identity_mismatch(self) -> None:
        """Filter value true should not match int 1 in identity check."""
        with pytest.raises(ApplyError, match="mismatch"):
            apply_delta({"items": []}, {
                "format": "json-atom",
                "version": 1,
                "operations": [
                    {"op": "add", "path": "$.items[?(@.active==true)]", "value": {"active": 1}}
                ],
            })


# ---------------------------------------------------------------------------
# Diff + apply integration
# ---------------------------------------------------------------------------


class TestDiffApplyIntegration:
    def test_complex_object_diff_apply(self) -> None:
        """Complex object with multiple changes at different levels."""
        old = {
            "user": {"name": "Alice", "age": 30, "address": {"city": "Portland", "zip": "97201"}},
            "settings": {"theme": "light", "notifications": True},
        }
        new = {
            "user": {"name": "Alice", "age": 31, "address": {"city": "Seattle", "zip": "97201"}},
            "settings": {"theme": "dark", "notifications": True, "language": "en"},
        }
        delta = diff_delta(old, new)
        result = apply_delta(deep_clone(old), delta)
        assert result == new

    def test_diff_invert_apply_roundtrip(self) -> None:
        """Full round-trip: apply(target, invert(diff(source, target))) == source."""
        source = {"name": "Alice", "items": [1, 2, 3]}
        target = {"name": "Bob", "items": [1, 2, 4], "extra": True}
        delta = diff_delta(source, target)
        result = apply_delta(deep_clone(source), delta)
        assert result == target

        inverse = invert_delta(delta)
        recovered = apply_delta(deep_clone(target), inverse)
        assert recovered == source

    def test_root_diff(self) -> None:
        """Diff between scalars at root level produces root replace."""
        delta = diff_delta("old", "new")
        assert len(delta["operations"]) == 1
        op = delta["operations"][0]
        assert op["op"] == "replace"
        assert op["path"] == "$"
