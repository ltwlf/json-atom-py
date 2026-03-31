"""Tests for json_atom.apply — delta application."""

import copy

import pytest

from json_atom.apply import apply_delta
from json_atom.errors import ApplyError

from tests.conftest import deep_clone, load_fixture


# ---------------------------------------------------------------------------
# Property operations
# ---------------------------------------------------------------------------


class TestPropertyReplace:
    def test_simple_replace(self) -> None:
        obj = {"name": "Alice"}
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "replace", "path": "$.name", "value": "Bob", "oldValue": "Alice"}
            ],
        }
        result = apply_delta(obj, delta)
        assert result["name"] == "Bob"

    def test_nested_replace(self) -> None:
        obj = {"user": {"address": {"city": "Portland"}}}
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "replace", "path": "$.user.address.city", "value": "Seattle", "oldValue": "Portland"}
            ],
        }
        result = apply_delta(obj, delta)
        assert result["user"]["address"]["city"] == "Seattle"

    def test_replace_non_existent_raises(self) -> None:
        obj = {"name": "Alice"}
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "replace", "path": "$.missing", "value": "x"}
            ],
        }
        with pytest.raises(ApplyError, match="does not exist"):
            apply_delta(obj, delta)


class TestPropertyAdd:
    def test_simple_add(self) -> None:
        obj = {"name": "Alice"}
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "add", "path": "$.role", "value": "admin"}
            ],
        }
        result = apply_delta(obj, delta)
        assert result["role"] == "admin"
        assert result["name"] == "Alice"

    def test_add_on_existing_raises(self) -> None:
        obj = {"name": "Alice"}
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "add", "path": "$.name", "value": "Bob"}
            ],
        }
        with pytest.raises(ApplyError, match="already exists"):
            apply_delta(obj, delta)


class TestPropertyRemove:
    def test_simple_remove(self) -> None:
        obj = {"name": "Alice", "role": "admin"}
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "remove", "path": "$.role"}
            ],
        }
        result = apply_delta(obj, delta)
        assert "role" not in result
        assert result["name"] == "Alice"

    def test_remove_non_existent_raises(self) -> None:
        obj = {"name": "Alice"}
        delta = {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "remove", "path": "$.missing"}
            ],
        }
        with pytest.raises(ApplyError, match="does not exist"):
            apply_delta(obj, delta)


# ---------------------------------------------------------------------------
# Root operations (spec Section 6.5)
# ---------------------------------------------------------------------------


class TestRootOperations:
    def test_root_add_from_null(self) -> None:
        result = apply_delta(None, {
            "format": "json-atom",
            "version": 1,
            "operations": [{"op": "add", "path": "$", "value": {"created": True}}],
        })
        assert result == {"created": True}

    def test_root_add_from_non_null_raises(self) -> None:
        with pytest.raises(ApplyError, match="null"):
            apply_delta({"x": 1}, {
                "format": "json-atom",
                "version": 1,
                "operations": [{"op": "add", "path": "$", "value": {"new": True}}],
            })

    def test_root_remove_to_null(self) -> None:
        result = apply_delta({"name": "Alice"}, {
            "format": "json-atom",
            "version": 1,
            "operations": [{"op": "remove", "path": "$", "oldValue": {"name": "Alice"}}],
        })
        assert result is None

    def test_root_remove_from_null_raises(self) -> None:
        with pytest.raises(ApplyError, match="non-null"):
            apply_delta(None, {
                "format": "json-atom",
                "version": 1,
                "operations": [{"op": "remove", "path": "$"}],
            })

    def test_root_replace(self) -> None:
        result = apply_delta({"old": True}, {
            "format": "json-atom",
            "version": 1,
            "operations": [{"op": "replace", "path": "$", "value": {"new": True}, "oldValue": {"old": True}}],
        })
        assert result == {"new": True}

    def test_root_replace_object_to_array(self) -> None:
        result = apply_delta({"x": 1}, {
            "format": "json-atom",
            "version": 1,
            "operations": [{"op": "replace", "path": "$", "value": [1, 2, 3]}],
        })
        assert result == [1, 2, 3]

    def test_root_replace_object_to_primitive(self) -> None:
        result = apply_delta({"x": 1}, {
            "format": "json-atom",
            "version": 1,
            "operations": [{"op": "replace", "path": "$", "value": "hello"}],
        })
        assert result == "hello"

    def test_root_replace_from_null_raises(self) -> None:
        with pytest.raises(ApplyError, match="non-null"):
            apply_delta(None, {
                "format": "json-atom",
                "version": 1,
                "operations": [{"op": "replace", "path": "$", "value": {"new": True}}],
            })


# ---------------------------------------------------------------------------
# Index-based array operations (spec Section 7.1)
# ---------------------------------------------------------------------------


class TestIndexOperations:
    def test_index_replace(self) -> None:
        obj = {"tags": ["urgent", "review", "draft"]}
        result = apply_delta(obj, {
            "format": "json-atom",
            "version": 1,
            "operations": [{"op": "replace", "path": "$.tags[1]", "value": "approved"}],
        })
        assert result["tags"] == ["urgent", "approved", "draft"]

    def test_index_add_inserts(self) -> None:
        obj = {"items": [1, 2, 3]}
        result = apply_delta(obj, {
            "format": "json-atom",
            "version": 1,
            "operations": [{"op": "add", "path": "$.items[1]", "value": 99}],
        })
        assert result["items"] == [1, 99, 2, 3]

    def test_index_add_at_end(self) -> None:
        obj = {"items": [1, 2]}
        result = apply_delta(obj, {
            "format": "json-atom",
            "version": 1,
            "operations": [{"op": "add", "path": "$.items[2]", "value": 3}],
        })
        assert result["items"] == [1, 2, 3]

    def test_index_remove(self) -> None:
        obj = {"items": [1, 2, 3]}
        result = apply_delta(obj, {
            "format": "json-atom",
            "version": 1,
            "operations": [{"op": "remove", "path": "$.items[1]"}],
        })
        assert result["items"] == [1, 3]

    def test_index_out_of_range_raises(self) -> None:
        obj = {"items": [1, 2]}
        with pytest.raises(ApplyError, match="out of range"):
            apply_delta(obj, {
                "format": "json-atom",
                "version": 1,
                "operations": [{"op": "replace", "path": "$.items[5]", "value": 99}],
            })


# ---------------------------------------------------------------------------
# Key filter operations (spec Section 7.2)
# ---------------------------------------------------------------------------


class TestKeyFilterOperations:
    def test_key_filter_replace_deep_path(self) -> None:
        """Replace a property within a keyed-array element."""
        obj = {"items": [{"id": 1, "name": "Widget", "price": 10}]}
        result = apply_delta(obj, {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "replace", "path": "$.items[?(@.id==1)].name", "value": "Widget Pro"}
            ],
        })
        assert result["items"][0]["name"] == "Widget Pro"

    def test_key_filter_add_element(self) -> None:
        """Add a new element to a keyed array."""
        obj = {"items": [{"id": 1, "name": "Widget"}]}
        result = apply_delta(obj, {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "add", "path": "$.items[?(@.id==2)]", "value": {"id": 2, "name": "Gadget"}}
            ],
        })
        assert len(result["items"]) == 2
        assert result["items"][1] == {"id": 2, "name": "Gadget"}

    def test_key_filter_remove_element(self) -> None:
        obj = {"items": [{"id": 1, "name": "Widget"}, {"id": 2, "name": "Gadget"}]}
        result = apply_delta(obj, {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "remove", "path": "$.items[?(@.id==2)]"}
            ],
        })
        assert len(result["items"]) == 1
        assert result["items"][0]["id"] == 1

    def test_key_filter_with_string_literal(self) -> None:
        obj = {"items": [{"id": "a", "val": 1}, {"id": "b", "val": 2}]}
        result = apply_delta(obj, {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "replace", "path": "$.items[?(@.id=='b')].val", "value": 99}
            ],
        })
        assert result["items"][1]["val"] == 99

    def test_key_filter_with_boolean_literal(self) -> None:
        obj = {"flags": [{"active": True, "name": "a"}, {"active": False, "name": "b"}]}
        result = apply_delta(obj, {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "replace", "path": "$.flags[?(@.active==true)].name", "value": "updated"}
            ],
        })
        assert result["flags"][0]["name"] == "updated"

    def test_key_filter_with_null_literal(self) -> None:
        obj = {"items": [{"status": None, "name": "pending"}, {"status": "done", "name": "finished"}]}
        result = apply_delta(obj, {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "replace", "path": "$.items[?(@.status==null)].name", "value": "waiting"}
            ],
        })
        assert result["items"][0]["name"] == "waiting"

    def test_key_filter_match_zero_raises(self) -> None:
        obj = {"items": [{"id": 1, "name": "Widget"}]}
        with pytest.raises(ApplyError, match="zero"):
            apply_delta(obj, {
                "format": "json-atom",
                "version": 1,
                "operations": [
                    {"op": "replace", "path": "$.items[?(@.id==99)].name", "value": "x"}
                ],
            })

    def test_key_filter_match_multiple_raises(self) -> None:
        obj = {"items": [{"id": 1, "name": "A"}, {"id": 1, "name": "B"}]}
        with pytest.raises(ApplyError, match="2 elements"):
            apply_delta(obj, {
                "format": "json-atom",
                "version": 1,
                "operations": [
                    {"op": "replace", "path": "$.items[?(@.id==1)].name", "value": "x"}
                ],
            })


# ---------------------------------------------------------------------------
# Value filter operations (spec Section 7.3)
# ---------------------------------------------------------------------------


class TestValueFilterOperations:
    def test_value_filter_remove_string(self) -> None:
        obj = {"tags": ["urgent", "review", "draft"]}
        result = apply_delta(obj, {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "remove", "path": "$.tags[?(@=='draft')]"}
            ],
        })
        assert result["tags"] == ["urgent", "review"]

    def test_value_filter_add(self) -> None:
        obj = {"tags": ["urgent"]}
        result = apply_delta(obj, {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "add", "path": "$.tags[?(@=='new')]", "value": "new"}
            ],
        })
        assert result["tags"] == ["urgent", "new"]

    def test_value_filter_replace_number(self) -> None:
        obj = {"scores": [10, 20, 30]}
        result = apply_delta(obj, {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "replace", "path": "$.scores[?(@==20)]", "value": 25}
            ],
        })
        assert result["scores"] == [10, 25, 30]

    def test_value_filter_add_number(self) -> None:
        obj = {"scores": [10, 20, 30]}
        result = apply_delta(obj, {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "add", "path": "$.scores[?(@==40)]", "value": 40}
            ],
        })
        assert result["scores"] == [10, 20, 30, 40]

    def test_value_filter_add_duplicate_raises(self) -> None:
        obj = {"tags": ["urgent"]}
        with pytest.raises(ApplyError, match="already matches"):
            apply_delta(obj, {
                "format": "json-atom",
                "version": 1,
                "operations": [
                    {"op": "add", "path": "$.tags[?(@=='urgent')]", "value": "urgent"}
                ],
            })

    def test_value_filter_replace_string(self) -> None:
        obj = {"tags": ["urgent", "review", "draft"]}
        result = apply_delta(obj, {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "replace", "path": "$.tags[?(@=='review')]", "value": "approved"}
            ],
        })
        assert result["tags"] == ["urgent", "approved", "draft"]

    def test_value_filter_on_non_array_raises(self) -> None:
        obj = {"tags": "not-an-array"}
        with pytest.raises(ApplyError, match="value filter"):
            apply_delta(obj, {
                "format": "json-atom",
                "version": 1,
                "operations": [
                    {"op": "remove", "path": "$.tags[?(@=='x')]"}
                ],
            })

    def test_value_filter_match_zero_raises(self) -> None:
        obj = {"tags": ["urgent"]}
        with pytest.raises(ApplyError, match="zero"):
            apply_delta(obj, {
                "format": "json-atom",
                "version": 1,
                "operations": [
                    {"op": "remove", "path": "$.tags[?(@=='missing')]"}
                ],
            })


# ---------------------------------------------------------------------------
# Keyed-array value consistency (spec Section 6.4)
# ---------------------------------------------------------------------------


class TestKeyedArrayConsistency:
    def test_add_valid_consistency(self) -> None:
        """Value contains matching identity property."""
        obj = {"items": []}
        result = apply_delta(obj, {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "add", "path": "$.items[?(@.id==1)]", "value": {"id": 1, "name": "Widget"}}
            ],
        })
        assert len(result["items"]) == 1

    def test_add_missing_identity_prop_raises(self) -> None:
        obj = {"items": []}
        with pytest.raises(ApplyError, match="identity property"):
            apply_delta(obj, {
                "format": "json-atom",
                "version": 1,
                "operations": [
                    {"op": "add", "path": "$.items[?(@.id==1)]", "value": {"name": "Widget"}}
                ],
            })

    def test_add_wrong_identity_value_raises(self) -> None:
        obj = {"items": []}
        with pytest.raises(ApplyError, match="mismatch"):
            apply_delta(obj, {
                "format": "json-atom",
                "version": 1,
                "operations": [
                    {"op": "add", "path": "$.items[?(@.id==1)]", "value": {"id": 99, "name": "Widget"}}
                ],
            })

    def test_add_type_mismatch_identity_raises(self) -> None:
        """Filter uses string '4' but value has int 4."""
        obj = {"items": []}
        with pytest.raises(ApplyError, match="mismatch"):
            apply_delta(obj, {
                "format": "json-atom",
                "version": 1,
                "operations": [
                    {"op": "add", "path": "$.items[?(@.id=='4')]", "value": {"id": 4, "name": "Widget"}}
                ],
            })

    def test_add_value_not_dict_raises(self) -> None:
        obj = {"items": []}
        with pytest.raises(ApplyError, match="object"):
            apply_delta(obj, {
                "format": "json-atom",
                "version": 1,
                "operations": [
                    {"op": "add", "path": "$.items[?(@.id==1)]", "value": "not-a-dict"}
                ],
            })

    def test_replace_element_level_checks_consistency(self) -> None:
        """Element-level replace (no trailing segments) must check consistency."""
        obj = {"items": [{"id": 1, "name": "Widget"}]}
        with pytest.raises(ApplyError, match="mismatch"):
            apply_delta(obj, {
                "format": "json-atom",
                "version": 1,
                "operations": [
                    {"op": "replace", "path": "$.items[?(@.id==1)]", "value": {"id": 99, "name": "Other"}}
                ],
            })

    def test_deep_path_skips_consistency(self) -> None:
        """When path has trailing segments after filter, consistency check does NOT apply."""
        obj = {"items": [{"id": 1, "name": "Widget"}]}
        result = apply_delta(obj, {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "replace", "path": "$.items[?(@.id==1)].name", "value": "Gizmo"}
            ],
        })
        assert result["items"][0]["name"] == "Gizmo"


# ---------------------------------------------------------------------------
# Sequential operations
# ---------------------------------------------------------------------------


class TestSequentialOperations:
    def test_operations_see_modified_state(self) -> None:
        """Subsequent operations see the state after previous operations."""
        obj = {"counter": 0, "items": []}
        result = apply_delta(obj, {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "replace", "path": "$.counter", "value": 1, "oldValue": 0},
                {"op": "add", "path": "$.newProp", "value": "added"},
            ],
        })
        assert result["counter"] == 1
        assert result["newProp"] == "added"

    def test_mutation_in_place(self) -> None:
        """apply_delta mutates the object in place for non-root operations."""
        obj = {"name": "Alice"}
        result = apply_delta(obj, {
            "format": "json-atom",
            "version": 1,
            "operations": [
                {"op": "replace", "path": "$.name", "value": "Bob"}
            ],
        })
        assert result is obj
        assert obj["name"] == "Bob"


# ---------------------------------------------------------------------------
# Error conditions
# ---------------------------------------------------------------------------


class TestErrorConditions:
    def test_invalid_delta_structure_raises(self) -> None:
        with pytest.raises(ApplyError, match="Invalid delta"):
            apply_delta({}, {"not": "a-delta"})

    def test_malformed_path_raises(self) -> None:
        with pytest.raises(ApplyError):
            apply_delta({"x": 1}, {
                "format": "json-atom",
                "version": 1,
                "operations": [{"op": "replace", "path": "bad.path", "value": "x"}],
            })

    def test_navigate_property_on_non_object_raises(self) -> None:
        with pytest.raises(ApplyError):
            apply_delta({"x": "string_value"}, {
                "format": "json-atom",
                "version": 1,
                "operations": [
                    {"op": "replace", "path": "$.x.nested", "value": "y"}
                ],
            })

    def test_navigate_index_on_non_array_raises(self) -> None:
        with pytest.raises(ApplyError):
            apply_delta({"x": "not-array"}, {
                "format": "json-atom",
                "version": 1,
                "operations": [
                    {"op": "replace", "path": "$.x[0]", "value": "y"}
                ],
            })


# ---------------------------------------------------------------------------
# Level 1 conformance
# ---------------------------------------------------------------------------


class TestLevel1Conformance:
    def test_basic_replace_fixture(self) -> None:
        fixture = load_fixture("basic-replace")
        source = deep_clone(fixture["source"])
        result = apply_delta(source, fixture["delta"])
        assert result == fixture["target"]

    def test_keyed_array_update_fixture(self) -> None:
        fixture = load_fixture("keyed-array-update")
        source = deep_clone(fixture["source"])
        result = apply_delta(source, fixture["delta"])
        assert result == fixture["target"]
