"""Tests for json_delta.json_patch — JSON Patch (RFC 6902) interop."""

import copy

import pytest

from json_delta import diff_delta
from json_delta.json_patch import from_json_patch, to_json_patch
from json_delta.models import Delta, Operation


# ---------------------------------------------------------------------------
# to_json_patch
# ---------------------------------------------------------------------------


class TestToJsonPatch:
    def test_simple_replace(self) -> None:
        delta = Delta({
            "format": "json-delta",
            "version": 1,
            "operations": [{"op": "replace", "path": "$.name", "value": "Bob"}],
        })
        doc = {"name": "Alice"}
        patch = to_json_patch(delta, doc)
        assert patch == [{"op": "replace", "path": "/name", "value": "Bob"}]

    def test_simple_add(self) -> None:
        delta = Delta({
            "format": "json-delta",
            "version": 1,
            "operations": [{"op": "add", "path": "$.email", "value": "a@b.com"}],
        })
        doc = {"name": "Alice"}
        patch = to_json_patch(delta, doc)
        assert patch == [{"op": "add", "path": "/email", "value": "a@b.com"}]

    def test_simple_remove(self) -> None:
        delta = Delta({
            "format": "json-delta",
            "version": 1,
            "operations": [{"op": "remove", "path": "$.name"}],
        })
        doc = {"name": "Alice"}
        patch = to_json_patch(delta, doc)
        assert patch == [{"op": "remove", "path": "/name"}]

    def test_key_filter_resolve(self) -> None:
        doc = {"items": [{"id": 1, "name": "Widget"}, {"id": 2, "name": "Gadget"}]}
        delta = Delta({
            "format": "json-delta",
            "version": 1,
            "operations": [{"op": "replace", "path": "$.items[?(@.id==2)].name", "value": "Super Gadget"}],
        })
        patch = to_json_patch(delta, doc)
        assert patch == [{"op": "replace", "path": "/items/1/name", "value": "Super Gadget"}]

    def test_add_new_array_element_uses_dash(self) -> None:
        doc = {"items": [{"id": 1, "name": "Widget"}]}
        delta = Delta({
            "format": "json-delta",
            "version": 1,
            "operations": [
                {"op": "add", "path": "$.items[?(@.id==2)]", "value": {"id": 2, "name": "Gadget"}},
            ],
        })
        patch = to_json_patch(delta, doc)
        assert patch == [{"op": "add", "path": "/items/-", "value": {"id": 2, "name": "Gadget"}}]

    def test_multiple_operations(self) -> None:
        doc = {"x": 1, "y": 2}
        delta = Delta({
            "format": "json-delta",
            "version": 1,
            "operations": [
                {"op": "replace", "path": "$.x", "value": 10},
                {"op": "remove", "path": "$.y"},
                {"op": "add", "path": "$.z", "value": 3},
            ],
        })
        patch = to_json_patch(delta, doc)
        assert len(patch) == 3
        assert patch[0]["path"] == "/x"
        assert patch[1]["path"] == "/y"
        assert patch[2]["path"] == "/z"

    def test_oldValue_not_included(self) -> None:
        delta = Delta({
            "format": "json-delta",
            "version": 1,
            "operations": [{"op": "replace", "path": "$.x", "value": 2, "oldValue": 1}],
        })
        patch = to_json_patch(delta, {"x": 1})
        assert "oldValue" not in patch[0]

    def test_delta_method(self) -> None:
        delta = Delta({
            "format": "json-delta",
            "version": 1,
            "operations": [{"op": "replace", "path": "$.x", "value": 2}],
        })
        patch = delta.to_json_patch({"x": 1})
        assert patch == [{"op": "replace", "path": "/x", "value": 2}]

    def test_pointer_escaping(self) -> None:
        doc = {"a/b": {"c~d": 1}}
        delta = Delta({
            "format": "json-delta",
            "version": 1,
            "operations": [{"op": "replace", "path": "$['a/b']['c~d']", "value": 2}],
        })
        patch = to_json_patch(delta, doc)
        assert patch[0]["path"] == "/a~1b/c~0d"


# ---------------------------------------------------------------------------
# from_json_patch
# ---------------------------------------------------------------------------


class TestFromJsonPatch:
    def test_simple_add(self) -> None:
        patch = [{"op": "add", "path": "/name", "value": "Alice"}]
        delta = from_json_patch(patch)
        assert isinstance(delta, Delta)
        assert delta.format == "json-delta"
        assert delta.version == 1
        assert len(delta.operations) == 1
        assert delta.operations[0].op == "add"
        assert delta.operations[0].path == "$.name"
        assert delta.operations[0].value == "Alice"

    def test_simple_remove(self) -> None:
        patch = [{"op": "remove", "path": "/name"}]
        delta = from_json_patch(patch)
        assert delta.operations[0].op == "remove"
        assert delta.operations[0].path == "$.name"

    def test_simple_replace(self) -> None:
        patch = [{"op": "replace", "path": "/name", "value": "Bob"}]
        delta = from_json_patch(patch)
        assert delta.operations[0].op == "replace"
        assert delta.operations[0].value == "Bob"

    def test_nested_path(self) -> None:
        patch = [{"op": "replace", "path": "/user/name", "value": "Bob"}]
        delta = from_json_patch(patch)
        assert delta.operations[0].path == "$.user.name"

    def test_array_index(self) -> None:
        patch = [{"op": "replace", "path": "/items/0/name", "value": "New"}]
        delta = from_json_patch(patch)
        assert delta.operations[0].path == "$.items[0].name"

    def test_root_path(self) -> None:
        patch = [{"op": "replace", "path": "", "value": {"new": "doc"}}]
        delta = from_json_patch(patch)
        assert delta.operations[0].path == "$"

    def test_pointer_unescaping(self) -> None:
        patch = [{"op": "replace", "path": "/a~1b/c~0d", "value": 1}]
        delta = from_json_patch(patch)
        assert delta.operations[0].path == "$['a/b']['c~d']"

    def test_multiple_operations(self) -> None:
        patch = [
            {"op": "add", "path": "/x", "value": 1},
            {"op": "remove", "path": "/y"},
            {"op": "replace", "path": "/z", "value": 3},
        ]
        delta = from_json_patch(patch)
        assert len(delta.operations) == 3

    def test_move_raises(self) -> None:
        patch = [{"op": "move", "path": "/b", "from": "/a"}]
        with pytest.raises(ValueError, match="'move' operation is not supported"):
            from_json_patch(patch)

    def test_copy_raises(self) -> None:
        patch = [{"op": "copy", "path": "/b", "from": "/a"}]
        with pytest.raises(ValueError, match="'copy' operation is not supported"):
            from_json_patch(patch)

    def test_test_raises(self) -> None:
        patch = [{"op": "test", "path": "/x", "value": 1}]
        with pytest.raises(ValueError, match="'test' operation is not supported"):
            from_json_patch(patch)

    def test_unknown_op_raises(self) -> None:
        patch = [{"op": "foobar", "path": "/x"}]
        with pytest.raises(ValueError, match="unknown operation"):
            from_json_patch(patch)

    def test_from_classmethod(self) -> None:
        patch = [{"op": "add", "path": "/x", "value": 1}]
        delta = Delta.from_json_patch(patch)
        assert isinstance(delta, Delta)
        assert delta.operations[0].op == "add"


# ---------------------------------------------------------------------------
# Round-trip: diff → to_json_patch
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_property_changes(self) -> None:
        old = {"name": "Alice", "age": 30}
        new = {"name": "Bob", "age": 30, "email": "bob@x.com"}
        delta = diff_delta(old, new)
        patch = to_json_patch(delta, old)

        # Apply patch manually
        result = copy.deepcopy(old)
        for op in patch:
            _apply_json_patch_op(result, op)
        assert result == new

    def test_keyed_array_changes(self) -> None:
        old = {"items": [{"id": 1, "name": "Widget"}, {"id": 2, "name": "Gadget"}]}
        new = {"items": [{"id": 1, "name": "Widget Pro"}, {"id": 2, "name": "Gadget"}]}
        delta = diff_delta(old, new, array_keys={"items": "id"})
        patch = to_json_patch(delta, old)
        assert len(patch) == 1
        assert patch[0]["path"] == "/items/0/name"
        assert patch[0]["value"] == "Widget Pro"


def _apply_json_patch_op(doc: dict, op: dict) -> None:
    """Minimal JSON Patch apply for testing (property-level only)."""
    parts = op["path"].lstrip("/").split("/") if op["path"] else []
    if not parts:
        return
    parent = doc
    for part in parts[:-1]:
        if part.isdigit():
            parent = parent[int(part)]
        else:
            parent = parent[part]
    final = parts[-1]
    if op["op"] == "add":
        parent[final] = op["value"]
    elif op["op"] == "remove":
        del parent[final]
    elif op["op"] == "replace":
        parent[final] = op["value"]
