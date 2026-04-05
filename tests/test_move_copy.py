"""Tests for move and copy operations."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from json_atom.apply import apply_delta
from json_atom.errors import ApplyError, InvertError
from json_atom.invert import invert_delta, revert_delta
from json_atom.models import Delta, Operation
from json_atom.validate import validate_delta


def _delta(*ops: Operation | dict[str, Any], **ext: Any) -> Delta:
    return Delta.create(*ops, **ext)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_valid_move(self) -> None:
        d = _delta(Operation.move("$.a", "$.b"))
        assert validate_delta(d).valid

    def test_valid_copy(self) -> None:
        d = _delta(Operation.copy_op("$.a", "$.b"))
        assert validate_delta(d).valid

    def test_valid_copy_with_value(self) -> None:
        d = _delta(Operation.copy_op("$.a", "$.b", value=42))
        assert validate_delta(d).valid

    def test_move_requires_from(self) -> None:
        d = _delta({"op": "move", "path": "$.b"})
        r = validate_delta(d)
        assert not r.valid
        assert any("requires 'from'" in e for e in r.errors)

    def test_copy_requires_from(self) -> None:
        d = _delta({"op": "copy", "path": "$.b"})
        r = validate_delta(d)
        assert not r.valid
        assert any("requires 'from'" in e for e in r.errors)

    def test_move_rejects_value(self) -> None:
        d = _delta({"op": "move", "from": "$.a", "path": "$.b", "value": 1})
        r = validate_delta(d)
        assert not r.valid
        assert any("must not include 'value'" in e for e in r.errors)

    def test_move_rejects_old_value(self) -> None:
        d = _delta({"op": "move", "from": "$.a", "path": "$.b", "oldValue": 1})
        r = validate_delta(d)
        assert not r.valid
        assert any("must not include 'oldValue'" in e for e in r.errors)

    def test_copy_rejects_old_value(self) -> None:
        d = _delta({"op": "copy", "from": "$.a", "path": "$.b", "oldValue": 1})
        r = validate_delta(d)
        assert not r.valid
        assert any("must not include 'oldValue'" in e for e in r.errors)

    def test_move_rejects_self_move(self) -> None:
        d = _delta({"op": "move", "from": "$.a", "path": "$.a"})
        r = validate_delta(d)
        assert not r.valid
        assert any("must differ" in e for e in r.errors)

    def test_move_rejects_subtree_move(self) -> None:
        d = _delta({"op": "move", "from": "$.a", "path": "$.a.b"})
        r = validate_delta(d)
        assert not r.valid
        assert any("subtree" in e for e in r.errors)

    def test_move_allows_ancestor_target(self) -> None:
        """Moving from subtree to ancestor is valid (not self-move)."""
        d = _delta({"op": "move", "from": "$.a.b", "path": "$.c"})
        assert validate_delta(d).valid

    def test_move_rejects_non_string_from(self) -> None:
        d = _delta({"op": "move", "from": 42, "path": "$.b"})
        r = validate_delta(d)
        assert not r.valid
        assert any("must be a string" in e for e in r.errors)

    def test_mixed_ops_validate(self) -> None:
        d = _delta(
            Operation.replace("$.x", "new", old_value="old"),
            Operation.move("$.a", "$.b"),
            Operation.copy_op("$.c", "$.d"),
            Operation.add("$.e", 1),
        )
        assert validate_delta(d).valid


# ---------------------------------------------------------------------------
# Apply — Move
# ---------------------------------------------------------------------------


class TestApplyMove:
    def test_move_object_property(self) -> None:
        obj = {"a": 1, "b": 2}
        d = _delta(Operation.move("$.a", "$.c"))
        result = apply_delta(obj, d)
        assert result == {"b": 2, "c": 1}

    def test_move_nested_property(self) -> None:
        obj = {"user": {"name": "Alice", "role": "admin"}}
        d = _delta(Operation.move("$.user.name", "$.user.displayName"))
        result = apply_delta(obj, d)
        assert result == {"user": {"displayName": "Alice", "role": "admin"}}

    def test_move_array_element_by_index(self) -> None:
        obj = {"arr": [10, 20, 30]}
        # Remove index 0 (10), then add at index 2 — but after removal arr is [20,30]
        # so index 2 appends: [20, 30, 10]
        d = _delta(Operation.move("$.arr[0]", "$.arr[2]"))
        result = apply_delta(obj, d)
        assert result == {"arr": [20, 30, 10]}

    def test_move_keyed_array_element(self) -> None:
        obj = {
            "items": [{"id": 1, "v": "a"}, {"id": 2, "v": "b"}],
            "archive": [],
        }
        d = _delta(Operation.move("$.items[?(@.id==2)]", "$.archive[?(@.id==2)]"))
        result = apply_delta(obj, d)
        assert result == {
            "items": [{"id": 1, "v": "a"}],
            "archive": [{"id": 2, "v": "b"}],
        }

    def test_move_from_root(self) -> None:
        obj = {"data": "hello"}
        d = _delta(Operation.move("$.data", "$.backup"))
        result = apply_delta(obj, d)
        assert result == {"backup": "hello"}

    def test_move_complex_object(self) -> None:
        obj = {"a": {"nested": {"deep": [1, 2, 3]}}, "b": {}}
        d = _delta(Operation.move("$.a.nested", "$.b.nested"))
        result = apply_delta(obj, d)
        assert result == {"a": {}, "b": {"nested": {"deep": [1, 2, 3]}}}

    def test_move_error_nonexistent_source(self) -> None:
        obj = {"a": 1}
        d = _delta(Operation.move("$.missing", "$.b"))
        with pytest.raises(ApplyError):
            apply_delta(obj, d)

    def test_move_error_existing_target(self) -> None:
        obj = {"a": 1, "b": 2}
        d = _delta(Operation.move("$.a", "$.b"))
        with pytest.raises(ApplyError):
            apply_delta(obj, d)


# ---------------------------------------------------------------------------
# Apply — Copy
# ---------------------------------------------------------------------------


class TestApplyCopy:
    def test_copy_object_property(self) -> None:
        obj = {"a": 1}
        d = _delta(Operation.copy_op("$.a", "$.b"))
        result = apply_delta(obj, d)
        assert result == {"a": 1, "b": 1}

    def test_copy_preserves_source(self) -> None:
        obj = {"a": {"nested": 1}}
        d = _delta(Operation.copy_op("$.a", "$.b"))
        result = apply_delta(obj, d)
        assert result["a"] == {"nested": 1}
        assert result["b"] == {"nested": 1}

    def test_copy_deep_clones(self) -> None:
        obj = {"a": {"nested": [1, 2]}}
        d = _delta(Operation.copy_op("$.a", "$.b"))
        result = apply_delta(obj, d)
        # Mutate the copy — source should be unchanged
        result["b"]["nested"].append(3)
        assert result["a"]["nested"] == [1, 2]
        assert result["b"]["nested"] == [1, 2, 3]

    def test_copy_from_root(self) -> None:
        obj = {"x": 1}
        d = _delta(Operation.copy_op("$", "$.snapshot"))
        result = apply_delta(obj, d)
        assert result == {"x": 1, "snapshot": {"x": 1}}

    def test_copy_array_element(self) -> None:
        obj = {"arr": [10, 20], "other": []}
        d = _delta(Operation.copy_op("$.arr[0]", "$.other[0]"))
        result = apply_delta(obj, d)
        assert result == {"arr": [10, 20], "other": [10]}

    def test_copy_error_nonexistent_source(self) -> None:
        obj = {"a": 1}
        d = _delta(Operation.copy_op("$.missing", "$.b"))
        with pytest.raises(ApplyError):
            apply_delta(obj, d)

    def test_copy_error_existing_target(self) -> None:
        obj = {"a": 1, "b": 2}
        d = _delta(Operation.copy_op("$.a", "$.b"))
        with pytest.raises(ApplyError):
            apply_delta(obj, d)


# ---------------------------------------------------------------------------
# Inversion
# ---------------------------------------------------------------------------


class TestInversion:
    def test_move_inversion_swaps_paths(self) -> None:
        d = _delta(Operation.move("$.a", "$.b"))
        inv = invert_delta(d)
        assert inv.operations[0]["op"] == "move"
        assert inv.operations[0]["from"] == "$.b"
        assert inv.operations[0]["path"] == "$.a"

    def test_move_round_trip(self) -> None:
        obj = {"a": 1, "b": 2}
        d = _delta(Operation.move("$.a", "$.c"))
        target = apply_delta(copy.deepcopy(obj), d)
        assert target == {"b": 2, "c": 1}
        restored = revert_delta(target, d)
        assert restored == obj

    def test_copy_inversion_produces_remove(self) -> None:
        d = _delta(Operation.copy_op("$.a", "$.b", value=42))
        inv = invert_delta(d)
        assert inv.operations[0]["op"] == "remove"
        assert inv.operations[0]["path"] == "$.b"
        assert inv.operations[0]["oldValue"] == 42

    def test_copy_round_trip(self) -> None:
        obj = {"a": 42}
        d = _delta(Operation.copy_op("$.a", "$.b", value=42))
        target = apply_delta(copy.deepcopy(obj), d)
        assert target == {"a": 42, "b": 42}
        restored = revert_delta(target, d)
        assert restored == obj

    def test_copy_without_value_raises(self) -> None:
        d = _delta(Operation.copy_op("$.a", "$.b"))
        with pytest.raises(InvertError, match="missing 'value'"):
            invert_delta(d)

    def test_extension_preserved(self) -> None:
        d = _delta({"op": "move", "from": "$.a", "path": "$.b", "x_tag": "test"})
        inv = invert_delta(d)
        assert inv.operations[0].get("x_tag") == "test"

    def test_multi_op_inversion_order(self) -> None:
        d = _delta(
            Operation.move("$.a", "$.b"),
            Operation.copy_op("$.c", "$.d", value=1),
        )
        inv = invert_delta(d)
        # Order reversed
        assert inv.operations[0]["op"] == "remove"  # inverted copy
        assert inv.operations[0]["path"] == "$.d"
        assert inv.operations[1]["op"] == "move"  # inverted move
        assert inv.operations[1]["from"] == "$.b"


# ---------------------------------------------------------------------------
# Sequential semantics
# ---------------------------------------------------------------------------


class TestSequentialSemantics:
    def test_move_then_operate_on_moved(self) -> None:
        obj = {"a": {"v": 1}, "b": {}}
        d = _delta(
            Operation.move("$.a", "$.c"),
            Operation.replace("$.c.v", 2, old_value=1),
        )
        result = apply_delta(obj, d)
        assert result == {"b": {}, "c": {"v": 2}}

    def test_copy_then_modify_copy(self) -> None:
        obj = {"a": {"v": 1}}
        d = _delta(
            Operation.copy_op("$.a", "$.b"),
            Operation.replace("$.b.v", 99, old_value=1),
        )
        result = apply_delta(obj, d)
        assert result == {"a": {"v": 1}, "b": {"v": 99}}

    def test_multiple_moves(self) -> None:
        obj = {"a": 1, "b": 2, "c": 3}
        d = _delta(
            Operation.move("$.a", "$.x"),
            Operation.move("$.b", "$.y"),
        )
        result = apply_delta(obj, d)
        assert result == {"c": 3, "x": 1, "y": 2}

    def test_mixed_ops(self) -> None:
        obj = {"a": 1, "b": 2}
        d = _delta(
            Operation.copy_op("$.a", "$.c"),
            Operation.move("$.b", "$.d"),
            Operation.add("$.e", 5),
        )
        result = apply_delta(obj, d)
        assert result == {"a": 1, "c": 1, "d": 2, "e": 5}


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_move_null_value(self) -> None:
        obj = {"a": None, "b": 1}
        d = _delta(Operation.move("$.a", "$.c"))
        result = apply_delta(obj, d)
        assert result == {"b": 1, "c": None}

    def test_copy_null_value(self) -> None:
        obj = {"a": None}
        d = _delta(Operation.copy_op("$.a", "$.b"))
        result = apply_delta(obj, d)
        assert result == {"a": None, "b": None}

    def test_move_empty_object(self) -> None:
        obj = {"a": {}, "b": 1}
        d = _delta(Operation.move("$.a", "$.c"))
        result = apply_delta(obj, d)
        assert result == {"b": 1, "c": {}}

    def test_move_empty_array(self) -> None:
        obj = {"a": [], "b": 1}
        d = _delta(Operation.move("$.a", "$.c"))
        result = apply_delta(obj, d)
        assert result == {"b": 1, "c": []}

    def test_copy_with_value_matches_actual(self) -> None:
        """The optional value field on copy should match what's actually copied."""
        obj = {"a": 42}
        d = _delta(Operation.copy_op("$.a", "$.b", value=42))
        result = apply_delta(obj, d)
        # Apply ignores value, reads from source
        assert result == {"a": 42, "b": 42}

    def test_move_boolean_value(self) -> None:
        obj = {"a": False, "b": 1}
        d = _delta(Operation.move("$.a", "$.c"))
        result = apply_delta(obj, d)
        assert result == {"b": 1, "c": False}
