"""Cross-validation tests: verify json-atom-py produces the same results as json-diff-ts.

These tests replicate key test cases from json-diff-ts/tests/jsonDelta.test.ts
to verify behavioral equivalence between the TypeScript and Python implementations.
"""

import copy

import pytest

from json_atom import (
    apply_delta,
    diff_delta,
    invert_delta,
    revert_delta,
    validate_delta,
)

# ─── Helpers ────────────────────────────────────────────────────────────────


def deep_clone(obj):
    """JSON-style deep clone (matches JSON.parse(JSON.stringify(x)) in TS)."""
    import json

    return json.loads(json.dumps(obj))


# ─── validateDelta (mirrors jsonDelta.test.ts → validateDelta) ────────────


class TestValidateDeltaCrossValidation:
    """TS: describe('validateDelta', ...)"""

    def test_validates_correct_delta(self):
        """TS: it('validates a correct delta')"""
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [{"op": "replace", "path": "$.name", "value": "Bob", "oldValue": "Alice"}],
        }
        result = validate_delta(delta)
        assert result.valid is True
        assert result.errors == ()

    def test_validates_delta_with_x_extension_properties(self):
        """TS: it('validates delta with x_ extension properties')"""
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [{"op": "replace", "path": "$.name", "value": "Bob", "x_author": "system"}],
            "x_metadata": {"timestamp": 123},
        }
        result = validate_delta(delta)
        assert result.valid is True
        assert result.errors == ()

    def test_validates_delta_with_empty_operations(self):
        """TS: it('validates delta with empty operations')"""
        delta = {"format": "json-atom", "version": 1, "operations": []}
        result = validate_delta(delta)
        assert result.valid is True

    def test_rejects_missing_format(self):
        """TS: it('rejects missing format')"""
        result = validate_delta({"version": 1, "operations": []})
        assert result.valid is False
        assert any("format" in e for e in result.errors)

    def test_rejects_wrong_format(self):
        """TS: it('rejects wrong format')"""
        result = validate_delta({"format": "json-patch", "version": 1, "operations": []})
        assert result.valid is False

    def test_rejects_missing_version(self):
        """TS: it('rejects missing version')"""
        result = validate_delta({"format": "json-atom", "operations": []})
        assert result.valid is False
        assert any("version" in e for e in result.errors)

    def test_rejects_missing_operations(self):
        """TS: it('rejects missing operations')"""
        result = validate_delta({"format": "json-atom", "version": 1})
        assert result.valid is False
        assert any("operations" in e for e in result.errors)

    def test_rejects_invalid_op(self):
        """TS: it('rejects invalid op')"""
        result = validate_delta({
            "format": "json-atom",
            "version": 1,
            "operations": [{"op": "move", "path": "$.x"}],
        })
        assert result.valid is False

    def test_rejects_add_with_old_value(self):
        """TS: it('rejects add with oldValue')"""
        result = validate_delta({
            "format": "json-atom",
            "version": 1,
            "operations": [{"op": "add", "path": "$.x", "value": 1, "oldValue": 0}],
        })
        assert result.valid is False

    def test_rejects_remove_with_value(self):
        """TS: it('rejects remove with value')"""
        result = validate_delta({
            "format": "json-atom",
            "version": 1,
            "operations": [{"op": "remove", "path": "$.x", "value": 1}],
        })
        assert result.valid is False

    def test_rejects_add_without_value(self):
        """TS: it('rejects add without value')"""
        result = validate_delta({
            "format": "json-atom",
            "version": 1,
            "operations": [{"op": "add", "path": "$.x"}],
        })
        assert result.valid is False

    def test_rejects_replace_without_value(self):
        """TS: it('rejects replace without value')"""
        result = validate_delta({
            "format": "json-atom",
            "version": 1,
            "operations": [{"op": "replace", "path": "$.x", "oldValue": 1}],
        })
        assert result.valid is False

    def test_rejects_non_object(self):
        """TS: it('rejects non-object')"""
        assert validate_delta(None).valid is False
        assert validate_delta("string").valid is False
        assert validate_delta(42).valid is False

    def test_rejects_non_object_operation_entries(self):
        """TS: it('rejects non-object operation entries')"""
        result = validate_delta({
            "format": "json-atom",
            "version": 1,
            "operations": [None, "not-an-object"],
        })
        assert result.valid is False
        assert any("must be" in e.lower() or "object" in e.lower() or "dict" in e.lower() for e in result.errors)

    def test_rejects_operation_with_non_string_path(self):
        """TS: it('rejects operation with non-string path')"""
        result = validate_delta({
            "format": "json-atom",
            "version": 1,
            "operations": [{"op": "add", "path": 123, "value": "x"}],
        })
        assert result.valid is False
        assert any("path" in e.lower() and "string" in e.lower() for e in result.errors)


# ─── diffDelta (mirrors jsonDelta.test.ts → diffDelta) ───────────────────


class TestDiffDeltaCrossValidation:
    """TS: describe('diffDelta', ...)"""

    def test_empty_operations_for_identical_objects(self):
        """TS: it('produces empty operations for identical objects')"""
        obj = {"a": 1, "b": "hello"}
        delta = diff_delta(obj, deep_clone(obj))
        assert delta["format"] == "json-atom"
        assert delta["version"] == 1
        assert delta["operations"] == []

    def test_simple_property_replace(self):
        """TS: it('detects simple property replace')"""
        delta = diff_delta({"name": "Alice"}, {"name": "Bob"})
        assert delta["operations"] == [
            {"op": "replace", "path": "$.name", "value": "Bob", "oldValue": "Alice"},
        ]

    def test_property_add(self):
        """TS: it('detects property add')"""
        delta = diff_delta({"a": 1}, {"a": 1, "b": 2})
        assert len(delta["operations"]) == 1
        assert delta["operations"][0] == {"op": "add", "path": "$.b", "value": 2}

    def test_property_remove(self):
        """TS: it('detects property remove')"""
        delta = diff_delta({"a": 1, "b": 2}, {"a": 1})
        assert len(delta["operations"]) == 1
        op = delta["operations"][0]
        assert op["op"] == "remove"
        assert op["path"] == "$.b"
        assert op["oldValue"] == 2

    def test_nested_object_changes(self):
        """TS: it('handles nested object changes')"""
        delta = diff_delta(
            {"user": {"name": "Alice", "address": {"city": "Portland"}}},
            {"user": {"name": "Alice", "address": {"city": "Seattle"}}},
        )
        assert delta["operations"] == [
            {"op": "replace", "path": "$.user.address.city", "value": "Seattle", "oldValue": "Portland"},
        ]

    def test_arrays_with_index_default(self):
        """TS: it('handles arrays with $index (default)')"""
        delta = diff_delta({"items": [1, 2, 3]}, {"items": [1, 2, 4]})
        assert len(delta["operations"]) == 1
        op = delta["operations"][0]
        assert op["op"] == "replace"
        assert op["path"] == "$.items[2]"
        assert op["value"] == 4
        assert op["oldValue"] == 3

    def test_arrays_with_named_key_string_ids(self):
        """TS: it('handles arrays with named key (string IDs)')"""
        delta = diff_delta(
            {"items": [{"id": "1", "name": "Widget"}]},
            {"items": [{"id": "1", "name": "Gadget"}]},
            array_identity_keys={"items": "id"},
        )
        assert delta["operations"] == [
            {"op": "replace", "path": "$.items[?(@.id=='1')].name", "value": "Gadget", "oldValue": "Widget"},
        ]

    def test_arrays_with_named_key_numeric_ids(self):
        """TS: it('handles arrays with named key (numeric IDs) — canonical typed literals')"""
        delta = diff_delta(
            {"items": [{"id": 1, "name": "Widget"}]},
            {"items": [{"id": 1, "name": "Gadget"}]},
            array_identity_keys={"items": "id"},
        )
        assert delta["operations"] == [
            {"op": "replace", "path": "$.items[?(@.id==1)].name", "value": "Gadget", "oldValue": "Widget"},
        ]

    def test_keyed_array_add_and_remove(self):
        """TS: it('handles keyed array add and remove')"""
        delta = diff_delta(
            {"items": [{"id": "1", "name": "Widget"}]},
            {"items": [{"id": "1", "name": "Widget"}, {"id": "2", "name": "Gadget"}]},
            array_identity_keys={"items": "id"},
        )
        assert len(delta["operations"]) == 1
        op = delta["operations"][0]
        assert op["op"] == "add"
        assert op["path"] == "$.items[?(@.id=='2')]"
        assert op["value"] == {"id": "2", "name": "Gadget"}

    def test_value_arrays_with_string_values(self):
        """TS: it('handles $value arrays with string values')"""
        delta = diff_delta(
            {"tags": ["urgent", "review"]},
            {"tags": ["urgent", "draft"]},
            array_identity_keys={"tags": "$value"},
        )
        assert len(delta["operations"]) == 2
        remove_op = next(op for op in delta["operations"] if op["op"] == "remove")
        add_op = next(op for op in delta["operations"] if op["op"] == "add")
        assert remove_op["path"] == "$.tags[?(@=='review')]"
        assert add_op["path"] == "$.tags[?(@=='draft')]"

    def test_value_arrays_with_numeric_values(self):
        """TS: it('handles $value arrays with numeric values')"""
        delta = diff_delta(
            {"scores": [10, 20, 30]},
            {"scores": [10, 25, 30]},
            array_identity_keys={"scores": "$value"},
        )
        assert len(delta["operations"]) == 2
        remove_op = next(op for op in delta["operations"] if op["op"] == "remove")
        add_op = next(op for op in delta["operations"] if op["op"] == "add")
        assert remove_op["path"] == "$.scores[?(@==20)]"
        assert add_op["path"] == "$.scores[?(@==25)]"

    def test_type_change_produces_single_replace(self):
        """TS: it('type changes produce single replace (not REMOVE+ADD)')"""
        delta = diff_delta({"a": "hello"}, {"a": 42})
        assert len(delta["operations"]) == 1
        op = delta["operations"][0]
        assert op["op"] == "replace"
        assert op["path"] == "$.a"
        assert op["value"] == 42
        assert op["oldValue"] == "hello"

    def test_object_to_array_type_change(self):
        """TS: it('Object→Array type change produces single replace')"""
        delta = diff_delta({"a": {"x": 1}}, {"a": [1, 2]})
        assert len(delta["operations"]) == 1
        op = delta["operations"][0]
        assert op["op"] == "replace"
        assert op["path"] == "$.a"
        assert op["value"] == [1, 2]
        assert op["oldValue"] == {"x": 1}

    def test_array_to_object_type_change(self):
        """TS: it('Array→Object type change produces single replace')"""
        delta = diff_delta({"a": [1, 2]}, {"a": {"x": 1}})
        assert len(delta["operations"]) == 1
        assert delta["operations"][0]["op"] == "replace"

    def test_null_to_object_produces_replace(self):
        """TS: it('null→Object produces single replace')"""
        delta = diff_delta({"a": None}, {"a": {"x": 1}})
        assert len(delta["operations"]) == 1
        op = delta["operations"][0]
        assert op["op"] == "replace"
        assert op["path"] == "$.a"
        assert op["value"] == {"x": 1}
        assert op["oldValue"] is None

    def test_replace_with_null_value(self):
        """TS: it('replace with null value')"""
        delta = diff_delta({"a": 42}, {"a": None})
        assert len(delta["operations"]) == 1
        op = delta["operations"][0]
        assert op["op"] == "replace"
        assert op["path"] == "$.a"
        assert op["value"] is None
        assert op["oldValue"] == 42

    def test_omits_old_value_when_reversible_false(self):
        """TS: it('omits oldValue when reversible is false')"""
        delta = diff_delta({"name": "Alice"}, {"name": "Bob"}, reversible=False)
        assert delta["operations"][0] == {"op": "replace", "path": "$.name", "value": "Bob"}
        assert "oldValue" not in delta["operations"][0]

    def test_nested_property_names_with_dots_bracket_notation(self):
        """TS: it('handles nested property names with dots (bracket notation)')"""
        delta = diff_delta({"a.b": 1}, {"a.b": 2})
        assert len(delta["operations"]) == 1
        assert delta["operations"][0]["path"] == "$['a.b']"

    def test_deep_path_in_index_arrays(self):
        """TS: it('handles deep path in $index arrays')"""
        delta = diff_delta(
            {"items": [{"name": "Widget", "color": "red"}]},
            {"items": [{"name": "Widget", "color": "blue"}]},
        )
        assert len(delta["operations"]) == 1
        assert delta["operations"][0]["path"] == "$.items[0].color"


# ─── applyDelta (mirrors jsonDelta.test.ts → applyDelta) ─────────────────


class TestApplyDeltaCrossValidation:
    """TS: describe('applyDelta', ...)"""

    def test_simple_property_changes(self):
        """TS: it('applies simple property changes')"""
        obj = {"name": "Alice", "age": 30}
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "replace", "path": "$.name", "value": "Bob", "oldValue": "Alice"},
            ],
        }
        result = apply_delta(obj, delta)
        assert result == {"name": "Bob", "age": 30}

    def test_add_and_remove(self):
        """TS: it('applies add and remove')"""
        obj = {"a": 1, "b": 2}
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "remove", "path": "$.b", "oldValue": 2},
                {"op": "add", "path": "$.c", "value": 3},
            ],
        }
        result = apply_delta(obj, delta)
        assert result == {"a": 1, "c": 3}

    def test_keyed_array_operations(self):
        """TS: it('applies keyed array operations')"""
        obj = {
            "items": [
                {"id": "1", "name": "Widget", "price": 10},
                {"id": "2", "name": "Gadget", "price": 20},
            ],
        }
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "replace", "path": "$.items[?(@.id=='1')].name", "value": "Widget Pro", "oldValue": "Widget"},
            ],
        }
        result = apply_delta(obj, delta)
        assert result["items"][0]["name"] == "Widget Pro"

    def test_root_add_from_null(self):
        """TS: it('applies root add (from null)')"""
        result = apply_delta(None, {
            "format": "json-atom",
            "version": 1,
            "operations": [{"op": "add", "path": "$", "value": {"hello": "world"}}],
        })
        assert result == {"hello": "world"}

    def test_root_remove_to_null(self):
        """TS: it('applies root remove (to null)')"""
        result = apply_delta({"hello": "world"}, {
            "format": "json-atom",
            "version": 1,
            "operations": [{"op": "remove", "path": "$", "oldValue": {"hello": "world"}}],
        })
        assert result is None

    def test_root_replace(self):
        """TS: it('applies root replace')"""
        result = apply_delta(
            {"old": True},
            {
                "format": "json-atom",
                "version": 1,
                "operations": [{"op": "replace", "path": "$", "value": {"new": True}, "oldValue": {"old": True}}],
            },
        )
        assert result == {"new": True}

    def test_root_replace_with_primitive(self):
        """TS: it('root replace with primitive returns new value')"""
        result = apply_delta(
            "old",
            {
                "format": "json-atom",
                "version": 1,
                "operations": [{"op": "replace", "path": "$", "value": "new", "oldValue": "old"}],
            },
        )
        assert result == "new"

    def test_root_replace_object_with_array(self):
        """TS: it('root replace object with array returns array')"""
        result = apply_delta(
            {"old": True},
            {
                "format": "json-atom",
                "version": 1,
                "operations": [{"op": "replace", "path": "$", "value": [1, 2, 3], "oldValue": {"old": True}}],
            },
        )
        assert result == [1, 2, 3]
        assert isinstance(result, list)

    def test_root_replace_array_with_object(self):
        """TS: it('root replace array with object returns plain object')"""
        result = apply_delta(
            [1, 2, 3],
            {
                "format": "json-atom",
                "version": 1,
                "operations": [{"op": "replace", "path": "$", "value": {"new": True}, "oldValue": [1, 2, 3]}],
            },
        )
        assert result == {"new": True}
        assert not isinstance(result, list)

    def test_root_replace_array_with_array(self):
        """TS: it('root replace array with array returns new array')"""
        result = apply_delta(
            [1, 2],
            {
                "format": "json-atom",
                "version": 1,
                "operations": [{"op": "replace", "path": "$", "value": [3, 4, 5], "oldValue": [1, 2]}],
            },
        )
        assert result == [3, 4, 5]
        assert isinstance(result, list)

    def test_sequential_operations_order_matters(self):
        """TS: it('applies operations sequentially (order matters)')"""
        obj = {"items": ["a", "b", "c"]}
        # Remove index 1 ('b'), array becomes ['a', 'c']
        # Then replace index 1 (now 'c') with 'd'
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "remove", "path": "$.items[1]", "oldValue": "b"},
                {"op": "replace", "path": "$.items[1]", "value": "d", "oldValue": "c"},
            ],
        }
        result = apply_delta(obj, delta)
        assert result["items"] == ["a", "d"]

    def test_throws_on_invalid_delta(self):
        """TS: it('throws on invalid delta')"""
        with pytest.raises(Exception):
            apply_delta({}, {"format": "wrong"})


# ─── revertDelta (mirrors jsonDelta.test.ts → revertDelta) ───────────────


class TestRevertDeltaCrossValidation:
    """TS: describe('revertDelta', ...)"""

    def test_full_round_trip(self):
        """TS: it('full round-trip: source → applyDelta → revertDelta == source')"""
        source = {"name": "Alice", "age": 30, "tags": ["admin"]}
        target = {"name": "Bob", "age": 31, "tags": ["admin", "user"]}
        delta = diff_delta(source, target, array_identity_keys={"tags": "$value"})

        applied = apply_delta(deep_clone(source), delta)
        assert applied == target

        reverted = revert_delta(deep_clone(applied), delta)
        assert reverted == source

    def test_throws_on_non_reversible_delta(self):
        """TS: it('throws on non-reversible delta (missing oldValue)')"""
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [{"op": "replace", "path": "$.name", "value": "Bob"}],
        }
        with pytest.raises(Exception, match="(?i)reversible|oldValue"):
            revert_delta({"name": "Alice"}, delta)


# ─── invertDelta (mirrors jsonDelta.test.ts → invertDelta) ───────────────


class TestInvertDeltaCrossValidation:
    """TS: describe('invertDelta', ...)"""

    def test_inverts_add_to_remove(self):
        """TS: it('inverts add → remove')"""
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [{"op": "add", "path": "$.x", "value": 42}],
        }
        inverse = invert_delta(delta)
        assert inverse["operations"] == [{"op": "remove", "path": "$.x", "oldValue": 42}]

    def test_inverts_remove_to_add(self):
        """TS: it('inverts remove → add')"""
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [{"op": "remove", "path": "$.x", "oldValue": 42}],
        }
        inverse = invert_delta(delta)
        assert inverse["operations"] == [{"op": "add", "path": "$.x", "value": 42}]

    def test_inverts_replace_swaps_values(self):
        """TS: it('inverts replace (swaps value and oldValue)')"""
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [{"op": "replace", "path": "$.name", "value": "Bob", "oldValue": "Alice"}],
        }
        inverse = invert_delta(delta)
        assert inverse["operations"] == [
            {"op": "replace", "path": "$.name", "value": "Alice", "oldValue": "Bob"},
        ]

    def test_reverses_operation_order(self):
        """TS: it('reverses operation order')"""
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "add", "path": "$.a", "value": 1},
                {"op": "add", "path": "$.b", "value": 2},
            ],
        }
        inverse = invert_delta(delta)
        assert inverse["operations"][0]["path"] == "$.b"
        assert inverse["operations"][1]["path"] == "$.a"

    def test_throws_when_replace_missing_old_value(self):
        """TS: it('throws when replace missing oldValue')"""
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [{"op": "replace", "path": "$.x", "value": 42}],
        }
        with pytest.raises(Exception, match="(?i)reversible|oldValue"):
            invert_delta(delta)

    def test_throws_when_remove_missing_old_value(self):
        """TS: it('throws when remove missing oldValue')"""
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [{"op": "remove", "path": "$.x"}],
        }
        with pytest.raises(Exception, match="(?i)reversible|oldValue"):
            invert_delta(delta)

    def test_preserves_envelope_extension_properties(self):
        """TS: it('preserves envelope extension properties')"""
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [{"op": "add", "path": "$.x", "value": 1}],
            "x_source": "test",
        }
        inverse = invert_delta(delta)
        assert inverse["x_source"] == "test"
        assert inverse["format"] == "json-atom"

    def test_preserves_operation_level_extension_properties(self):
        """TS: it('preserves operation-level extension properties')"""
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [{"op": "add", "path": "$.x", "value": 1, "x_author": "alice"}],
        }
        inverse = invert_delta(delta)
        assert inverse["operations"][0]["x_author"] == "alice"

    def test_throws_on_invalid_delta_input(self):
        """TS: it('throws on invalid delta input')"""
        with pytest.raises(Exception):
            invert_delta({"format": "wrong"})


# ─── Extension property preservation (mirrors jsonDelta.test.ts) ─────────


class TestExtensionCrossValidation:
    """TS: describe('extension property preservation', ...)"""

    def test_apply_delta_ignores_extensions(self):
        """TS: it('applyDelta ignores extension properties without error')"""
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "replace", "path": "$.name", "value": "Bob", "oldValue": "Alice", "x_reason": "rename"}
            ],
            "x_metadata": {"ts": 123},
        }
        result = apply_delta({"name": "Alice"}, delta)
        assert result == {"name": "Bob"}


# ─── Conformance fixtures (mirrors jsonDelta.test.ts → conformance) ──────


class TestConformanceCrossValidation:
    """TS: describe('conformance fixtures', ...)"""

    def test_basic_replace_level_1(self):
        """TS: it('Level 1: applyDelta(source, delta) == target')"""
        source = {"name": "Alice", "age": 30}
        target = {"name": "Bob", "age": 30}
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "replace", "path": "$.name", "value": "Bob", "oldValue": "Alice"}
            ],
        }
        result = apply_delta(deep_clone(source), delta)
        assert result == target

    def test_basic_replace_level_2(self):
        """TS: it('Level 2: applyDelta(target, inverse(delta)) == source')"""
        source = {"name": "Alice", "age": 30}
        target = {"name": "Bob", "age": 30}
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "replace", "path": "$.name", "value": "Bob", "oldValue": "Alice"}
            ],
        }
        inverse = invert_delta(delta)
        result = apply_delta(deep_clone(target), inverse)
        assert result == source

    def test_basic_replace_diff_produces_equivalent(self):
        """TS: it('diffDelta produces equivalent delta (verified by apply)')"""
        source = {"name": "Alice", "age": 30}
        target = {"name": "Bob", "age": 30}
        computed = diff_delta(source, target)
        result = apply_delta(deep_clone(source), computed)
        assert result == target

    def test_keyed_array_update_level_1(self):
        """TS: it('Level 1: applyDelta(source, delta) == target') for keyed-array"""
        source = {
            "items": [
                {"id": "1", "name": "Widget", "price": 10},
                {"id": "2", "name": "Gadget", "price": 20},
                {"id": "3", "name": "Doohickey", "price": 30},
            ]
        }
        target = {
            "items": [
                {"id": "1", "name": "Widget Pro", "price": 15},
                {"id": "2", "name": "Gadget", "price": 20},
                {"id": "4", "name": "Thingamajig", "price": 40},
            ]
        }
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "replace", "path": "$.items[?(@.id=='1')].name", "value": "Widget Pro", "oldValue": "Widget"},
                {"op": "replace", "path": "$.items[?(@.id=='1')].price", "value": 15, "oldValue": 10},
                {
                    "op": "remove",
                    "path": "$.items[?(@.id=='3')]",
                    "oldValue": {"id": "3", "name": "Doohickey", "price": 30},
                },
                {
                    "op": "add",
                    "path": "$.items[?(@.id=='4')]",
                    "value": {"id": "4", "name": "Thingamajig", "price": 40},
                },
            ],
        }
        result = apply_delta(deep_clone(source), delta)
        assert result == target

    def test_keyed_array_update_level_2(self):
        """TS: it('Level 2: applyDelta(target, inverse(delta)) == source') for keyed-array"""
        source = {
            "items": [
                {"id": "1", "name": "Widget", "price": 10},
                {"id": "2", "name": "Gadget", "price": 20},
                {"id": "3", "name": "Doohickey", "price": 30},
            ]
        }
        target = {
            "items": [
                {"id": "1", "name": "Widget Pro", "price": 15},
                {"id": "2", "name": "Gadget", "price": 20},
                {"id": "4", "name": "Thingamajig", "price": 40},
            ]
        }
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "replace", "path": "$.items[?(@.id=='1')].name", "value": "Widget Pro", "oldValue": "Widget"},
                {"op": "replace", "path": "$.items[?(@.id=='1')].price", "value": 15, "oldValue": 10},
                {
                    "op": "remove",
                    "path": "$.items[?(@.id=='3')]",
                    "oldValue": {"id": "3", "name": "Doohickey", "price": 30},
                },
                {
                    "op": "add",
                    "path": "$.items[?(@.id=='4')]",
                    "value": {"id": "4", "name": "Thingamajig", "price": 40},
                },
            ],
        }
        inverse = invert_delta(delta)
        result = apply_delta(deep_clone(target), inverse)
        assert result == source

    def test_keyed_array_diff_produces_equivalent(self):
        """TS: it('diffDelta produces equivalent delta (verified by apply)') for keyed-array"""
        source = {
            "items": [
                {"id": "1", "name": "Widget", "price": 10},
                {"id": "2", "name": "Gadget", "price": 20},
                {"id": "3", "name": "Doohickey", "price": 30},
            ]
        }
        target = {
            "items": [
                {"id": "1", "name": "Widget Pro", "price": 15},
                {"id": "2", "name": "Gadget", "price": 20},
                {"id": "4", "name": "Thingamajig", "price": 40},
            ]
        }
        computed = diff_delta(source, target, array_identity_keys={"items": "id"})
        result = apply_delta(deep_clone(source), computed)
        assert result == target


# ─── Integration round-trips (mirrors jsonDelta.test.ts) ─────────────────


class TestIntegrationRoundTripsCrossValidation:
    """TS: describe('integration round-trips', ...)"""

    def test_nested_objects_with_add_remove_replace(self):
        """TS: it('nested objects with add/remove/replace')"""
        source = {
            "user": {"name": "Alice", "age": 30},
            "settings": {"theme": "light", "lang": "en"},
        }
        target = {
            "user": {"name": "Bob", "age": 31},
            "settings": {"theme": "dark"},
            "newField": True,
        }
        delta = diff_delta(source, target)
        assert apply_delta(deep_clone(source), delta) == target
        assert revert_delta(deep_clone(target), delta) == source

    def test_keyed_arrays_with_deep_property_changes(self):
        """TS: it('keyed arrays with deep property changes')"""
        source = {
            "items": [
                {"id": 1, "name": "Widget", "details": {"color": "red"}},
                {"id": 2, "name": "Gadget", "details": {"color": "blue"}},
            ],
        }
        target = {
            "items": [
                {"id": 1, "name": "Widget", "details": {"color": "green"}},
                {"id": 2, "name": "Gadget", "details": {"color": "blue"}},
            ],
        }
        delta = diff_delta(source, target, array_identity_keys={"items": "id"})
        assert len(delta["operations"]) == 1
        assert delta["operations"][0]["path"] == "$.items[?(@.id==1)].details.color"
        assert apply_delta(deep_clone(source), delta) == target
        assert revert_delta(deep_clone(target), delta) == source


# ─── Complex scenarios from jsonDiff.test.ts (adapted to delta format) ───


class TestComplexScenariosCrossValidation:
    """Complex test cases adapted from json-diff-ts to test equivalent Python behavior."""

    def test_nested_array_changes_with_id_key(self):
        """TS: it('should correctly apply changes to nested arrays with id key')"""
        source = {
            "items": [
                {"id": 1, "name": "item1"},
                {"id": 2, "name": "item2"},
                {"id": 3, "name": "item3"},
            ]
        }
        target = {
            "items": [
                {"id": 1, "name": "item1-modified"},
                {"id": 3, "name": "item3"},
                {"id": 4, "name": "item4"},
            ]
        }
        delta = diff_delta(source, target, array_identity_keys={"items": "id"})
        result = apply_delta(copy.deepcopy(source), delta)
        assert result == target

    def test_nested_array_changes_index_based(self):
        """TS: it('should correctly apply changes to nested arrays with index key')"""
        source = {
            "items": [
                {"id": 1, "name": "item1"},
                {"id": 2, "name": "item2"},
                {"id": 3, "name": "item3"},
            ]
        }
        target = {
            "items": [
                {"id": 1, "name": "item1-modified"},
                {"id": 3, "name": "item3-modified"},
                {"id": 4, "name": "item4"},
            ]
        }
        delta = diff_delta(source, target)
        result = apply_delta(copy.deepcopy(source), delta)
        assert result == target

    def test_complex_nested_array_changes(self):
        """TS: it('should correctly apply complex nested array changes')"""
        source = {
            "departments": [
                {
                    "name": "Engineering",
                    "teams": [
                        {"id": "team1", "name": "Frontend", "members": ["Alice", "Bob"]},
                        {"id": "team2", "name": "Backend", "members": ["Charlie", "Dave"]},
                    ],
                },
                {
                    "name": "Marketing",
                    "teams": [
                        {"id": "team3", "name": "Digital", "members": ["Eve", "Frank"]},
                    ],
                },
            ]
        }
        target = {
            "departments": [
                {
                    "name": "Engineering",
                    "teams": [
                        {"id": "team1", "name": "Frontend Dev", "members": ["Alice", "Bob", "Grace"]},
                        {"id": "team4", "name": "DevOps", "members": ["Heidi"]},
                    ],
                },
                {
                    "name": "Marketing",
                    "teams": [
                        {"id": "team3", "name": "Digital Marketing", "members": ["Eve", "Ivy"]},
                    ],
                },
            ]
        }
        delta = diff_delta(
            source,
            target,
            array_identity_keys={
                "departments": "name",
                "departments.teams": "id",
            },
        )
        result = apply_delta(copy.deepcopy(source), delta)
        assert result == target

    def test_value_key_string_arrays(self):
        """TS: it('tracks array changes by array value') adapted to delta"""
        old_obj = {"items": ["apple", "banana", "orange"]}
        new_obj = {"items": ["orange", "lemon"]}
        delta = diff_delta(old_obj, new_obj, array_identity_keys={"items": "$value"})

        # Should have removes for apple and banana, and add for lemon
        remove_ops = [op for op in delta["operations"] if op["op"] == "remove"]
        add_ops = [op for op in delta["operations"] if op["op"] == "add"]
        assert len(remove_ops) == 2
        assert len(add_ops) == 1

        # Apply and verify
        result = apply_delta(copy.deepcopy(old_obj), delta)
        assert set(result["items"]) == set(new_obj["items"])

    def test_value_key_round_trip(self):
        """Value-based array round-trip via diff/apply/revert."""
        source = {"tags": ["red", "blue"]}
        target = {"tags": ["blue", "green"]}
        delta = diff_delta(source, target, array_identity_keys={"tags": "$value"})

        applied = apply_delta(copy.deepcopy(source), delta)
        assert set(applied["tags"]) == set(target["tags"])

        reverted = revert_delta(copy.deepcopy(applied), delta)
        assert set(reverted["tags"]) == set(source["tags"])


# ─── Path parsing cross-validation (mirrors deltaPath.test.ts) ───────────


class TestPathCrossValidation:
    """TS: describe('parseDeltaPath', ...) and describe('buildDeltaPath', ...)"""

    def test_parse_and_build_round_trips(self):
        """TS: it('round-trips with parseDeltaPath for canonical paths')"""
        from json_atom import build_path, parse_path

        paths = [
            "$",
            "$.name",
            "$.user.address.city",
            "$['a.b']",
            "$.items[0]",
            "$.items[?(@.id==42)]",
            "$.items[?(@.name=='Widget')]",
            "$.tags[?(@=='urgent')]",
            "$.items[?(@.id==1)].name",
        ]
        # Note: TS uses $.config['a.b'] but our canonical form is $['a.b'] for root-level
        for path in paths:
            assert build_path(parse_path(path)) == path

    def test_filter_literal_containing_close_bracket_paren(self):
        """TS: it('handles filter literal containing )]')
        Note: TS includes RootSegment in parsed output, Python omits it (root $ is implicit).
        """
        from json_atom import parse_path
        from json_atom.models import KeyFilterSegment, PropertySegment

        result = parse_path("$.items[?(@.name=='val)]ue')]")
        assert result == [
            PropertySegment(name="items"),
            KeyFilterSegment(property="name", value="val)]ue"),
        ]

    def test_format_filter_literal(self):
        """TS: describe('formatFilterLiteral', ...)"""
        from json_atom.path import format_filter_literal

        assert format_filter_literal("Alice") == "'Alice'"
        assert format_filter_literal("O'Brien") == "'O''Brien'"
        assert format_filter_literal(42) == "42"
        assert format_filter_literal(-7) == "-7"
        assert format_filter_literal(3.14) == "3.14"
        assert format_filter_literal(True) == "true"
        assert format_filter_literal(False) == "false"
        assert format_filter_literal(None) == "null"

    def test_parse_filter_literal(self):
        """TS: describe('parseFilterLiteral', ...)"""
        from json_atom.path import parse_filter_literal

        assert parse_filter_literal("'Alice'") == "Alice"
        assert parse_filter_literal("'O''Brien'") == "O'Brien"
        assert parse_filter_literal("42") == 42
        assert parse_filter_literal("-7") == -7
        assert parse_filter_literal("3.14") == 3.14
        assert parse_filter_literal("1e3") == 1000
        assert parse_filter_literal("true") is True
        assert parse_filter_literal("false") is False
        assert parse_filter_literal("null") is None

    def test_parse_filter_literal_rejects_invalid(self):
        """TS: it('rejects non-JSON numeric formats')"""
        from json_atom.path import parse_filter_literal

        with pytest.raises(Exception):
            parse_filter_literal("")
        with pytest.raises(Exception):
            parse_filter_literal("0x10")
        with pytest.raises(Exception):
            parse_filter_literal("0o7")
        with pytest.raises(Exception):
            parse_filter_literal("0b101")
        with pytest.raises(Exception):
            parse_filter_literal("01")
