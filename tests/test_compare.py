"""Tests for json_delta.compare — enriched comparison tree."""

from json_delta._identity import IdentityResolver
from json_delta.compare import compare
from json_delta.models import ChangeType, ComparisonNode


# ---------------------------------------------------------------------------
# Identical / unchanged
# ---------------------------------------------------------------------------


class TestUnchanged:
    def test_identical_scalars(self) -> None:
        node = compare(42, 42)
        assert node.type == ChangeType.UNCHANGED
        assert node.value == 42

    def test_identical_strings(self) -> None:
        node = compare("hello", "hello")
        assert node.type == ChangeType.UNCHANGED

    def test_identical_none(self) -> None:
        node = compare(None, None)
        assert node.type == ChangeType.UNCHANGED
        assert node.value is None

    def test_identical_object(self) -> None:
        obj = {"name": "Alice", "age": 30}
        node = compare(obj, obj)
        assert node.type == ChangeType.CONTAINER
        assert isinstance(node.value, dict)
        assert node.value["name"].type == ChangeType.UNCHANGED
        assert node.value["name"].value == "Alice"
        assert node.value["age"].type == ChangeType.UNCHANGED
        assert node.value["age"].value == 30

    def test_identical_array(self) -> None:
        node = compare([1, 2, 3], [1, 2, 3])
        assert node.type == ChangeType.CONTAINER
        assert isinstance(node.value, list)
        assert len(node.value) == 3
        assert all(child.type == ChangeType.UNCHANGED for child in node.value)

    def test_identical_nested(self) -> None:
        obj = {"users": [{"id": 1, "name": "Alice"}]}
        node = compare(obj, obj)
        assert node.type == ChangeType.CONTAINER
        users_node = node.value["users"]
        assert users_node.type == ChangeType.CONTAINER
        assert users_node.value[0].type == ChangeType.CONTAINER


# ---------------------------------------------------------------------------
# Scalar changes
# ---------------------------------------------------------------------------


class TestScalarChanges:
    def test_string_replace(self) -> None:
        node = compare("hello", "world")
        assert node.type == ChangeType.REPLACED
        assert node.value == "world"
        assert node.old_value == "hello"

    def test_number_replace(self) -> None:
        node = compare(1, 2)
        assert node.type == ChangeType.REPLACED

    def test_null_to_value(self) -> None:
        node = compare(None, "hello")
        assert node.type == ChangeType.REPLACED
        assert node.value == "hello"
        assert node.old_value is None

    def test_value_to_null(self) -> None:
        node = compare("hello", None)
        assert node.type == ChangeType.REPLACED
        assert node.value is None
        assert node.old_value == "hello"

    def test_bool_vs_int(self) -> None:
        """True != 1 in JSON semantics."""
        node = compare(True, 1)
        assert node.type == ChangeType.REPLACED


# ---------------------------------------------------------------------------
# Object comparison
# ---------------------------------------------------------------------------


class TestObjectComparison:
    def test_property_replace(self) -> None:
        node = compare({"name": "Alice"}, {"name": "Bob"})
        assert node.type == ChangeType.CONTAINER
        assert node.value["name"].type == ChangeType.REPLACED
        assert node.value["name"].value == "Bob"
        assert node.value["name"].old_value == "Alice"

    def test_property_add(self) -> None:
        node = compare({"name": "Alice"}, {"name": "Alice", "role": "admin"})
        assert node.type == ChangeType.CONTAINER
        assert node.value["name"].type == ChangeType.UNCHANGED
        assert node.value["role"].type == ChangeType.ADDED
        assert node.value["role"].value == "admin"

    def test_property_remove(self) -> None:
        node = compare({"name": "Alice", "role": "admin"}, {"name": "Alice"})
        assert node.type == ChangeType.CONTAINER
        assert node.value["name"].type == ChangeType.UNCHANGED
        assert node.value["role"].type == ChangeType.REMOVED
        assert node.value["role"].old_value == "admin"

    def test_mixed_changes(self) -> None:
        old = {"a": 1, "b": 2, "c": 3}
        new = {"a": 1, "b": 99, "d": 4}
        node = compare(old, new)
        assert node.value["a"].type == ChangeType.UNCHANGED
        assert node.value["b"].type == ChangeType.REPLACED
        assert node.value["c"].type == ChangeType.REMOVED
        assert node.value["d"].type == ChangeType.ADDED

    def test_nested_object_changes(self) -> None:
        old = {"user": {"address": {"city": "Portland", "zip": "97201"}}}
        new = {"user": {"address": {"city": "Seattle", "zip": "97201"}}}
        node = compare(old, new)
        assert node.type == ChangeType.CONTAINER
        user = node.value["user"]
        assert user.type == ChangeType.CONTAINER
        addr = user.value["address"]
        assert addr.type == ChangeType.CONTAINER
        assert addr.value["city"].type == ChangeType.REPLACED
        assert addr.value["zip"].type == ChangeType.UNCHANGED


# ---------------------------------------------------------------------------
# Type changes
# ---------------------------------------------------------------------------


class TestTypeChanges:
    def test_object_to_array(self) -> None:
        node = compare({"key": "val"}, [1, 2, 3])
        assert node.type == ChangeType.REPLACED
        assert node.value == [1, 2, 3]
        assert node.old_value == {"key": "val"}

    def test_array_to_string(self) -> None:
        node = compare([1, 2], "hello")
        assert node.type == ChangeType.REPLACED

    def test_string_to_number(self) -> None:
        node = compare({"val": "42"}, {"val": 42})
        assert node.value["val"].type == ChangeType.REPLACED


# ---------------------------------------------------------------------------
# Index-based array comparison
# ---------------------------------------------------------------------------


class TestArraysIndex:
    def test_element_replace(self) -> None:
        node = compare([1, 2, 3], [1, 99, 3])
        assert node.type == ChangeType.CONTAINER
        assert node.value[0].type == ChangeType.UNCHANGED
        assert node.value[1].type == ChangeType.REPLACED
        assert node.value[1].value == 99
        assert node.value[1].old_value == 2
        assert node.value[2].type == ChangeType.UNCHANGED

    def test_element_add(self) -> None:
        node = compare([1, 2], [1, 2, 3])
        assert len(node.value) == 3
        assert node.value[0].type == ChangeType.UNCHANGED
        assert node.value[1].type == ChangeType.UNCHANGED
        assert node.value[2].type == ChangeType.ADDED
        assert node.value[2].value == 3

    def test_element_remove(self) -> None:
        node = compare([1, 2, 3], [1, 2])
        assert len(node.value) == 3
        assert node.value[0].type == ChangeType.UNCHANGED
        assert node.value[1].type == ChangeType.UNCHANGED
        assert node.value[2].type == ChangeType.REMOVED
        assert node.value[2].old_value == 3

    def test_nested_objects_in_array(self) -> None:
        old = [{"id": 1, "val": "a"}, {"id": 2, "val": "b"}]
        new = [{"id": 1, "val": "a"}, {"id": 2, "val": "x"}]
        node = compare(old, new)
        assert node.value[0].type == ChangeType.CONTAINER
        assert node.value[0].value["val"].type == ChangeType.UNCHANGED
        assert node.value[1].type == ChangeType.CONTAINER
        assert node.value[1].value["val"].type == ChangeType.REPLACED


# ---------------------------------------------------------------------------
# Key-based array comparison
# ---------------------------------------------------------------------------


class TestArraysKeyed:
    def test_keyed_update(self) -> None:
        old = {"items": [{"id": 1, "name": "Widget"}, {"id": 2, "name": "Gadget"}]}
        new = {"items": [{"id": 1, "name": "Widget Pro"}, {"id": 2, "name": "Gadget"}]}
        node = compare(old, new, array_identity_keys={"items": "id"})
        items = node.value["items"]
        assert items.type == ChangeType.CONTAINER
        # First item changed
        assert items.value[0].type == ChangeType.CONTAINER
        assert items.value[0].value["name"].type == ChangeType.REPLACED
        # Second item unchanged
        assert items.value[1].type == ChangeType.CONTAINER
        assert items.value[1].value["name"].type == ChangeType.UNCHANGED

    def test_keyed_add(self) -> None:
        old = {"items": [{"id": 1, "name": "Widget"}]}
        new = {"items": [{"id": 1, "name": "Widget"}, {"id": 2, "name": "Gadget"}]}
        node = compare(old, new, array_identity_keys={"items": "id"})
        items = node.value["items"]
        assert len(items.value) == 2
        assert items.value[0].type == ChangeType.CONTAINER  # unchanged match
        # Added dict is wrapped as CONTAINER with ADDED leaf children
        added = items.value[1]
        assert added.type == ChangeType.CONTAINER
        assert added.value["id"].type == ChangeType.ADDED
        assert added.value["name"].type == ChangeType.ADDED
        assert added.value["name"].value == "Gadget"

    def test_keyed_remove(self) -> None:
        old = {"items": [{"id": 1, "name": "Widget"}, {"id": 2, "name": "Gadget"}]}
        new = {"items": [{"id": 1, "name": "Widget"}]}
        node = compare(old, new, array_identity_keys={"items": "id"})
        items = node.value["items"]
        assert len(items.value) == 2
        assert items.value[0].type == ChangeType.CONTAINER  # matched
        # Removed dict is wrapped as CONTAINER with REMOVED leaf children
        removed = items.value[1]
        assert removed.type == ChangeType.CONTAINER
        assert removed.value["id"].type == ChangeType.REMOVED
        assert removed.value["name"].type == ChangeType.REMOVED
        assert removed.value["name"].old_value == "Gadget"

    def test_keyed_with_callable(self) -> None:
        old = {"items": [{"sku": "A", "val": 1}]}
        new = {"items": [{"sku": "A", "val": 2}]}
        node = compare(
            old, new,
            array_identity_keys={"items": ("sku", lambda e: e["sku"])},
        )
        items = node.value["items"]
        assert items.value[0].value["val"].type == ChangeType.REPLACED

    def test_keyed_with_identity_resolver(self) -> None:
        old = {"items": [{"id": 1, "val": "a"}]}
        new = {"items": [{"id": 1, "val": "b"}]}
        node = compare(
            old, new,
            array_identity_keys={"items": IdentityResolver("id", lambda e: e["id"])},
        )
        assert node.value["items"].value[0].value["val"].type == ChangeType.REPLACED


# ---------------------------------------------------------------------------
# Value-based array comparison
# ---------------------------------------------------------------------------


class TestArraysValue:
    def test_value_unchanged(self) -> None:
        node = compare(
            {"tags": ["urgent", "review"]},
            {"tags": ["urgent", "review"]},
            array_identity_keys={"tags": "$value"},
        )
        tags = node.value["tags"]
        assert all(child.type == ChangeType.UNCHANGED for child in tags.value)

    def test_value_add(self) -> None:
        node = compare(
            {"tags": ["urgent"]},
            {"tags": ["urgent", "review"]},
            array_identity_keys={"tags": "$value"},
        )
        tags = node.value["tags"]
        types = [child.type for child in tags.value]
        assert ChangeType.UNCHANGED in types
        assert ChangeType.ADDED in types

    def test_value_remove(self) -> None:
        node = compare(
            {"tags": ["urgent", "draft"]},
            {"tags": ["urgent"]},
            array_identity_keys={"tags": "$value"},
        )
        tags = node.value["tags"]
        types = [child.type for child in tags.value]
        assert ChangeType.UNCHANGED in types
        assert ChangeType.REMOVED in types


# ---------------------------------------------------------------------------
# ComparisonNode is frozen
# ---------------------------------------------------------------------------


class TestExcludeKeys:
    def test_exclude_key_at_top_level(self) -> None:
        node = compare(
            {"name": "Alice", "cache": "old"},
            {"name": "Alice", "cache": "new"},
            exclude_keys={"cache"},
        )
        assert "cache" not in node.value

    def test_exclude_key_at_any_depth(self) -> None:
        node = compare(
            {"user": {"name": "Alice", "cache": "a"}, "product": {"cache": "b"}},
            {"user": {"name": "Alice", "cache": "x"}, "product": {"cache": "y"}},
            exclude_keys={"cache"},
        )
        assert "cache" not in node.value["user"].value
        assert "cache" not in node.value["product"].value

    def test_exclude_multiple_keys(self) -> None:
        node = compare(
            {"a": 1, "b": 2, "c": 3},
            {"a": 1, "b": 99, "c": 99},
            exclude_keys={"b", "c"},
        )
        assert set(node.value.keys()) == {"a"}
        assert node.value["a"].type == ChangeType.UNCHANGED

    def test_exclude_key_in_unchanged_subtree(self) -> None:
        """Excluded keys are filtered even when the surrounding object is unchanged."""
        obj = {"user": {"name": "Alice", "cache": "x"}}
        node = compare(obj, obj, exclude_keys={"cache"})
        assert "cache" not in node.value["user"].value
        assert node.value["user"].value["name"].type == ChangeType.UNCHANGED

    def test_exclude_key_in_added_container(self) -> None:
        """Excluded keys are filtered inside newly added containers."""
        node = compare(
            {},
            {"user": {"name": "Alice", "cache": "x"}},
            exclude_keys={"cache"},
        )
        user = node.value["user"]
        assert user.type == ChangeType.CONTAINER
        assert "cache" not in user.value
        assert user.value["name"].type == ChangeType.ADDED

    def test_exclude_key_in_removed_container(self) -> None:
        """Excluded keys are filtered inside removed containers."""
        node = compare(
            {"user": {"name": "Alice", "cache": "x"}},
            {},
            exclude_keys={"cache"},
        )
        user = node.value["user"]
        assert user.type == ChangeType.CONTAINER
        assert "cache" not in user.value
        assert user.value["name"].type == ChangeType.REMOVED


class TestExcludePaths:
    def test_exclude_specific_path(self) -> None:
        node = compare(
            {"user": {"name": "Alice", "cache": "a"}, "product": {"cache": "b"}},
            {"user": {"name": "Alice", "cache": "x"}, "product": {"cache": "y"}},
            exclude_paths={"user.cache"},
        )
        # user.cache excluded
        assert "cache" not in node.value["user"].value
        # product.cache NOT excluded
        assert "cache" in node.value["product"].value
        assert node.value["product"].value["cache"].type == ChangeType.REPLACED

    def test_exclude_path_in_unchanged_subtree(self) -> None:
        """Excluded paths are filtered even when the surrounding object is unchanged."""
        obj = {"user": {"name": "Alice", "cache": "x"}, "product": {"cache": "y"}}
        node = compare(obj, obj, exclude_paths={"user.cache"})
        assert "cache" not in node.value["user"].value
        # product.cache should still be present
        assert "cache" in node.value["product"].value

    def test_exclude_path_in_added_container(self) -> None:
        """Excluded paths are filtered inside newly added containers."""
        node = compare(
            {},
            {"user": {"name": "Alice", "cache": "x"}},
            exclude_paths={"user.cache"},
        )
        user = node.value["user"]
        assert "cache" not in user.value
        assert user.value["name"].type == ChangeType.ADDED

    def test_exclude_path_in_removed_container(self) -> None:
        """Excluded paths are filtered inside removed containers."""
        node = compare(
            {"user": {"name": "Alice", "cache": "x"}},
            {},
            exclude_paths={"user.cache"},
        )
        user = node.value["user"]
        assert "cache" not in user.value
        assert user.value["name"].type == ChangeType.REMOVED

    def test_combined_exclude_keys_and_paths(self) -> None:
        node = compare(
            {"a": {"x": 1, "y": 2}, "b": {"x": 3, "y": 4}},
            {"a": {"x": 1, "y": 99}, "b": {"x": 99, "y": 99}},
            exclude_keys={"y"},
            exclude_paths={"b.x"},
        )
        # y excluded everywhere
        assert "y" not in node.value["a"].value
        assert "y" not in node.value["b"].value
        # b.x excluded specifically
        assert "x" not in node.value["b"].value
        # a.x still present
        assert node.value["a"].value["x"].type == ChangeType.UNCHANGED


class TestEmptyContainers:
    def test_empty_objects(self) -> None:
        node = compare({}, {})
        assert node.type == ChangeType.CONTAINER
        assert node.value == {}

    def test_empty_arrays(self) -> None:
        node = compare([], [])
        assert node.type == ChangeType.CONTAINER
        assert node.value == []

    def test_empty_to_populated_object(self) -> None:
        node = compare({}, {"name": "Alice"})
        assert node.value["name"].type == ChangeType.ADDED

    def test_empty_to_populated_array(self) -> None:
        node = compare([], [1, 2])
        assert len(node.value) == 2
        assert all(c.type == ChangeType.ADDED for c in node.value)

    def test_populated_to_empty_object(self) -> None:
        node = compare({"name": "Alice"}, {})
        assert node.value["name"].type == ChangeType.REMOVED

    def test_populated_to_empty_array(self) -> None:
        node = compare([1, 2], [])
        assert len(node.value) == 2
        assert all(c.type == ChangeType.REMOVED for c in node.value)


class TestEnrichedAddRemove:
    """ADDED/REMOVED container values are recursively wrapped as CONTAINER nodes."""

    def test_added_object_is_enriched(self) -> None:
        node = compare({}, {"user": {"name": "Alice", "age": 30}})
        user = node.value["user"]
        assert user.type == ChangeType.CONTAINER
        assert user.value["name"].type == ChangeType.ADDED
        assert user.value["name"].value == "Alice"
        assert user.value["age"].type == ChangeType.ADDED

    def test_removed_object_is_enriched(self) -> None:
        node = compare({"user": {"name": "Alice"}}, {})
        user = node.value["user"]
        assert user.type == ChangeType.CONTAINER
        assert user.value["name"].type == ChangeType.REMOVED
        assert user.value["name"].old_value == "Alice"

    def test_added_array_is_enriched(self) -> None:
        node = compare({}, {"tags": ["a", "b"]})
        tags = node.value["tags"]
        assert tags.type == ChangeType.CONTAINER
        assert len(tags.value) == 2
        assert all(c.type == ChangeType.ADDED for c in tags.value)

    def test_removed_nested_structure(self) -> None:
        old = {"data": {"items": [{"id": 1}]}}
        node = compare(old, {})
        data = node.value["data"]
        assert data.type == ChangeType.CONTAINER
        items = data.value["items"]
        assert items.type == ChangeType.CONTAINER
        assert items.value[0].type == ChangeType.CONTAINER
        assert items.value[0].value["id"].type == ChangeType.REMOVED


class TestDuplicateIdentity:
    """Duplicate identity keys in keyed arrays raise DiffError."""

    def test_duplicate_in_old_array(self) -> None:
        import pytest
        from json_delta.errors import DiffError
        with pytest.raises(DiffError, match="Duplicate identity.*at items"):
            compare(
                {"items": [{"id": 1, "v": "a"}, {"id": 1, "v": "b"}]},
                {"items": [{"id": 1, "v": "a"}]},
                array_identity_keys={"items": "id"},
            )

    def test_duplicate_in_new_array(self) -> None:
        import pytest
        from json_delta.errors import DiffError
        with pytest.raises(DiffError, match="Duplicate identity.*at items"):
            compare(
                {"items": [{"id": 1, "v": "a"}]},
                {"items": [{"id": 1, "v": "a"}, {"id": 1, "v": "b"}]},
                array_identity_keys={"items": "id"},
            )


class TestValueMultiset:
    """Value-based comparison uses multiset semantics for duplicates."""

    def test_duplicate_add(self) -> None:
        node = compare(
            {"tags": ["a"]},
            {"tags": ["a", "a"]},
            array_identity_keys={"tags": "$value"},
        )
        tags = node.value["tags"]
        types = [c.type for c in tags.value]
        assert types.count(ChangeType.UNCHANGED) == 1
        assert types.count(ChangeType.ADDED) == 1

    def test_duplicate_remove(self) -> None:
        node = compare(
            {"tags": ["a", "a"]},
            {"tags": ["a"]},
            array_identity_keys={"tags": "$value"},
        )
        tags = node.value["tags"]
        types = [c.type for c in tags.value]
        assert types.count(ChangeType.UNCHANGED) == 1
        assert types.count(ChangeType.REMOVED) == 1

    def test_all_duplicates_unchanged(self) -> None:
        node = compare(
            {"tags": ["a", "a"]},
            {"tags": ["a", "a"]},
            array_identity_keys={"tags": "$value"},
        )
        tags = node.value["tags"]
        assert all(c.type == ChangeType.UNCHANGED for c in tags.value)


class TestComparisonNodeProperties:
    def test_frozen(self) -> None:
        node = ComparisonNode(type=ChangeType.UNCHANGED, value=42)
        import pytest
        with pytest.raises(AttributeError):
            node.type = ChangeType.ADDED  # type: ignore[misc]

    def test_repr(self) -> None:
        node = ComparisonNode(type=ChangeType.REPLACED, value="new", old_value="old")
        assert "REPLACED" in repr(node)
