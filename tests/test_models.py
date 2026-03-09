"""Tests for json_delta.models — PathSegment types, ValidationResult, Delta, Operation."""

import copy
import json

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
