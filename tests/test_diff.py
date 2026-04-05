"""Tests for json_atom.diff — delta computation."""

import re

import pytest

from json_atom._identity import IdentityResolver
from json_atom.apply import apply_delta
from json_atom.diff import diff_delta
from json_atom.errors import DiffError
from json_atom.invert import invert_delta

from tests.conftest import deep_clone, load_fixture


# ---------------------------------------------------------------------------
# Identical objects
# ---------------------------------------------------------------------------


class TestIdentical:
    def test_identical_objects_empty_ops(self) -> None:
        obj = {"name": "Alice", "age": 30}
        delta = diff_delta(obj, obj)
        assert delta["operations"] == []

    def test_identical_arrays_empty_ops(self) -> None:
        delta = diff_delta([1, 2, 3], [1, 2, 3])
        assert delta["operations"] == []

    def test_identical_scalars_empty_ops(self) -> None:
        delta = diff_delta(42, 42)
        assert delta["operations"] == []

    def test_identical_null_empty_ops(self) -> None:
        delta = diff_delta(None, None)
        assert delta["operations"] == []


# ---------------------------------------------------------------------------
# Simple property operations
# ---------------------------------------------------------------------------


class TestPropertyDiff:
    def test_replace_property(self) -> None:
        old = {"name": "Alice"}
        new = {"name": "Bob"}
        delta = diff_delta(old, new)
        assert len(delta["operations"]) == 1
        op = delta["operations"][0]
        assert op["op"] == "replace"
        assert op["path"] == "$.name"
        assert op["value"] == "Bob"
        assert op["oldValue"] == "Alice"

    def test_add_property(self) -> None:
        old = {"name": "Alice"}
        new = {"name": "Alice", "role": "admin"}
        delta = diff_delta(old, new)
        ops = delta["operations"]
        add_ops = [o for o in ops if o["op"] == "add"]
        assert len(add_ops) == 1
        assert add_ops[0]["path"] == "$.role"
        assert add_ops[0]["value"] == "admin"

    def test_remove_property(self) -> None:
        old = {"name": "Alice", "role": "admin"}
        new = {"name": "Alice"}
        delta = diff_delta(old, new)
        ops = delta["operations"]
        remove_ops = [o for o in ops if o["op"] == "remove"]
        assert len(remove_ops) == 1
        assert remove_ops[0]["path"] == "$.role"
        assert remove_ops[0]["oldValue"] == "admin"

    def test_nested_property_changes(self) -> None:
        old = {"user": {"address": {"city": "Portland"}}}
        new = {"user": {"address": {"city": "Seattle"}}}
        delta = diff_delta(old, new)
        assert len(delta["operations"]) == 1
        assert delta["operations"][0]["path"] == "$.user.address.city"

    def test_replace_with_null(self) -> None:
        old = {"val": "hello"}
        new = {"val": None}
        delta = diff_delta(old, new)
        op = delta["operations"][0]
        assert op["value"] is None
        assert op["oldValue"] == "hello"


# ---------------------------------------------------------------------------
# Type changes
# ---------------------------------------------------------------------------


class TestTypeChanges:
    def test_object_to_array(self) -> None:
        old = {"data": {"key": "val"}}
        new = {"data": [1, 2, 3]}
        delta = diff_delta(old, new)
        ops = [o for o in delta["operations"] if o["path"] == "$.data"]
        assert len(ops) == 1
        assert ops[0]["op"] == "replace"

    def test_array_to_object(self) -> None:
        old = {"data": [1, 2]}
        new = {"data": {"key": "val"}}
        delta = diff_delta(old, new)
        ops = [o for o in delta["operations"] if o["path"] == "$.data"]
        assert len(ops) == 1
        assert ops[0]["op"] == "replace"

    def test_string_to_number(self) -> None:
        old = {"val": "42"}
        new = {"val": 42}
        delta = diff_delta(old, new)
        op = delta["operations"][0]
        assert op["op"] == "replace"
        assert op["value"] == 42
        assert op["oldValue"] == "42"

    def test_null_to_object(self) -> None:
        old = {"data": None}
        new = {"data": {"key": "val"}}
        delta = diff_delta(old, new)
        op = delta["operations"][0]
        assert op["op"] == "replace"


# ---------------------------------------------------------------------------
# Index-based array comparison
# ---------------------------------------------------------------------------


class TestIndexArrays:
    def test_replace_element(self) -> None:
        old = {"tags": ["urgent", "review"]}
        new = {"tags": ["urgent", "approved"]}
        delta = diff_delta(old, new)
        ops = delta["operations"]
        assert len(ops) == 1
        assert ops[0]["path"] == "$.tags[1]"
        assert ops[0]["op"] == "replace"

    def test_different_lengths_add(self) -> None:
        old = {"items": [1, 2]}
        new = {"items": [1, 2, 3]}
        delta = diff_delta(old, new)
        add_ops = [o for o in delta["operations"] if o["op"] == "add"]
        assert len(add_ops) == 1
        assert add_ops[0]["path"] == "$.items[2]"

    def test_different_lengths_remove(self) -> None:
        old = {"items": [1, 2, 3]}
        new = {"items": [1, 2]}
        delta = diff_delta(old, new)
        remove_ops = [o for o in delta["operations"] if o["op"] == "remove"]
        assert len(remove_ops) == 1
        assert remove_ops[0]["path"] == "$.items[2]"

    def test_explicit_index_identity(self) -> None:
        """$index identity mode explicitly set."""
        old = {"items": [1, 2]}
        new = {"items": [1, 3]}
        delta = diff_delta(old, new, array_identity_keys={"items": "$index"})
        assert len(delta["operations"]) == 1
        assert delta["operations"][0]["path"] == "$.items[1]"


# ---------------------------------------------------------------------------
# Key-based array comparison
# ---------------------------------------------------------------------------


class TestKeyedArrays:
    def test_update_element_property(self) -> None:
        old = {"items": [{"id": 1, "name": "Widget", "price": 10}]}
        new = {"items": [{"id": 1, "name": "Widget Pro", "price": 10}]}
        delta = diff_delta(old, new, array_identity_keys={"items": "id"})
        ops = delta["operations"]
        assert len(ops) == 1
        assert ops[0]["path"] == "$.items[?(@.id==1)].name"
        assert ops[0]["value"] == "Widget Pro"

    def test_add_element(self) -> None:
        old = {"items": [{"id": 1, "name": "Widget"}]}
        new = {"items": [{"id": 1, "name": "Widget"}, {"id": 2, "name": "Gadget"}]}
        delta = diff_delta(old, new, array_identity_keys={"items": "id"})
        add_ops = [o for o in delta["operations"] if o["op"] == "add"]
        assert len(add_ops) == 1
        assert add_ops[0]["value"] == {"id": 2, "name": "Gadget"}

    def test_remove_element(self) -> None:
        old = {"items": [{"id": 1, "name": "Widget"}, {"id": 2, "name": "Gadget"}]}
        new = {"items": [{"id": 1, "name": "Widget"}]}
        delta = diff_delta(old, new, array_identity_keys={"items": "id"})
        remove_ops = [o for o in delta["operations"] if o["op"] == "remove"]
        assert len(remove_ops) == 1
        assert remove_ops[0]["oldValue"] == {"id": 2, "name": "Gadget"}

    def test_string_id(self) -> None:
        old = {"items": [{"id": "a", "val": 1}]}
        new = {"items": [{"id": "a", "val": 2}]}
        delta = diff_delta(old, new, array_identity_keys={"items": "id"})
        assert delta["operations"][0]["path"] == "$.items[?(@.id=='a')].val"

    def test_numeric_id_typed_filter(self) -> None:
        """Numeric IDs should produce number literals in filter, not string."""
        old = {"items": [{"id": 42, "val": 1}]}
        new = {"items": [{"id": 42, "val": 2}]}
        delta = diff_delta(old, new, array_identity_keys={"items": "id"})
        assert "id==42" in delta["operations"][0]["path"]
        assert "id=='42'" not in delta["operations"][0]["path"]

    def test_missing_identity_key_raises(self) -> None:
        with pytest.raises(DiffError, match="identity key"):
            diff_delta(
                {"items": [{"name": "Widget"}]},
                {"items": [{"name": "Gadget"}]},
                array_identity_keys={"items": "id"},
            )


# ---------------------------------------------------------------------------
# Value-based array comparison
# ---------------------------------------------------------------------------


class TestValueArrays:
    def test_string_values_add(self) -> None:
        old = {"tags": ["urgent"]}
        new = {"tags": ["urgent", "review"]}
        delta = diff_delta(old, new, array_identity_keys={"tags": "$value"})
        add_ops = [o for o in delta["operations"] if o["op"] == "add"]
        assert len(add_ops) == 1
        assert "=='review'" in add_ops[0]["path"]

    def test_string_values_remove(self) -> None:
        old = {"tags": ["urgent", "draft"]}
        new = {"tags": ["urgent"]}
        delta = diff_delta(old, new, array_identity_keys={"tags": "$value"})
        remove_ops = [o for o in delta["operations"] if o["op"] == "remove"]
        assert len(remove_ops) == 1
        assert "=='draft'" in remove_ops[0]["path"]

    def test_number_values(self) -> None:
        old = {"scores": [10, 20]}
        new = {"scores": [10, 30]}
        delta = diff_delta(old, new, array_identity_keys={"scores": "$value"})
        assert len(delta["operations"]) == 2  # remove 20, add 30


# ---------------------------------------------------------------------------
# Reversibility
# ---------------------------------------------------------------------------


class TestReversibility:
    def test_non_reversible_omits_old_value(self) -> None:
        old = {"name": "Alice"}
        new = {"name": "Bob"}
        delta = diff_delta(old, new, reversible=False)
        op = delta["operations"][0]
        assert op["op"] == "replace"
        assert "oldValue" not in op

    def test_non_reversible_remove_omits_old_value(self) -> None:
        old = {"name": "Alice", "role": "admin"}
        new = {"name": "Alice"}
        delta = diff_delta(old, new, reversible=False)
        remove_ops = [o for o in delta["operations"] if o["op"] == "remove"]
        assert "oldValue" not in remove_ops[0]

    def test_reversible_includes_old_value(self) -> None:
        old = {"name": "Alice"}
        new = {"name": "Bob"}
        delta = diff_delta(old, new, reversible=True)
        assert "oldValue" in delta["operations"][0]


# ---------------------------------------------------------------------------
# Special property names
# ---------------------------------------------------------------------------


class TestSpecialPaths:
    def test_property_needing_brackets(self) -> None:
        old = {"a.b": 1}
        new = {"a.b": 2}
        delta = diff_delta(old, new)
        assert delta["operations"][0]["path"] == "$['a.b']"

    def test_digit_starting_property(self) -> None:
        old = {"0key": "old"}
        new = {"0key": "new"}
        delta = diff_delta(old, new)
        assert delta["operations"][0]["path"] == "$['0key']"


# ---------------------------------------------------------------------------
# Nested array keys
# ---------------------------------------------------------------------------


class TestNestedArrayKeys:
    def test_nested_keyed_array(self) -> None:
        old = {"users": [{"id": 1, "contacts": [{"type": "email", "val": "a@b.com"}]}]}
        new = {"users": [{"id": 1, "contacts": [{"type": "email", "val": "new@b.com"}]}]}
        delta = diff_delta(
            old, new,
            array_identity_keys={"users": "id", "users.contacts": "type"},
        )
        ops = delta["operations"]
        assert len(ops) == 1
        # Should target the nested property through both filters
        assert "id==1" in ops[0]["path"]
        assert "type=='email'" in ops[0]["path"]
        assert ops[0]["path"].endswith(".val")


# ---------------------------------------------------------------------------
# Delta envelope format
# ---------------------------------------------------------------------------


class TestDeltaFormat:
    def test_envelope_fields(self) -> None:
        delta = diff_delta({"a": 1}, {"a": 2})
        assert delta["format"] == "json-atom"
        assert delta["version"] == 1
        assert isinstance(delta["operations"], list)


# ---------------------------------------------------------------------------
# Error conditions
# ---------------------------------------------------------------------------


class TestDiffErrors:
    def test_non_finite_float_raises(self) -> None:
        with pytest.raises(DiffError, match="Non-finite"):
            diff_delta({"val": float("inf")}, {"val": 1})

    def test_nan_raises(self) -> None:
        with pytest.raises(DiffError, match="Non-finite"):
            diff_delta({"val": float("nan")}, {"val": 1})

    def test_non_json_type_raises(self) -> None:
        with pytest.raises(DiffError, match="non-JSON"):
            diff_delta(set(), {})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Exclude keys (flat name, any depth)
# ---------------------------------------------------------------------------


class TestExcludeKeys:
    def test_excluded_top_level_key_no_ops(self) -> None:
        """Excluded keys produce zero operations even when values differ."""
        old = {"name": "Alice", "metadata": {"updated": "2025-01-01"}}
        new = {"name": "Alice", "metadata": {"updated": "2026-03-10"}}
        delta = diff_delta(old, new, exclude_keys={"metadata"})
        assert delta["operations"] == []

    def test_non_excluded_keys_still_diff(self) -> None:
        """Non-excluded keys diff normally when exclude_keys is set."""
        old = {"name": "Alice", "metadata": "old"}
        new = {"name": "Bob", "metadata": "new"}
        delta = diff_delta(old, new, exclude_keys={"metadata"})
        assert len(delta["operations"]) == 1
        assert delta["operations"][0]["path"] == "$.name"
        assert delta["operations"][0]["value"] == "Bob"

    def test_excluded_key_added_no_ops(self) -> None:
        """Adding an excluded key produces no add operation."""
        old = {"name": "Alice"}
        new = {"name": "Alice", "_internal": True}
        delta = diff_delta(old, new, exclude_keys={"_internal"})
        assert delta["operations"] == []

    def test_excluded_key_removed_no_ops(self) -> None:
        """Removing an excluded key produces no remove operation."""
        old = {"name": "Alice", "_internal": True}
        new = {"name": "Alice"}
        delta = diff_delta(old, new, exclude_keys={"_internal"})
        assert delta["operations"] == []

    def test_exclude_inside_keyed_array_elements(self) -> None:
        """Exclusion works at any depth, including inside keyed array elements."""
        old = {"items": [{"id": 1, "name": "Widget", "metadata": {"v": 1}}]}
        new = {"items": [{"id": 1, "name": "Widget", "metadata": {"v": 2}}]}
        delta = diff_delta(old, new, array_identity_keys={"items": "id"}, exclude_keys={"metadata"})
        assert delta["operations"] == []

    def test_exclude_nested_property(self) -> None:
        """Exclusion applies at any depth in nested objects."""
        old = {"a": {"b": {"skip_me": 1, "keep": "old"}}}
        new = {"a": {"b": {"skip_me": 999, "keep": "new"}}}
        delta = diff_delta(old, new, exclude_keys={"skip_me"})
        assert len(delta["operations"]) == 1
        assert delta["operations"][0]["path"] == "$.a.b.keep"

    def test_empty_exclude_keys_same_as_none(self) -> None:
        """Empty set behaves identically to None."""
        old = {"name": "Alice"}
        new = {"name": "Bob"}
        delta_none = diff_delta(old, new, exclude_keys=None)
        delta_empty = diff_delta(old, new, exclude_keys=set())
        assert len(delta_none["operations"]) == len(delta_empty["operations"])
        assert delta_none["operations"][0]["path"] == delta_empty["operations"][0]["path"]

    def test_dotted_key_treated_as_literal_name(self) -> None:
        """Keys with dots are treated as literal property names, not paths."""
        old = {"a.b": 1, "c": 2}
        new = {"a.b": 99, "c": 3}
        delta = diff_delta(old, new, exclude_keys={"a.b"})
        assert len(delta["operations"]) == 1
        assert delta["operations"][0]["path"] == "$.c"

    def test_multiple_excluded_keys(self) -> None:
        """Multiple keys can be excluded simultaneously."""
        old = {"name": "Alice", "etag": "abc", "updated_at": "2025", "age": 30}
        new = {"name": "Bob", "etag": "def", "updated_at": "2026", "age": 31}
        delta = diff_delta(old, new, exclude_keys={"etag", "updated_at"})
        paths = {op["path"] for op in delta["operations"]}
        assert paths == {"$.name", "$.age"}

    def test_exclude_combined_with_reversible(self) -> None:
        """exclude_keys works correctly with reversible=False."""
        old = {"name": "Alice", "meta": "x"}
        new = {"name": "Bob", "meta": "y"}
        delta = diff_delta(old, new, exclude_keys={"meta"}, reversible=False)
        assert len(delta["operations"]) == 1
        assert "oldValue" not in delta["operations"][0]


# ---------------------------------------------------------------------------
# Exclude paths (dotted path, specific depth)
# ---------------------------------------------------------------------------


class TestExcludePaths:
    def test_exclude_path_skips_specific_depth(self) -> None:
        """exclude_paths skips at the exact dotted path depth."""
        old = {"user": {"name": "Alice", "cache": {"stale": True}}}
        new = {"user": {"name": "Bob", "cache": {"stale": False}}}
        delta = diff_delta(old, new, exclude_paths={"user.cache"})
        assert len(delta["operations"]) == 1
        assert delta["operations"][0]["path"] == "$.user.name"

    def test_exclude_path_does_not_match_other_depths(self) -> None:
        """exclude_paths='user.cache' does NOT skip 'product.cache'."""
        old = {"user": {"cache": "a"}, "product": {"cache": "b"}}
        new = {"user": {"cache": "x"}, "product": {"cache": "y"}}
        delta = diff_delta(old, new, exclude_paths={"user.cache"})
        paths = {op["path"] for op in delta["operations"]}
        assert "$.product.cache" in paths
        assert "$.user.cache" not in paths

    def test_exclude_path_nested(self) -> None:
        """Multi-level dotted paths work."""
        old = {"a": {"b": {"c": 1, "d": 2}}}
        new = {"a": {"b": {"c": 99, "d": 99}}}
        delta = diff_delta(old, new, exclude_paths={"a.b.c"})
        assert len(delta["operations"]) == 1
        assert delta["operations"][0]["path"] == "$.a.b.d"

    def test_exclude_path_combined_with_exclude_keys(self) -> None:
        """Both exclude_keys and exclude_paths work together."""
        old = {"user": {"name": "Alice", "cache": "old"}, "meta": "v1"}
        new = {"user": {"name": "Bob", "cache": "new"}, "meta": "v2"}
        delta = diff_delta(old, new, exclude_keys={"meta"}, exclude_paths={"user.cache"})
        assert len(delta["operations"]) == 1
        assert delta["operations"][0]["path"] == "$.user.name"

    def test_exclude_path_inside_keyed_array(self) -> None:
        """exclude_paths works inside keyed array element context."""
        old = {"items": [{"id": 1, "name": "Widget", "temp": "x"}]}
        new = {"items": [{"id": 1, "name": "Gadget", "temp": "y"}]}
        delta = diff_delta(
            old, new,
            array_identity_keys={"items": "id"},
            exclude_paths={"items.temp"},
        )
        assert len(delta["operations"]) == 1
        assert delta["operations"][0]["path"].endswith(".name")


# ---------------------------------------------------------------------------
# Callable identity keys
# ---------------------------------------------------------------------------


class TestCallableIdentityKeys:
    def test_tuple_form_basic(self) -> None:
        """Tuple (key_name, callable) resolves identity via callable."""
        old = {"items": [{"id": 1, "val": 10}]}
        new = {"items": [{"id": 1, "val": 20}]}
        delta = diff_delta(
            old, new,
            array_identity_keys={"items": ("id", lambda e: e["id"])},
        )
        assert len(delta.operations) == 1
        assert "id==1" in delta.operations[0].path
        assert delta.operations[0].path.endswith(".val")

    def test_identity_resolver_dataclass(self) -> None:
        """IdentityResolver dataclass works for custom identity."""
        old = {"items": [{"type": "A", "region": "US", "val": 10}]}
        new = {"items": [{"type": "A", "region": "US", "val": 20}]}
        delta = diff_delta(
            old, new,
            array_identity_keys={
                "items": IdentityResolver("type", lambda e: e["type"]),
            },
        )
        assert len(delta.operations) == 1
        assert "type=='A'" in delta.operations[0].path
        # Round-trip: delta can be applied
        result = apply_delta(deep_clone(old), delta)
        assert result == new

    def test_callable_add_element(self) -> None:
        """Adding an element with callable identity key."""
        old = {"items": [{"id": 1, "name": "Widget"}]}
        new = {"items": [{"id": 1, "name": "Widget"}, {"id": 2, "name": "Gadget"}]}
        delta = diff_delta(
            old, new,
            array_identity_keys={"items": ("id", lambda e: e["id"])},
        )
        add_ops = [op for op in delta.operations if op.op == "add"]
        assert len(add_ops) == 1

    def test_callable_remove_element(self) -> None:
        """Removing an element with callable identity key."""
        old = {"items": [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]}
        new = {"items": [{"id": 1, "name": "A"}]}
        delta = diff_delta(
            old, new,
            array_identity_keys={"items": ("id", lambda e: e["id"])},
        )
        remove_ops = [op for op in delta.operations if op.op == "remove"]
        assert len(remove_ops) == 1

    def test_callable_composite_key(self) -> None:
        """Callable uses actual property value for identity matching."""
        old = {"events": [{"type": "click", "target": "btn", "count": 5}]}
        new = {"events": [{"type": "click", "target": "btn", "count": 10}]}
        delta = diff_delta(
            old, new,
            array_identity_keys={
                "events": ("type", lambda e: e["type"]),
            },
        )
        assert len(delta.operations) == 1
        assert "type=='click'" in delta.operations[0].path
        # Round-trip: delta can be applied
        result = apply_delta(deep_clone(old), delta)
        assert result == new

    def test_callable_roundtrip(self) -> None:
        """Callable identity keys produce valid deltas that round-trip."""
        old = {"items": [{"sku": "A1", "price": 100}]}
        new = {"items": [{"sku": "A1", "price": 90}]}
        delta = diff_delta(
            old, new,
            array_identity_keys={"items": ("sku", lambda e: e["sku"])},
        )
        result = apply_delta(deep_clone(old), delta)
        assert result == new

    def test_resolver_error_wrapped(self) -> None:
        """Resolver exceptions are wrapped in DiffError with context."""
        import pytest
        from json_atom.errors import DiffError
        with pytest.raises(DiffError, match="Identity resolver.*failed"):
            diff_delta(
                {"items": [{"id": 1, "v": "a"}]},
                {"items": [{"id": 1, "v": "b"}]},
                array_identity_keys={"items": ("id", lambda e: e["missing_key"])},
            )

    def test_resolver_non_scalar_rejected(self) -> None:
        """Resolver returning a non-scalar value raises DiffError."""
        import pytest
        from json_atom.errors import DiffError
        with pytest.raises(DiffError, match="filter path would not match"):
            diff_delta(
                {"items": [{"id": 1, "v": "a"}]},
                {"items": [{"id": 1, "v": "b"}]},
                array_identity_keys={"items": ("id", lambda e: {"composite": True})},
            )


class TestNestedPathIdentityKeys:
    """Nested dot-path identity keys (e.g. positionNumber.value → @.positionNumber.value)."""

    def test_nested_path_string_key(self) -> None:
        """String key with dots resolves nested path."""
        old = {"items": [
            {"positionNumber": {"value": "001"}, "description": "alpha"},
            {"positionNumber": {"value": "002"}, "description": "beta"},
        ]}
        new = {"items": [
            {"positionNumber": {"value": "001"}, "description": "alpha"},
        ]}
        delta = diff_delta(old, new, array_identity_keys={"items": "positionNumber.value"})
        remove_ops = [op for op in delta.operations if op.op == "remove"]
        assert len(remove_ops) == 1
        assert remove_ops[0].path == "$.items[?(@.positionNumber.value=='002')]"

    def test_nested_path_resolver(self) -> None:
        """IdentityResolver with nested path produces dot notation."""
        old = {"items": [
            {"positionNumber": {"value": "001"}, "description": "alpha"},
            {"positionNumber": {"value": "002"}, "description": "beta"},
        ]}
        new = {"items": [
            {"positionNumber": {"value": "001"}, "description": "alpha"},
            {"positionNumber": {"value": "003"}, "description": "gamma"},
        ]}
        delta = diff_delta(old, new, array_identity_keys={
            "items": IdentityResolver(
                "positionNumber.value",
                lambda e: e["positionNumber"]["value"],
            ),
        })
        assert len(delta.operations) == 2
        removes = [op for op in delta.operations if op.op == "remove"]
        adds = [op for op in delta.operations if op.op == "add"]
        assert len(removes) == 1
        assert removes[0].path == "$.items[?(@.positionNumber.value=='002')]"
        assert len(adds) == 1
        assert adds[0].path == "$.items[?(@.positionNumber.value=='003')]"

    def test_nested_path_update_within_element(self) -> None:
        """Update a property inside an element with nested identity path."""
        old = {"items": [
            {"positionNumber": {"value": "001"}, "description": "alpha"},
            {"positionNumber": {"value": "002"}, "description": "beta"},
        ]}
        new = {"items": [
            {"positionNumber": {"value": "001"}, "description": "alpha"},
            {"positionNumber": {"value": "002"}, "description": "updated"},
        ]}
        delta = diff_delta(old, new, array_identity_keys={
            "items": "positionNumber.value",
        })
        assert len(delta.operations) == 1
        assert delta.operations[0].op == "replace"
        assert delta.operations[0].path == "$.items[?(@.positionNumber.value=='002')].description"
        assert delta.operations[0]["value"] == "updated"

    def test_nested_path_roundtrip(self) -> None:
        """Nested path identity produces deltas that round-trip."""
        old = {"items": [
            {"positionNumber": {"value": "001"}, "description": "alpha"},
            {"positionNumber": {"value": "002"}, "description": "beta"},
        ]}
        new = {"items": [
            {"positionNumber": {"value": "001"}, "description": "alpha"},
            {"positionNumber": {"value": "003"}, "description": "gamma"},
        ]}
        delta = diff_delta(old, new, array_identity_keys={
            "items": "positionNumber.value",
        })
        result = apply_delta(deep_clone(old), delta)
        assert result == new


# ---------------------------------------------------------------------------
# Regex-based array key routing
# ---------------------------------------------------------------------------


class TestRegexPatternRouting:
    def test_regex_matches_array_path(self) -> None:
        """Regex pattern matches the dotted property path."""
        old = {"users": [{"id": 1, "name": "Alice"}]}
        new = {"users": [{"id": 1, "name": "Bob"}]}
        delta = diff_delta(
            old, new,
            array_identity_keys={re.compile(r"^users$"): "id"},
        )
        assert len(delta.operations) == 1
        assert "id==1" in delta.operations[0].path

    def test_regex_matches_multiple_arrays(self) -> None:
        """One regex pattern can match multiple array paths."""
        old = {"users": [{"id": 1, "name": "A"}], "products": [{"id": 1, "title": "X"}]}
        new = {"users": [{"id": 1, "name": "B"}], "products": [{"id": 1, "title": "Y"}]}
        delta = diff_delta(
            old, new,
            array_identity_keys={re.compile(r"^(users|products)$"): "id"},
        )
        assert all("id==1" in op.path for op in delta.operations)

    def test_exact_string_takes_priority_over_regex(self) -> None:
        """Exact string match is checked before regex patterns."""
        old = {"items": [{"id": 1, "val": 10}]}
        new = {"items": [{"id": 1, "val": 20}]}
        delta = diff_delta(
            old, new,
            array_identity_keys={
                "items": "id",
                re.compile(r"items"): "$value",  # would fail if matched
            },
        )
        assert "id==1" in delta.operations[0].path

    def test_regex_with_callable_value(self) -> None:
        """Regex key + callable identity value."""
        old = {"data": {"items": [{"sku": "A", "price": 10}]}}
        new = {"data": {"items": [{"sku": "A", "price": 20}]}}
        delta = diff_delta(
            old, new,
            array_identity_keys={
                re.compile(r"items$"): ("sku", lambda e: e["sku"]),
            },
        )
        assert len(delta.operations) == 1
        assert "sku=='A'" in delta.operations[0].path

    def test_no_match_falls_back_to_index(self) -> None:
        """When no string or regex matches, falls back to $index."""
        old = {"tags": ["a", "b"]}
        new = {"tags": ["a", "c"]}
        delta = diff_delta(
            old, new,
            array_identity_keys={re.compile(r"^items$"): "id"},
        )
        assert delta.operations[0].path == "$.tags[1]"


# ---------------------------------------------------------------------------
# Conformance: apply(source, diff(source, target)) == target
# ---------------------------------------------------------------------------


class TestDiffConformance:
    def test_basic_replace_apply_roundtrip(self) -> None:
        fixture = load_fixture("basic-replace")
        source = fixture["source"]
        target = fixture["target"]
        delta = diff_delta(source, target)
        result = apply_delta(deep_clone(source), delta)
        assert result == target

    def test_keyed_array_apply_roundtrip(self) -> None:
        fixture = load_fixture("keyed-array-update")
        source = fixture["source"]
        target = fixture["target"]
        hints = fixture.get("computeHints", {})
        array_identity_keys = hints.get("arrayKeys")
        delta = diff_delta(source, target, array_identity_keys=array_identity_keys)
        result = apply_delta(deep_clone(source), delta)
        assert result == target

    def test_keyed_array_invert_roundtrip(self) -> None:
        """diff + invert + apply round-trip: apply(target, invert(diff(source, target))) == source."""
        fixture = load_fixture("keyed-array-update")
        source = fixture["source"]
        target = fixture["target"]
        hints = fixture.get("computeHints", {})
        array_identity_keys = hints.get("arrayKeys")
        delta = diff_delta(source, target, array_identity_keys=array_identity_keys)
        inverse = invert_delta(delta)
        recovered = apply_delta(deep_clone(target), inverse)
        assert recovered == source


# ---------------------------------------------------------------------------
# Duplicate identity detection
# ---------------------------------------------------------------------------


class TestDuplicateIdentity:
    def test_duplicate_in_old_raises(self) -> None:
        """Duplicate identity keys in old array raise DiffError."""
        import pytest
        from json_atom.errors import DiffError
        with pytest.raises(DiffError, match="Duplicate identity"):
            diff_delta(
                {"items": [{"id": 1, "v": "a"}, {"id": 1, "v": "b"}]},
                {"items": [{"id": 1, "v": "a"}]},
                array_identity_keys={"items": "id"},
            )

    def test_duplicate_in_new_raises(self) -> None:
        """Duplicate identity keys in new array raise DiffError."""
        import pytest
        from json_atom.errors import DiffError
        with pytest.raises(DiffError, match="Duplicate identity"):
            diff_delta(
                {"items": [{"id": 1, "v": "a"}]},
                {"items": [{"id": 1, "v": "a"}, {"id": 1, "v": "b"}]},
                array_identity_keys={"items": "id"},
            )


# ---------------------------------------------------------------------------
# Value-based duplicate detection
# ---------------------------------------------------------------------------


class TestValueDuplicates:
    def test_duplicate_in_new_raises(self) -> None:
        """$value identity rejects duplicates in new array."""
        import pytest
        from json_atom.errors import DiffError
        with pytest.raises(DiffError, match="Duplicate value.*\\$value identity requires unique"):
            diff_delta(
                {"tags": ["a"]},
                {"tags": ["a", "a"]},
                array_identity_keys={"tags": "$value"},
            )

    def test_duplicate_in_old_raises(self) -> None:
        """$value identity rejects duplicates in old array."""
        import pytest
        from json_atom.errors import DiffError
        with pytest.raises(DiffError, match="Duplicate value.*\\$value identity requires unique"):
            diff_delta(
                {"tags": ["a", "a"]},
                {"tags": ["a"]},
                array_identity_keys={"tags": "$value"},
            )

    def test_duplicate_in_both_raises(self) -> None:
        """$value identity rejects duplicates even when both sides differ."""
        import pytest
        from json_atom.errors import DiffError
        with pytest.raises(DiffError, match="Duplicate value.*\\$value identity requires unique"):
            diff_delta(
                {"tags": ["a", "a", "b"]},
                {"tags": ["a", "a", "c"]},
                array_identity_keys={"tags": "$value"},
            )

    def test_unique_values_work(self) -> None:
        """$value identity works correctly with unique values."""
        delta = diff_delta(
            {"tags": ["a", "b"]},
            {"tags": ["a", "c"]},
            array_identity_keys={"tags": "$value"},
        )
        add_ops = [op for op in delta.operations if op.op == "add"]
        remove_ops = [op for op in delta.operations if op.op == "remove"]
        assert len(add_ops) == 1
        assert len(remove_ops) == 1

    def test_non_scalar_in_old_raises(self) -> None:
        """$value identity rejects non-scalar elements in old array."""
        import pytest
        from json_atom.errors import DiffError
        with pytest.raises(DiffError, match="Non-scalar value.*\\$value identity requires scalar"):
            diff_delta(
                {"tags": [{"x": 1}]},
                {"tags": ["a"]},
                array_identity_keys={"tags": "$value"},
            )

    def test_non_scalar_in_new_raises(self) -> None:
        """$value identity rejects non-scalar elements in new array."""
        import pytest
        from json_atom.errors import DiffError
        with pytest.raises(DiffError, match="Non-scalar value.*\\$value identity requires scalar"):
            diff_delta(
                {"tags": ["a"]},
                {"tags": [["nested"]]},
                array_identity_keys={"tags": "$value"},
            )


# ---------------------------------------------------------------------------
# squash_deltas
# ---------------------------------------------------------------------------


class TestSquashDeltas:
    def test_two_property_changes(self) -> None:
        from json_atom.diff import squash_deltas
        source = {"name": "Alice", "age": 30}
        d1 = diff_delta(source, {"name": "Bob", "age": 30})
        intermediate = apply_delta(deep_clone(source), d1)
        d2 = diff_delta(intermediate, {"name": "Bob", "age": 31})
        squashed = squash_deltas(source, d1, d2)
        result = apply_delta(deep_clone(source), squashed)
        assert result == {"name": "Bob", "age": 31}

    def test_add_then_remove_cancels(self) -> None:
        from json_atom.diff import squash_deltas
        source = {"x": 1}
        d1 = diff_delta(source, {"x": 1, "y": 2})
        intermediate = apply_delta(deep_clone(source), d1)
        d2 = diff_delta(intermediate, {"x": 1})
        squashed = squash_deltas(source, d1, d2)
        assert squashed.is_empty

    def test_empty_deltas(self) -> None:
        from json_atom.diff import squash_deltas
        source = {"x": 1}
        squashed = squash_deltas(source)
        assert squashed.is_empty

    def test_single_delta(self) -> None:
        from json_atom.diff import squash_deltas
        source = {"x": 1}
        d1 = diff_delta(source, {"x": 2})
        squashed = squash_deltas(source, d1)
        result = apply_delta(deep_clone(source), squashed)
        assert result == {"x": 2}

    def test_keyed_array(self) -> None:
        from json_atom.diff import squash_deltas
        keys = {"items": "id"}
        source = {"items": [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]}
        d1 = diff_delta(
            source,
            {"items": [{"id": 1, "name": "A2"}, {"id": 2, "name": "B"}]},
            array_identity_keys=keys,
        )
        intermediate = apply_delta(deep_clone(source), d1)
        d2 = diff_delta(
            intermediate,
            {"items": [{"id": 1, "name": "A2"}, {"id": 2, "name": "B2"}]},
            array_identity_keys=keys,
        )
        squashed = squash_deltas(source, d1, d2, array_identity_keys=keys)
        result = apply_delta(deep_clone(source), squashed)
        assert result == {"items": [{"id": 1, "name": "A2"}, {"id": 2, "name": "B2"}]}

    def test_envelope_extension_merge(self) -> None:
        from json_atom.diff import squash_deltas
        from json_atom.models import Delta, Operation
        source = {"x": 1}
        d1 = Delta.create(Operation.replace("$.x", 2, old_value=1), x_author="alice")
        d2 = Delta.create(Operation.replace("$.x", 3, old_value=2), x_author="bob", x_ts="now")
        squashed = squash_deltas(source, d1, d2)
        assert squashed["x_author"] == "bob"  # last-wins
        assert squashed["x_ts"] == "now"

    def test_direct_source_target(self) -> None:
        from json_atom.diff import squash_deltas
        source = {"x": 1, "y": 2}
        target = {"x": 3, "y": 2}
        squashed = squash_deltas(source, target=target)
        result = apply_delta(deep_clone(source), squashed)
        assert result == target

    def test_verify_target_raises_on_mismatch(self) -> None:
        from json_atom.diff import squash_deltas
        from json_atom.models import Delta, Operation
        source = {"x": 1}
        d1 = Delta.create(Operation.replace("$.x", 2, old_value=1))
        wrong_target = {"x": 99}
        # verify_target=True is the default — mismatched target raises
        with pytest.raises(DiffError, match="does not match"):
            squash_deltas(source, d1, target=wrong_target)

    def test_verify_target_passes_on_match(self) -> None:
        from json_atom.diff import squash_deltas
        source = {"x": 1}
        d1 = diff_delta(source, {"x": 2})
        # verify_target=True is the default — correct target passes
        squashed = squash_deltas(source, d1, target={"x": 2})
        result = apply_delta(deep_clone(source), squashed)
        assert result == {"x": 2}

    def test_verify_target_false_skips_check(self) -> None:
        from json_atom.diff import squash_deltas
        from json_atom.models import Delta, Operation
        source = {"x": 1}
        d1 = Delta.create(Operation.replace("$.x", 2, old_value=1))
        wrong_target = {"x": 99}
        # verify_target=False trusts the caller — wrong target silently accepted
        squashed = squash_deltas(source, d1, target=wrong_target, verify_target=False)
        # Result is diff(source, wrong_target), not diff(source, apply(source, d1))
        result = apply_delta(deep_clone(source), squashed)
        assert result == {"x": 99}

    def test_reversible_false(self) -> None:
        from json_atom.diff import squash_deltas
        source = {"x": 1}
        d1 = diff_delta(source, {"x": 2})
        squashed = squash_deltas(source, d1, reversible=False)
        assert not squashed.is_reversible

    def test_delta_squash_classmethod(self) -> None:
        from json_atom.models import Delta
        source = {"x": 1}
        d1 = diff_delta(source, {"x": 2})
        intermediate = apply_delta(deep_clone(source), d1)
        d2 = diff_delta(intermediate, {"x": 3})
        squashed = Delta.squash(source, d1, d2)
        result = apply_delta(deep_clone(source), squashed)
        assert result == {"x": 3}
