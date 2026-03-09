"""Tests for json_delta.models — PathSegment types, ValidationResult, Delta, Operation."""

import copy
import json

import pytest

from json_delta.models import (
    Delta,
    IndexSegment,
    KeyFilterSegment,
    Operation,
    PropertySegment,
    RootSegment,
    ValidationResult,
    ValueFilterSegment,
)


class TestRootSegment:
    def test_construction(self) -> None:
        seg = RootSegment()
        assert isinstance(seg, RootSegment)

    def test_equality(self) -> None:
        assert RootSegment() == RootSegment()

    def test_hash(self) -> None:
        assert hash(RootSegment()) == hash(RootSegment())

    def test_frozen(self) -> None:
        seg = RootSegment()
        try:
            seg.x = 1  # type: ignore[attr-defined]
            assert False, "Should raise"
        except (AttributeError, TypeError):
            pass


class TestPropertySegment:
    def test_construction(self) -> None:
        seg = PropertySegment(name="user")
        assert seg.name == "user"

    def test_equality(self) -> None:
        assert PropertySegment("name") == PropertySegment("name")
        assert PropertySegment("name") != PropertySegment("other")

    def test_hash(self) -> None:
        assert hash(PropertySegment("x")) == hash(PropertySegment("x"))
        # Different names should (usually) have different hashes
        assert hash(PropertySegment("x")) != hash(PropertySegment("y"))

    def test_frozen(self) -> None:
        seg = PropertySegment("name")
        try:
            seg.name = "other"  # type: ignore[misc]
            assert False, "Should raise"
        except AttributeError:
            pass


class TestIndexSegment:
    def test_construction(self) -> None:
        seg = IndexSegment(index=0)
        assert seg.index == 0

    def test_equality(self) -> None:
        assert IndexSegment(0) == IndexSegment(0)
        assert IndexSegment(0) != IndexSegment(1)

    def test_hash(self) -> None:
        assert hash(IndexSegment(0)) == hash(IndexSegment(0))


class TestKeyFilterSegment:
    def test_construction_with_string_value(self) -> None:
        seg = KeyFilterSegment(property="id", value="42")
        assert seg.property == "id"
        assert seg.value == "42"

    def test_construction_with_int_value(self) -> None:
        seg = KeyFilterSegment(property="id", value=42)
        assert seg.value == 42

    def test_construction_with_bool_value(self) -> None:
        seg = KeyFilterSegment(property="active", value=True)
        assert seg.value is True

    def test_construction_with_null_value(self) -> None:
        seg = KeyFilterSegment(property="status", value=None)
        assert seg.value is None

    def test_equality(self) -> None:
        assert KeyFilterSegment("id", 42) == KeyFilterSegment("id", 42)
        assert KeyFilterSegment("id", 42) != KeyFilterSegment("id", "42")
        assert KeyFilterSegment("id", 42) != KeyFilterSegment("key", 42)

    def test_hash(self) -> None:
        assert hash(KeyFilterSegment("id", 42)) == hash(KeyFilterSegment("id", 42))


class TestValueFilterSegment:
    def test_construction_with_string(self) -> None:
        seg = ValueFilterSegment(value="urgent")
        assert seg.value == "urgent"

    def test_construction_with_number(self) -> None:
        seg = ValueFilterSegment(value=100)
        assert seg.value == 100

    def test_equality(self) -> None:
        assert ValueFilterSegment("urgent") == ValueFilterSegment("urgent")
        assert ValueFilterSegment("urgent") != ValueFilterSegment("other")
        assert ValueFilterSegment(42) != ValueFilterSegment("42")

    def test_hash(self) -> None:
        assert hash(ValueFilterSegment("x")) == hash(ValueFilterSegment("x"))


class TestValidationResult:
    def test_valid(self) -> None:
        result = ValidationResult(valid=True, errors=())
        assert result.valid is True
        assert result.errors == ()

    def test_invalid(self) -> None:
        result = ValidationResult(valid=False, errors=("missing format",))
        assert result.valid is False
        assert result.errors == ("missing format",)

    def test_multiple_errors(self) -> None:
        result = ValidationResult(valid=False, errors=("error 1", "error 2"))
        assert len(result.errors) == 2

    def test_frozen(self) -> None:
        result = ValidationResult(valid=True, errors=())
        try:
            result.valid = False  # type: ignore[misc]
            assert False, "Should raise"
        except AttributeError:
            pass

    def test_equality(self) -> None:
        assert ValidationResult(True, ()) == ValidationResult(True, ())
        assert ValidationResult(False, ("e",)) == ValidationResult(False, ("e",))
        assert ValidationResult(True, ()) != ValidationResult(False, ())


# ---------------------------------------------------------------------------
# Operation
# ---------------------------------------------------------------------------


class TestOperation:
    def test_construction_from_dict(self) -> None:
        op = Operation({"op": "add", "path": "$.name", "value": "Alice"})
        assert op.op == "add"
        assert op.path == "$.name"
        assert op.value == "Alice"
        assert op.old_value is None

    def test_construction_from_kwargs(self) -> None:
        op = Operation(op="replace", path="$.name", value="Bob", oldValue="Alice")
        assert op.op == "replace"
        assert op.value == "Bob"
        assert op.old_value == "Alice"

    def test_remove_operation(self) -> None:
        op = Operation(op="remove", path="$.name", oldValue="Alice")
        assert op.op == "remove"
        assert op.value is None
        assert op.old_value == "Alice"

    def test_dict_access(self) -> None:
        op = Operation(op="add", path="$.x", value=42)
        assert op["op"] == "add"
        assert op["path"] == "$.x"
        assert op["value"] == 42

    def test_isinstance_dict(self) -> None:
        op = Operation(op="add", path="$", value=1)
        assert isinstance(op, dict)

    def test_json_serializable(self) -> None:
        op = Operation(op="replace", path="$.name", value="Bob", oldValue="Alice")
        serialized = json.dumps(op, sort_keys=True)
        assert '"op": "replace"' in serialized
        assert '"oldValue": "Alice"' in serialized

    def test_extension_properties(self) -> None:
        op = Operation(op="add", path="$.name", value="Alice")
        op["x_editor"] = "admin"
        assert op["x_editor"] == "admin"

    def test_repr(self) -> None:
        op = Operation(op="add", path="$", value=1)
        assert repr(op).startswith("Operation(")

    def test_describe(self) -> None:
        op = Operation(op="replace", path="$.user.name", value="Bob")
        assert op.describe() == "user > name"

    def test_describe_root(self) -> None:
        op = Operation(op="replace", path="$", value={})
        assert op.describe() == "(root)"

    def test_resolve(self) -> None:
        doc = {"items": [{"id": 1, "name": "Widget"}]}
        op = Operation(op="replace", path="$.items[?(@.id==1)].name", value="Gadget")
        assert op.resolve(doc) == "/items/0/name"

    def test_to_json_patch_op(self) -> None:
        doc = {"items": [{"id": 1, "name": "Widget"}]}
        op = Operation(op="replace", path="$.items[?(@.id==1)].name", value="Gadget", oldValue="Widget")
        patch_op = op.to_json_patch_op(doc)
        assert patch_op == {"op": "replace", "path": "/items/0/name", "value": "Gadget"}

    # -- segments property --------------------------------------------------

    def test_segments_simple(self) -> None:
        op = Operation(op="replace", path="$.user.name", value="Bob")
        segs = op.segments
        assert len(segs) == 2
        assert segs[0] == PropertySegment(name="user")
        assert segs[1] == PropertySegment(name="name")

    def test_segments_with_filter(self) -> None:
        op = Operation(op="replace", path="$.items[?(@.id==1)].name", value="X")
        segs = op.segments
        assert len(segs) == 3
        assert segs[0] == PropertySegment(name="items")
        assert segs[1] == KeyFilterSegment(property="id", value=1)
        assert segs[2] == PropertySegment(name="name")

    def test_segments_root(self) -> None:
        op = Operation(op="replace", path="$", value={})
        assert op.segments == []

    # -- filter_values (cached property) ------------------------------------

    def test_filter_values_single_key(self) -> None:
        op = Operation(op="replace", path="$.items[?(@.id==42)].name", value="X")
        assert op.filter_values == {"items": 42}

    def test_filter_values_multiple_keys(self) -> None:
        op = Operation(
            op="replace",
            path="$.articles[?(@.id=='art-3')].clauses[?(@.id=='cl-1')].text",
            value="new",
        )
        assert op.filter_values == {"articles": "art-3", "clauses": "cl-1"}

    def test_filter_values_no_filters(self) -> None:
        op = Operation(op="replace", path="$.user.name", value="Bob")
        assert op.filter_values == {}

    def test_filter_values_value_filter(self) -> None:
        op = Operation(op="remove", path="$.tags[?(@=='urgent')]")
        assert op.filter_values == {"tags": "urgent"}

    # -- Factory methods ----------------------------------------------------

    def test_factory_add(self) -> None:
        op = Operation.add("$.name", "Alice")
        assert op.op == "add"
        assert op.path == "$.name"
        assert op.value == "Alice"
        assert op.old_value is None

    def test_factory_replace(self) -> None:
        op = Operation.replace("$.name", "Bob", old_value="Alice")
        assert op.op == "replace"
        assert op.path == "$.name"
        assert op.value == "Bob"
        assert op.old_value == "Alice"

    def test_factory_replace_without_old_value(self) -> None:
        op = Operation.replace("$.name", "Bob")
        assert op.op == "replace"
        assert op.value == "Bob"
        assert "oldValue" not in op

    def test_factory_remove(self) -> None:
        op = Operation.remove("$.name", old_value="Alice")
        assert op.op == "remove"
        assert op.path == "$.name"
        assert op.value is None
        assert op.old_value == "Alice"

    def test_factory_remove_without_old_value(self) -> None:
        op = Operation.remove("$.name")
        assert op.op == "remove"
        assert "oldValue" not in op

    def test_factory_with_extensions(self) -> None:
        op = Operation.add("$.name", "Alice", x_editor="admin")
        assert op["x_editor"] == "admin"
        assert op.op == "add"

    def test_factory_json_serializable(self) -> None:
        op = Operation.replace("$.x", 2, old_value=1)
        serialized = json.dumps(op, sort_keys=True)
        assert '"op": "replace"' in serialized
        assert '"oldValue": 1' in serialized

    # -- Caching ------------------------------------------------------------

    def test_segments_cached(self) -> None:
        op = Operation(op="replace", path="$.user.name", value="Bob")
        assert op.segments is op.segments  # same object identity

    def test_filter_values_cached(self) -> None:
        op = Operation(op="replace", path="$.items[?(@.id==1)].name", value="X")
        assert op.filter_values is op.filter_values  # same object identity

    def test_cache_invalidated_on_setitem(self) -> None:
        op = Operation(op="replace", path="$.user.name", value="Bob")
        old_segs = op.segments
        op["path"] = "$.items[0].title"
        assert op.segments != old_segs
        assert op.segments[0] == PropertySegment(name="items")

    def test_cache_invalidated_on_update(self) -> None:
        op = Operation(op="replace", path="$.user.name", value="Bob")
        _ = op.segments  # populate cache
        op.update({"path": "$.x"})
        assert op.segments == [PropertySegment(name="x")]

    def test_cache_invalidated_on_clear(self) -> None:
        op = Operation(op="replace", path="$.user.name", value="Bob")
        _ = op.segments  # populate cache
        op.clear()
        assert "segments" not in op.__dict__

    def test_cache_invalidated_on_popitem(self) -> None:
        op = Operation(op="replace", path="$.user.name", value="Bob")
        _ = op.segments  # populate cache
        # popitem removes LIFO; keep popping until "path" is gone
        while "path" in op:
            op.popitem()
        assert "segments" not in op.__dict__

    def test_cache_not_invalidated_on_non_path_setitem(self) -> None:
        op = Operation(op="replace", path="$.user.name", value="Bob")
        segs = op.segments
        op["value"] = "Alice"  # non-path key
        assert op.segments is segs  # same cached object

    # -- __getattr__ (extension attribute access) ---------------------------

    def test_getattr_extension(self) -> None:
        op = Operation(op="add", path="$.x", value=1, x_editor="admin")
        assert op.x_editor == "admin"

    def test_getattr_missing_raises(self) -> None:
        op = Operation(op="add", path="$.x", value=1)
        with pytest.raises(AttributeError, match="no attribute"):
            _ = op.nonexistent

    def test_getattr_spec_property_takes_precedence(self) -> None:
        """Class properties (op, path, value, old_value) take precedence over __getattr__."""
        op = Operation(op="add", path="$.x", value=1)
        assert op.op == "add"  # via @property, not __getattr__
        assert op.path == "$.x"

    # -- __dir__ ------------------------------------------------------------

    def test_dir_includes_extensions(self) -> None:
        op = Operation(op="add", path="$.x", value=1, x_editor="admin")
        d = dir(op)
        assert "x_editor" in d
        assert "op" in d  # class attributes still present

    # -- extensions property ------------------------------------------------

    def test_extensions_returns_non_spec_keys(self) -> None:
        op = Operation(op="add", path="$.x", value=1, x_editor="admin", x_ts="2024-01-01")
        assert op.extensions == {"x_editor": "admin", "x_ts": "2024-01-01"}

    def test_extensions_empty(self) -> None:
        op = Operation(op="add", path="$.x", value=1)
        assert op.extensions == {}

    def test_extensions_excludes_spec_keys(self) -> None:
        op = Operation(op="replace", path="$.x", value=2, oldValue=1, x_reason="fix")
        assert "op" not in op.extensions
        assert "path" not in op.extensions
        assert "value" not in op.extensions
        assert "oldValue" not in op.extensions
        assert op.extensions == {"x_reason": "fix"}


# ---------------------------------------------------------------------------
# Delta
# ---------------------------------------------------------------------------


class TestDelta:
    def test_construction(self) -> None:
        delta = Delta({
            "format": "json-delta",
            "version": 1,
            "operations": [
                {"op": "add", "path": "$.name", "value": "Alice"},
            ],
        })
        assert delta.format == "json-delta"
        assert delta.version == 1
        assert len(delta.operations) == 1

    def test_operations_are_operation_instances(self) -> None:
        delta = Delta({
            "format": "json-delta",
            "version": 1,
            "operations": [{"op": "add", "path": "$", "value": 1}],
        })
        assert isinstance(delta.operations[0], Operation)

    def test_operations_already_wrapped(self) -> None:
        op = Operation(op="add", path="$", value=1)
        delta = Delta({"format": "json-delta", "version": 1, "operations": [op]})
        assert delta.operations[0] is op

    def test_dict_access(self) -> None:
        delta = Delta({"format": "json-delta", "version": 1, "operations": []})
        assert delta["format"] == "json-delta"
        assert delta["version"] == 1
        assert delta["operations"] == []

    def test_isinstance_dict(self) -> None:
        delta = Delta({"format": "json-delta", "version": 1, "operations": []})
        assert isinstance(delta, dict)

    def test_json_serializable(self) -> None:
        delta = Delta({
            "format": "json-delta",
            "version": 1,
            "operations": [{"op": "add", "path": "$.x", "value": 42}],
        })
        result = json.loads(json.dumps(delta))
        assert result["format"] == "json-delta"
        assert result["operations"][0]["op"] == "add"

    def test_extension_properties(self) -> None:
        delta = Delta({"format": "json-delta", "version": 1, "operations": []})
        delta["x_agent"] = "test-agent"
        assert delta["x_agent"] == "test-agent"

    def test_is_empty_true(self) -> None:
        delta = Delta({"format": "json-delta", "version": 1, "operations": []})
        assert delta.is_empty is True

    def test_is_empty_false(self) -> None:
        delta = Delta({
            "format": "json-delta",
            "version": 1,
            "operations": [{"op": "add", "path": "$.x", "value": 1}],
        })
        assert delta.is_empty is False

    def test_is_reversible_true(self) -> None:
        delta = Delta({
            "format": "json-delta",
            "version": 1,
            "operations": [
                {"op": "replace", "path": "$.x", "value": 2, "oldValue": 1},
                {"op": "remove", "path": "$.y", "oldValue": "gone"},
                {"op": "add", "path": "$.z", "value": "new"},
            ],
        })
        assert delta.is_reversible is True

    def test_is_reversible_false(self) -> None:
        delta = Delta({
            "format": "json-delta",
            "version": 1,
            "operations": [
                {"op": "replace", "path": "$.x", "value": 2},  # no oldValue
            ],
        })
        assert delta.is_reversible is False

    def test_is_reversible_empty(self) -> None:
        delta = Delta({"format": "json-delta", "version": 1, "operations": []})
        assert delta.is_reversible is True

    def test_repr(self) -> None:
        delta = Delta({
            "format": "json-delta",
            "version": 1,
            "operations": [{"op": "add", "path": "$", "value": 1}],
        })
        assert "1 operations" in repr(delta)

    def test_apply_method(self) -> None:
        delta = Delta({
            "format": "json-delta",
            "version": 1,
            "operations": [{"op": "add", "path": "$.name", "value": "Alice"}],
        })
        result = delta.apply({})
        assert result == {"name": "Alice"}

    def test_invert_method(self) -> None:
        delta = Delta({
            "format": "json-delta",
            "version": 1,
            "operations": [{"op": "replace", "path": "$.x", "value": 2, "oldValue": 1}],
        })
        inv = delta.invert()
        assert isinstance(inv, Delta)
        assert inv.operations[0].op == "replace"
        assert inv.operations[0].value == 1
        assert inv.operations[0].old_value == 2

    def test_revert_method(self) -> None:
        source = {"x": 1}
        target = {"x": 2}
        from json_delta import diff_delta

        delta = diff_delta(source, target)
        result = delta.revert(copy.deepcopy(target))
        assert result == source

    def test_to_json_patch_method(self) -> None:
        delta = Delta({
            "format": "json-delta",
            "version": 1,
            "operations": [{"op": "replace", "path": "$.name", "value": "Bob"}],
        })
        patch = delta.to_json_patch({"name": "Alice"})
        assert len(patch) == 1
        assert patch[0] == {"op": "replace", "path": "/name", "value": "Bob"}

    def test_from_json_patch_classmethod(self) -> None:
        patch = [{"op": "add", "path": "/name", "value": "Alice"}]
        delta = Delta.from_json_patch(patch)
        assert isinstance(delta, Delta)
        assert delta.format == "json-delta"
        assert delta.operations[0].op == "add"

    # -- Delta.from_dict() --------------------------------------------------

    def test_from_dict_valid(self) -> None:
        raw = {
            "format": "json-delta",
            "version": 1,
            "operations": [{"op": "add", "path": "$.x", "value": 1}],
        }
        delta = Delta.from_dict(raw)
        assert isinstance(delta, Delta)
        assert delta.format == "json-delta"
        assert len(delta.operations) == 1
        assert isinstance(delta.operations[0], Operation)

    def test_from_dict_with_extensions(self) -> None:
        raw = {
            "format": "json-delta",
            "version": 1,
            "operations": [],
            "x_agent": "test",
        }
        delta = Delta.from_dict(raw)
        assert delta["x_agent"] == "test"

    def test_from_dict_missing_operations(self) -> None:
        with pytest.raises(ValueError, match="missing keys.*operations"):
            Delta.from_dict({"format": "json-delta", "version": 1})

    def test_from_dict_missing_format(self) -> None:
        with pytest.raises(ValueError, match="missing keys.*format"):
            Delta.from_dict({"version": 1, "operations": []})

    def test_from_dict_empty_dict(self) -> None:
        with pytest.raises(ValueError, match="missing keys"):
            Delta.from_dict({})

    # -- __getattr__ (extension attribute access) ---------------------------

    def test_delta_getattr_extension(self) -> None:
        delta = Delta.create(Operation.add("$.x", 1), x_agent="test-agent")
        assert delta.x_agent == "test-agent"

    def test_delta_getattr_missing_raises(self) -> None:
        delta = Delta.create()
        with pytest.raises(AttributeError, match="no attribute"):
            _ = delta.nonexistent

    # -- __dir__ ------------------------------------------------------------

    def test_delta_dir_includes_extensions(self) -> None:
        delta = Delta.create(x_agent="test")
        d = dir(delta)
        assert "x_agent" in d
        assert "operations" in d

    # -- extensions property ------------------------------------------------

    def test_delta_extensions(self) -> None:
        delta = Delta.create(Operation.add("$.x", 1), x_agent="test", x_ts="2024-01-01")
        assert delta.extensions == {"x_agent": "test", "x_ts": "2024-01-01"}

    def test_delta_extensions_empty(self) -> None:
        delta = Delta.create()
        assert delta.extensions == {}

    def test_delta_extensions_excludes_spec_keys(self) -> None:
        delta = Delta.create(Operation.add("$.x", 1), x_meta="info")
        assert "format" not in delta.extensions
        assert "version" not in delta.extensions
        assert "operations" not in delta.extensions
        assert delta.extensions == {"x_meta": "info"}

    # -- Delta.create() factory ---------------------------------------------

    def test_create_with_operations(self) -> None:
        delta = Delta.create(
            Operation.add("$.name", "Alice"),
            Operation.replace("$.age", 31, old_value=30),
        )
        assert delta.format == "json-delta"
        assert delta.version == 1
        assert len(delta.operations) == 2
        assert delta.operations[0].op == "add"
        assert delta.operations[1].op == "replace"

    def test_create_empty(self) -> None:
        delta = Delta.create()
        assert delta.format == "json-delta"
        assert delta.is_empty

    def test_create_with_extensions(self) -> None:
        delta = Delta.create(
            Operation.add("$.x", 1),
            x_agent="test-agent",
        )
        assert delta["x_agent"] == "test-agent"
        assert len(delta.operations) == 1

    def test_create_with_raw_dicts(self) -> None:
        delta = Delta.create({"op": "add", "path": "$.x", "value": 1})
        assert isinstance(delta.operations[0], Operation)
        assert delta.operations[0].op == "add"

    # -- Iteration protocol -------------------------------------------------

    def test_iter_operations(self) -> None:
        delta = Delta.create(
            Operation.add("$.a", 1),
            Operation.add("$.b", 2),
        )
        ops = list(delta)
        assert len(ops) == 2
        assert ops[0].path == "$.a"
        assert ops[1].path == "$.b"

    def test_len_returns_operation_count(self) -> None:
        delta = Delta.create(
            Operation.add("$.a", 1),
            Operation.add("$.b", 2),
            Operation.add("$.c", 3),
        )
        assert len(delta) == 3

    def test_len_empty(self) -> None:
        delta = Delta.create()
        assert len(delta) == 0

    def test_bool_true_when_has_operations(self) -> None:
        delta = Delta.create(Operation.add("$.x", 1))
        assert bool(delta) is True
        assert delta  # truthy

    def test_bool_false_when_empty(self) -> None:
        delta = Delta.create()
        assert bool(delta) is False
        assert not delta  # falsy

    def test_for_loop(self) -> None:
        delta = Delta.create(
            Operation.add("$.name", "Alice"),
            Operation.replace("$.age", 31),
        )
        paths = [op.path for op in delta]
        assert paths == ["$.name", "$.age"]

    # -- Combining (+) ------------------------------------------------------

    def test_add_deltas(self) -> None:
        d1 = Delta.create(Operation.add("$.x", 1))
        d2 = Delta.create(Operation.add("$.y", 2))
        combined = d1 + d2
        assert isinstance(combined, Delta)
        assert len(combined) == 2
        assert combined.operations[0].path == "$.x"
        assert combined.operations[1].path == "$.y"

    def test_add_preserves_extensions(self) -> None:
        d1 = Delta.create(Operation.add("$.x", 1), x_source="d1")
        d2 = Delta.create(Operation.add("$.y", 2), x_source="d2")
        combined = d1 + d2
        assert combined["x_source"] == "d2"  # other wins on conflict

    def test_add_invalid_type(self) -> None:
        delta = Delta.create(Operation.add("$.x", 1))
        result = delta.__add__({"not": "a delta"})
        assert result is NotImplemented

    # -- Filtering ----------------------------------------------------------

    def test_filter_by_op_type(self) -> None:
        delta = Delta.create(
            Operation.add("$.name", "Alice"),
            Operation.replace("$.age", 31),
            Operation.remove("$.old"),
        )
        adds = delta.filter(lambda op: op.op == "add")
        assert len(adds) == 1
        assert adds.operations[0].path == "$.name"

    def test_filter_by_path(self) -> None:
        delta = Delta.create(
            Operation.replace("$.user.name", "Bob"),
            Operation.replace("$.user.email", "bob@x.com"),
            Operation.replace("$.settings.theme", "dark"),
        )
        user_changes = delta.filter(lambda op: op.path.startswith("$.user"))
        assert len(user_changes) == 2

    def test_filter_preserves_envelope(self) -> None:
        delta = Delta.create(
            Operation.add("$.x", 1),
            Operation.add("$.y", 2),
            x_agent="test",
        )
        filtered = delta.filter(lambda op: op.path == "$.x")
        assert filtered["x_agent"] == "test"
        assert filtered.format == "json-delta"

    def test_filter_empty_result(self) -> None:
        delta = Delta.create(Operation.add("$.x", 1))
        empty = delta.filter(lambda op: op.op == "remove")
        assert empty.is_empty
        assert not empty

    # -- affected_paths -----------------------------------------------------

    def test_affected_paths(self) -> None:
        delta = Delta.create(
            Operation.replace("$.user.name", "Bob"),
            Operation.add("$.user.email", "bob@x.com"),
            Operation.remove("$.old"),
        )
        assert delta.affected_paths == {"$.user.name", "$.user.email", "$.old"}

    def test_affected_paths_empty(self) -> None:
        delta = Delta.create()
        assert delta.affected_paths == set()

    def test_affected_paths_deduplicates(self) -> None:
        delta = Delta.create(
            Operation.replace("$.x", 1),
            Operation.replace("$.x", 2),
        )
        assert delta.affected_paths == {"$.x"}

    # -- summary() ----------------------------------------------------------

    def test_summary_basic(self) -> None:
        delta = Delta.create(
            Operation.replace("$.user.name", "Bob"),
            Operation.add("$.user.email", "bob@x.com"),
            Operation.remove("$.old"),
        )
        s = delta.summary()
        assert "replace: user > name" in s
        assert "add: user > email" in s
        assert "remove: old" in s

    def test_summary_empty(self) -> None:
        delta = Delta.create()
        assert delta.summary() == "(no changes)"

    def test_summary_includes_values(self) -> None:
        delta = Delta.create(Operation.replace("$.x", 42))
        s = delta.summary()
        assert "= 42" in s

    def test_summary_with_document(self) -> None:
        doc = {"items": [{"id": 1, "name": "Widget"}]}
        delta = Delta.create(
            Operation.replace("$.items[?(@.id==1)].name", "Gadget"),
        )
        s = delta.summary(doc)
        assert "/items/0/name" in s

    def test_diff_returns_delta(self) -> None:
        from json_delta import diff_delta

        delta = diff_delta({"x": 1}, {"x": 2})
        assert isinstance(delta, Delta)
        assert isinstance(delta.operations[0], Operation)
        assert delta.operations[0].op == "replace"
        assert delta.operations[0].path == "$.x"

    def test_invert_returns_delta(self) -> None:
        from json_delta import diff_delta, invert_delta

        delta = diff_delta({"x": 1}, {"x": 2})
        inv = invert_delta(delta)
        assert isinstance(inv, Delta)
        assert isinstance(inv.operations[0], Operation)
