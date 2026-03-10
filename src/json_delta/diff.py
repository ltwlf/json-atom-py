"""Compute a JSON Delta document from two objects.

Non-normative — the spec defines what a delta looks like, not how to produce one.
The key invariant: apply(source, diff(source, target)) == target.
"""

from __future__ import annotations

import math
from typing import Any

from json_delta._utils import json_equal
from json_delta.errors import DiffError
from json_delta.models import (
    Delta,
    IndexSegment,
    KeyFilterSegment,
    Operation,
    PropertySegment,
    ValueFilterSegment,
)
from json_delta.path import build_path

type _Segment = PropertySegment | IndexSegment | KeyFilterSegment | ValueFilterSegment


def diff_delta(
    old_obj: Any,
    new_obj: Any,
    *,
    array_keys: dict[str, str] | None = None,
    exclude_keys: set[str] | None = None,
    reversible: bool = True,
) -> Delta:
    """Compute a JSON Delta between two objects.

    Args:
        old_obj: The source document.
        new_obj: The target document.
        array_keys: Mapping from dotted property path to identity key.
            - A string key name (e.g., ``"id"``) → key-based identity.
            - ``"$value"`` → value-based identity.
            - ``"$index"`` → index-based identity (also the default).
        exclude_keys: Property names to skip during comparison at any depth.
            Matching keys are invisible to the diff engine — they produce no
            operations regardless of whether they differ, are added, or removed.
        reversible: If True (default), include ``oldValue`` on replace/remove.

    Returns:
        A :class:`Delta` document with typed :class:`Operation` instances.

    Raises:
        DiffError: If the input contains non-JSON values.
    """
    _validate_json_value(old_obj, "old_obj")
    _validate_json_value(new_obj, "new_obj")

    _exclude: frozenset[str] = frozenset(exclude_keys) if exclude_keys else frozenset()
    operations: list[Operation] = []
    _diff_values(old_obj, new_obj, [], [], array_keys or {}, _exclude, reversible, operations)

    return Delta({
        "format": "json-delta",
        "version": 1,
        "operations": operations,
    })


# ---------------------------------------------------------------------------
# Recursive comparison
# ---------------------------------------------------------------------------


def _diff_values(
    old: Any,
    new: Any,
    segments: list[_Segment],
    prop_path: list[str],
    array_keys: dict[str, str],
    exclude: frozenset[str],
    reversible: bool,
    operations: list[Operation],
) -> None:
    """Recursively compare two values and emit operations."""
    if json_equal(old, new):
        return

    old_is_dict = isinstance(old, dict) and not isinstance(old, bool)
    new_is_dict = isinstance(new, dict) and not isinstance(new, bool)

    old_is_list = isinstance(old, list)
    new_is_list = isinstance(new, list)

    if old_is_dict and new_is_dict:
        _diff_objects(old, new, segments, prop_path, array_keys, exclude, reversible, operations)
    elif old_is_list and new_is_list:
        _diff_arrays(old, new, segments, prop_path, array_keys, exclude, reversible, operations)
    else:
        # Type change or scalar difference → single replace
        _emit_replace(old, new, segments, reversible, operations)


def _diff_objects(
    old: dict[str, Any],
    new: dict[str, Any],
    segments: list[_Segment],
    prop_path: list[str],
    array_keys: dict[str, str],
    exclude: frozenset[str],
    reversible: bool,
    operations: list[Operation],
) -> None:
    """Compare two objects and emit add/remove/replace operations."""
    all_keys = sorted((set(old.keys()) | set(new.keys())) - exclude)

    for key in all_keys:
        seg = PropertySegment(name=key)
        child_segments = [*segments, seg]
        child_prop_path = [*prop_path, key]

        if key in old and key not in new:
            _emit_remove(old[key], child_segments, reversible, operations)
        elif key not in old and key in new:
            _emit_add(new[key], child_segments, operations)
        else:
            _diff_values(
                old[key], new[key], child_segments, child_prop_path,
                array_keys, exclude, reversible, operations,
            )


def _diff_arrays(
    old: list[Any],
    new: list[Any],
    segments: list[_Segment],
    prop_path: list[str],
    array_keys: dict[str, str],
    exclude: frozenset[str],
    reversible: bool,
    operations: list[Operation],
) -> None:
    """Compare two arrays using the appropriate identity model."""
    path_key = ".".join(prop_path)
    identity = array_keys.get(path_key, "$index")

    if identity == "$index":
        _diff_arrays_index(old, new, segments, prop_path, array_keys, exclude, reversible, operations)
    elif identity == "$value":
        _diff_arrays_value(old, new, segments, reversible, operations)
    else:
        _diff_arrays_keyed(old, new, segments, prop_path, array_keys, identity, exclude, reversible, operations)


# ---------------------------------------------------------------------------
# Index-based array comparison
# ---------------------------------------------------------------------------


def _diff_arrays_index(
    old: list[Any],
    new: list[Any],
    segments: list[_Segment],
    prop_path: list[str],
    array_keys: dict[str, str],
    exclude: frozenset[str],
    reversible: bool,
    operations: list[Operation],
) -> None:
    """Compare arrays by positional index."""
    min_len = min(len(old), len(new))

    # Compare shared positions
    for i in range(min_len):
        seg = IndexSegment(index=i)
        child_segments = [*segments, seg]
        _diff_values(old[i], new[i], child_segments, prop_path, array_keys, exclude, reversible, operations)

    # Elements removed from the end (remove from highest index first)
    for i in range(len(old) - 1, min_len - 1, -1):
        seg = IndexSegment(index=i)
        child_segments = [*segments, seg]
        _emit_remove(old[i], child_segments, reversible, operations)

    # Elements added at the end
    for i in range(min_len, len(new)):
        seg = IndexSegment(index=i)
        child_segments = [*segments, seg]
        _emit_add(new[i], child_segments, operations)


# ---------------------------------------------------------------------------
# Key-based array comparison
# ---------------------------------------------------------------------------


def _diff_arrays_keyed(
    old: list[Any],
    new: list[Any],
    segments: list[_Segment],
    prop_path: list[str],
    array_keys: dict[str, str],
    identity_key: str,
    exclude: frozenset[str],
    reversible: bool,
    operations: list[Operation],
) -> None:
    """Compare arrays by a key property on each element."""
    old_by_key: dict[Any, dict[str, Any]] = {}
    for elem in old:
        if not isinstance(elem, dict) or identity_key not in elem:
            raise DiffError(f"Array element missing identity key '{identity_key}': {elem!r}")
        key_val = elem[identity_key]
        hashable_key = _make_hashable(key_val)
        old_by_key[hashable_key] = elem

    new_by_key: dict[Any, dict[str, Any]] = {}
    new_key_order: list[Any] = []
    for elem in new:
        if not isinstance(elem, dict) or identity_key not in elem:
            raise DiffError(f"Array element missing identity key '{identity_key}': {elem!r}")
        key_val = elem[identity_key]
        hashable_key = _make_hashable(key_val)
        new_by_key[hashable_key] = elem
        new_key_order.append(hashable_key)

    # Removed elements (in old but not in new)
    for hashable_key, old_elem in old_by_key.items():
        if hashable_key not in new_by_key:
            key_val = old_elem[identity_key]
            filter_seg = KeyFilterSegment(property=identity_key, value=key_val)
            child_segments = [*segments, filter_seg]
            _emit_remove(old_elem, child_segments, reversible, operations)

    # Shared elements — recurse into properties for deep diffs
    for hashable_key in new_key_order:
        if hashable_key in old_by_key:
            old_elem = old_by_key[hashable_key]
            new_elem = new_by_key[hashable_key]
            if not json_equal(old_elem, new_elem):
                key_val = old_elem[identity_key]
                filter_seg = KeyFilterSegment(property=identity_key, value=key_val)
                # Recurse into properties of the matched element
                _diff_keyed_element(
                    old_elem, new_elem, [*segments, filter_seg], prop_path, array_keys, exclude, reversible, operations
                )

    # Added elements (in new but not in old)
    for hashable_key in new_key_order:
        if hashable_key not in old_by_key:
            new_elem = new_by_key[hashable_key]
            key_val = new_elem[identity_key]
            filter_seg = KeyFilterSegment(property=identity_key, value=key_val)
            child_segments = [*segments, filter_seg]
            _emit_add(new_elem, child_segments, operations)


def _diff_keyed_element(
    old_elem: dict[str, Any],
    new_elem: dict[str, Any],
    segments: list[_Segment],
    prop_path: list[str],
    array_keys: dict[str, str],
    exclude: frozenset[str],
    reversible: bool,
    operations: list[Operation],
) -> None:
    """Diff two keyed-array elements, emitting property-level operations."""
    all_keys = sorted((set(old_elem.keys()) | set(new_elem.keys())) - exclude)

    for key in all_keys:
        seg = PropertySegment(name=key)
        child_segments = [*segments, seg]
        child_prop_path = [*prop_path, key]

        if key in old_elem and key not in new_elem:
            _emit_remove(old_elem[key], child_segments, reversible, operations)
        elif key not in old_elem and key in new_elem:
            _emit_add(new_elem[key], child_segments, operations)
        else:
            _diff_values(
                old_elem[key], new_elem[key], child_segments, child_prop_path,
                array_keys, exclude, reversible, operations,
            )


# ---------------------------------------------------------------------------
# Value-based array comparison
# ---------------------------------------------------------------------------


def _diff_arrays_value(
    old: list[Any],
    new: list[Any],
    segments: list[_Segment],
    reversible: bool,
    operations: list[Operation],
) -> None:
    """Compare arrays by element value (for primitive arrays)."""
    # Find removed values (in old but not in new)
    for old_val in old:
        found = False
        for new_val in new:
            if json_equal(old_val, new_val):
                found = True
                break
        if not found:
            filter_seg = ValueFilterSegment(value=old_val)
            child_segments = [*segments, filter_seg]
            _emit_remove(old_val, child_segments, reversible, operations)

    # Find added values (in new but not in old)
    for new_val in new:
        found = False
        for old_val in old:
            if json_equal(old_val, new_val):
                found = True
                break
        if not found:
            filter_seg = ValueFilterSegment(value=new_val)
            child_segments = [*segments, filter_seg]
            _emit_add(new_val, child_segments, operations)


# ---------------------------------------------------------------------------
# Operation emission
# ---------------------------------------------------------------------------


def _emit_replace(
    old_val: Any,
    new_val: Any,
    segments: list[_Segment],
    reversible: bool,
    operations: list[Operation],
) -> None:
    """Emit a replace operation."""
    path = build_path(segments)
    if reversible:
        operations.append(Operation(op="replace", path=path, value=new_val, oldValue=old_val))
    else:
        operations.append(Operation(op="replace", path=path, value=new_val))


def _emit_add(
    value: Any,
    segments: list[_Segment],
    operations: list[Operation],
) -> None:
    """Emit an add operation."""
    path = build_path(segments)
    operations.append(Operation(op="add", path=path, value=value))


def _emit_remove(
    old_val: Any,
    segments: list[_Segment],
    reversible: bool,
    operations: list[Operation],
) -> None:
    """Emit a remove operation."""
    path = build_path(segments)
    if reversible:
        operations.append(Operation(op="remove", path=path, oldValue=old_val))
    else:
        operations.append(Operation(op="remove", path=path))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_hashable(value: Any) -> Any:
    """Convert a JSON scalar value to something hashable for dict keys.

    JSON scalars (str, int, float, bool, None) are already hashable.
    We wrap bool to avoid bool/int collision in dict keys.
    """
    if isinstance(value, bool):
        return ("__bool__", value)
    return value


def _validate_json_value(value: Any, name: str) -> None:
    """Validate that a value is a valid JSON type (recursive)."""
    if value is None:
        return
    if isinstance(value, bool):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise DiffError(f"Non-finite float in {name}: {value}")
        return
    if isinstance(value, str):
        return
    if isinstance(value, dict):
        for v in value.values():
            _validate_json_value(v, name)
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item, name)
        return
    raise DiffError(f"{name} contains non-JSON type: {type(value).__name__}")
