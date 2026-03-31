"""Enriched comparison tree for visual diff rendering.

Builds a tree of :class:`ComparisonNode` instances that classifies every value
as unchanged, added, removed, replaced, or container.  Unlike :func:`diff_delta`,
which produces a flat list of operations, :func:`compare` returns the full
document structure — including unchanged values — so you can render side-by-side
diffs, change-highlighted UIs, or detailed audit views.
"""

from __future__ import annotations

from typing import Any

from json_atom._identity import (
    ArrayIdentityKeys,
    _ResolvedIdentity,
    extract_identity,
    resolve_identity,
)
from json_atom._utils import json_equal, make_hashable, should_exclude_path, validate_json_value
from json_atom.errors import DiffError
from json_atom.models import ChangeType, ComparisonNode


def compare(
    old_obj: Any,
    new_obj: Any,
    *,
    array_identity_keys: ArrayIdentityKeys | None = None,
    exclude_keys: set[str] | None = None,
    exclude_paths: set[str] | None = None,
) -> ComparisonNode:
    """Build an enriched comparison tree showing all values and their change status.

    Unlike :func:`diff_delta` which produces flat operations, ``compare()``
    returns a tree including unchanged values — ideal for rendering
    side-by-side diffs or change-highlighted UIs.

    Args:
        old_obj: The source document.
        new_obj: The target document.
        array_identity_keys: Optional identity key mapping for arrays.
            Accepts the same forms as :func:`diff_delta`: string keys,
            ``(str, Callable)`` tuples, :class:`IdentityResolver` instances,
            and ``re.Pattern`` dict keys.
        exclude_keys: Property names to skip at any depth.
        exclude_paths: Dotted property paths to skip at a specific depth.

    Returns:
        A :class:`ComparisonNode` tree where each node is classified as
        ``unchanged``, ``added``, ``removed``, ``replaced``, or ``container``.

    Raises:
        DiffError: If the input contains non-JSON values.

    Example::

        node = compare(
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 30},
        )
        # node.type == ChangeType.CONTAINER
        # node.value["name"].type == ChangeType.REPLACED
        # node.value["age"].type == ChangeType.UNCHANGED
    """
    validate_json_value(old_obj, "old_obj")
    validate_json_value(new_obj, "new_obj")
    keys = array_identity_keys or {}
    _exclude: frozenset[str] = frozenset(exclude_keys) if exclude_keys else frozenset()
    _exclude_paths: frozenset[str] = frozenset(exclude_paths) if exclude_paths else frozenset()
    return _compare_values(old_obj, new_obj, [], keys, _exclude, _exclude_paths)


# ---------------------------------------------------------------------------
# Recursive comparison
# ---------------------------------------------------------------------------


def _compare_values(
    old: Any,
    new: Any,
    prop_path: list[str],
    identity_keys: ArrayIdentityKeys,
    exclude: frozenset[str],
    exclude_paths: frozenset[str],
) -> ComparisonNode:
    """Recursively compare two values and produce a ComparisonNode."""
    if json_equal(old, new):
        # Enrich from `new` so the tree reflects the target document's
        # structure/values (e.g. 1.0 vs 1, dict insertion order).
        return _enrich_unchanged(new, prop_path, exclude, exclude_paths)

    old_is_dict = isinstance(old, dict) and not isinstance(old, bool)
    new_is_dict = isinstance(new, dict) and not isinstance(new, bool)
    old_is_list = isinstance(old, list)
    new_is_list = isinstance(new, list)

    if old_is_dict and new_is_dict:
        return _compare_objects(old, new, prop_path, identity_keys, exclude, exclude_paths)
    elif old_is_list and new_is_list:
        return _compare_arrays(old, new, prop_path, identity_keys, exclude, exclude_paths)

    # Type change or scalar difference
    return ComparisonNode(type=ChangeType.REPLACED, value=new, old_value=old)


def _enrich_unchanged(
    value: Any,
    prop_path: list[str],
    exclude: frozenset[str],
    exclude_paths: frozenset[str],
) -> ComparisonNode:
    """Wrap an unchanged value as a ComparisonNode tree.

    Containers get ``ChangeType.CONTAINER`` with per-child nodes.
    Leaves get ``ChangeType.UNCHANGED``.
    Excluded keys and paths are filtered out so they never appear in the tree.
    """
    if isinstance(value, dict) and not isinstance(value, bool):
        obj_children: dict[str, ComparisonNode] = {}
        for k, v in value.items():
            if k in exclude:
                continue
            if should_exclude_path(prop_path, k, exclude_paths):
                continue
            obj_children[k] = _enrich_unchanged(v, [*prop_path, k], exclude, exclude_paths)
        return ComparisonNode(type=ChangeType.CONTAINER, value=obj_children)
    if isinstance(value, list):
        arr_children = [_enrich_unchanged(v, prop_path, exclude, exclude_paths) for v in value]
        return ComparisonNode(type=ChangeType.CONTAINER, value=arr_children)
    return ComparisonNode(type=ChangeType.UNCHANGED, value=value)


# ---------------------------------------------------------------------------
# Object comparison
# ---------------------------------------------------------------------------


def _compare_objects(
    old: dict[str, Any],
    new: dict[str, Any],
    prop_path: list[str],
    identity_keys: ArrayIdentityKeys,
    exclude: frozenset[str],
    exclude_paths: frozenset[str],
) -> ComparisonNode:
    """Compare two objects and produce a container node with per-key children."""
    children: dict[str, ComparisonNode] = {}
    all_keys = sorted((set(old.keys()) | set(new.keys())) - exclude)

    for key in all_keys:
        if should_exclude_path(prop_path, key, exclude_paths):
            continue

        child_path = [*prop_path, key]
        if key in old and key not in new:
            children[key] = _enrich_removed(old[key], child_path, exclude, exclude_paths)
        elif key not in old and key in new:
            children[key] = _enrich_added(new[key], child_path, exclude, exclude_paths)
        else:
            children[key] = _compare_values(
                old[key], new[key], child_path, identity_keys, exclude, exclude_paths,
            )

    return ComparisonNode(type=ChangeType.CONTAINER, value=children)


# ---------------------------------------------------------------------------
# Array comparison
# ---------------------------------------------------------------------------


def _compare_arrays(
    old: list[Any],
    new: list[Any],
    prop_path: list[str],
    identity_keys: ArrayIdentityKeys,
    exclude: frozenset[str],
    exclude_paths: frozenset[str],
) -> ComparisonNode:
    """Compare two arrays using the appropriate identity model."""
    identity = resolve_identity(prop_path, identity_keys)

    if identity.mode == "$index":
        return _compare_arrays_index(old, new, prop_path, identity_keys, exclude, exclude_paths)
    elif identity.mode == "$value":
        return _compare_arrays_value(old, new, prop_path, exclude, exclude_paths)
    else:
        return _compare_arrays_keyed(old, new, prop_path, identity_keys, exclude, exclude_paths, identity)


def _compare_arrays_index(
    old: list[Any],
    new: list[Any],
    prop_path: list[str],
    identity_keys: ArrayIdentityKeys,
    exclude: frozenset[str],
    exclude_paths: frozenset[str],
) -> ComparisonNode:
    """Compare arrays by positional index."""
    children: list[ComparisonNode] = []
    max_len = max(len(old), len(new))

    for i in range(max_len):
        if i < len(old) and i < len(new):
            children.append(_compare_values(old[i], new[i], prop_path, identity_keys, exclude, exclude_paths))
        elif i >= len(old):
            children.append(_enrich_added(new[i], prop_path, exclude, exclude_paths))
        else:
            children.append(_enrich_removed(old[i], prop_path, exclude, exclude_paths))

    return ComparisonNode(type=ChangeType.CONTAINER, value=children)


def _compare_arrays_keyed(
    old: list[Any],
    new: list[Any],
    prop_path: list[str],
    identity_keys: ArrayIdentityKeys,
    exclude: frozenset[str],
    exclude_paths: frozenset[str],
    identity: _ResolvedIdentity,
) -> ComparisonNode:
    """Compare arrays by key-based identity."""
    key_property = identity.key_property
    if key_property is None:  # pragma: no cover — guaranteed by resolve_identity for mode="key"
        msg = "key_property must be set for mode='key'"
        raise ValueError(msg)
    resolver = identity.resolver
    path_ctx = ".".join(prop_path) if prop_path else "$"

    # Build lookup maps preserving order; detect duplicates
    old_by_key: dict[Any, Any] = {}
    old_order: list[Any] = []
    for elem in old:
        key_val = extract_identity(elem, key_property, resolver)
        hashable_key = make_hashable(key_val)
        if hashable_key in old_by_key:
            raise DiffError(
                f"Duplicate identity '{key_property}=={key_val!r}' in old array at {path_ctx}"
            )
        old_by_key[hashable_key] = elem
        old_order.append(hashable_key)

    new_by_key: dict[Any, Any] = {}
    new_order: list[Any] = []
    for elem in new:
        key_val = extract_identity(elem, key_property, resolver)
        hashable_key = make_hashable(key_val)
        if hashable_key in new_by_key:
            raise DiffError(
                f"Duplicate identity '{key_property}=={key_val!r}' in new array at {path_ctx}"
            )
        new_by_key[hashable_key] = elem
        new_order.append(hashable_key)

    # Build children list following new order, then appending removed items
    children: list[ComparisonNode] = []

    # Items in new order (matched or added)
    for hashable_key in new_order:
        if hashable_key in old_by_key:
            children.append(
                _compare_values(old_by_key[hashable_key], new_by_key[hashable_key],
                                prop_path, identity_keys, exclude, exclude_paths)
            )
        else:
            children.append(_enrich_added(new_by_key[hashable_key], prop_path, exclude, exclude_paths))

    # Items removed (in old but not in new)
    for hashable_key in old_order:
        if hashable_key not in new_by_key:
            children.append(_enrich_removed(old_by_key[hashable_key], prop_path, exclude, exclude_paths))

    return ComparisonNode(type=ChangeType.CONTAINER, value=children)


def _compare_arrays_value(
    old: list[Any],
    new: list[Any],
    prop_path: list[str],
    exclude: frozenset[str],
    exclude_paths: frozenset[str],
) -> ComparisonNode:
    """Compare arrays by value identity (for primitive arrays)."""
    children: list[ComparisonNode] = []

    # Track matched counts for correct multiset semantics.
    # Without this, old=["a"] new=["a","a"] would wrongly match both.
    old_matched = [False] * len(old)

    for new_val in new:
        match_idx = _find_unmatched(new_val, old, old_matched)
        if match_idx is not None:
            old_matched[match_idx] = True
            children.append(_enrich_unchanged(new_val, prop_path, exclude, exclude_paths))
        else:
            children.append(_enrich_added(new_val, prop_path, exclude, exclude_paths))

    # Unmatched old values are removed
    for i, old_val in enumerate(old):
        if not old_matched[i]:
            children.append(_enrich_removed(old_val, prop_path, exclude, exclude_paths))

    return ComparisonNode(type=ChangeType.CONTAINER, value=children)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_unmatched(
    target: Any,
    candidates: list[Any],
    matched: list[bool],
) -> int | None:
    """Find the first unmatched candidate that equals *target*.

    Returns the index into *candidates*, or ``None`` if no match.
    """
    for i, candidate in enumerate(candidates):
        if not matched[i] and json_equal(target, candidate):
            return i
    return None


def _enrich_added(
    value: Any,
    prop_path: list[str],
    exclude: frozenset[str],
    exclude_paths: frozenset[str],
) -> ComparisonNode:
    """Wrap an added value as a ComparisonNode tree.

    Containers become ``CONTAINER`` nodes with all descendants marked ``ADDED``.
    Scalars become ``ADDED`` leaf nodes.
    Excluded keys and paths are filtered out.
    """
    if isinstance(value, dict) and not isinstance(value, bool):
        children: dict[str, ComparisonNode] = {}
        for k, v in value.items():
            if k in exclude:
                continue
            if should_exclude_path(prop_path, k, exclude_paths):
                continue
            children[k] = _enrich_added(v, [*prop_path, k], exclude, exclude_paths)
        return ComparisonNode(type=ChangeType.CONTAINER, value=children)
    if isinstance(value, list):
        children_list = [_enrich_added(v, prop_path, exclude, exclude_paths) for v in value]
        return ComparisonNode(type=ChangeType.CONTAINER, value=children_list)
    return ComparisonNode(type=ChangeType.ADDED, value=value)


def _enrich_removed(
    value: Any,
    prop_path: list[str],
    exclude: frozenset[str],
    exclude_paths: frozenset[str],
) -> ComparisonNode:
    """Wrap a removed value as a ComparisonNode tree.

    Containers become ``CONTAINER`` nodes with all descendants marked ``REMOVED``.
    Scalars become ``REMOVED`` leaf nodes.
    Excluded keys and paths are filtered out.
    """
    if isinstance(value, dict) and not isinstance(value, bool):
        children: dict[str, ComparisonNode] = {}
        for k, v in value.items():
            if k in exclude:
                continue
            if should_exclude_path(prop_path, k, exclude_paths):
                continue
            children[k] = _enrich_removed(v, [*prop_path, k], exclude, exclude_paths)
        return ComparisonNode(type=ChangeType.CONTAINER, value=children)
    if isinstance(value, list):
        children_list = [_enrich_removed(v, prop_path, exclude, exclude_paths) for v in value]
        return ComparisonNode(type=ChangeType.CONTAINER, value=children_list)
    return ComparisonNode(type=ChangeType.REMOVED, old_value=value)


