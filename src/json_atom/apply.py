"""Apply a JSON Atom document to a source object.

Implements Section 8 (Applying a Delta) of the JSON Atom v0 specification.
"""

from __future__ import annotations

import copy
from typing import Any

from json_atom._utils import json_equal
from json_atom.errors import ApplyError
from json_atom.models import (
    Delta,
    IndexSegment,
    KeyFilterSegment,
    Operation,
    PropertySegment,
    RootSegment,
    ValueFilterSegment,
)
from json_atom.path import parse_path
from json_atom.validate import validate_delta


def apply_delta(obj: Any, delta: Delta) -> Any:
    """Apply a JSON Atom to a source object.

    Mutates the object in place where possible. Always use the return value,
    as root operations may replace the entire object.

    Raises ApplyError on invalid delta structure or failed operations.
    """
    # Validate delta structure
    result = validate_delta(delta)
    if not result.valid:
        raise ApplyError(f"Invalid delta: {'; '.join(result.errors)}")

    # Apply operations sequentially (spec Section 8)
    for i, op in enumerate(delta["operations"]):
        try:
            obj = _apply_operation(obj, op)
        except ApplyError:
            raise
        except Exception as e:
            raise ApplyError(f"operations[{i}]: {e}") from e

    return obj


def _apply_operation(obj: Any, op: Operation) -> Any:
    """Apply a single operation and return the (possibly new) root object."""
    op_type = op["op"]

    # Move/copy: two-path operations handled separately
    if op_type == "move":
        return _apply_move(obj, op)
    if op_type == "copy":
        return _apply_copy(obj, op)

    path_str = op["path"]
    segments = parse_path(path_str)

    # Root operation: path is "$" (no segments after root)
    if len(segments) == 0:
        return _apply_root_operation(obj, op_type, op)

    # Resolve the parent and final segment
    parent, final_seg = _resolve_parent(obj, segments, path_str)

    if isinstance(final_seg, PropertySegment):
        _apply_property_op(parent, final_seg.name, op_type, op, path_str)
    elif isinstance(final_seg, IndexSegment):
        _apply_index_op(parent, final_seg.index, op_type, op, path_str)
    elif isinstance(final_seg, KeyFilterSegment):
        _apply_key_filter_op(parent, final_seg, op_type, op, path_str, is_element_level=True)
    elif isinstance(final_seg, ValueFilterSegment):
        _apply_value_filter_op(parent, final_seg, op_type, op, path_str, is_element_level=True)
    else:
        raise ApplyError(f"Unexpected segment type at end of path: {type(final_seg).__name__}")

    return obj


# ---------------------------------------------------------------------------
# Move / Copy operations (spec Section 6.6, 6.7)
# ---------------------------------------------------------------------------


def _read_value_at_path(obj: Any, path_str: str) -> Any:
    """Resolve a JSON Atom path to its value in the document."""
    segments = parse_path(path_str)
    if not segments:
        return obj  # root
    current = obj
    for seg in segments:
        if isinstance(seg, RootSegment):
            continue
        elif isinstance(seg, PropertySegment):
            if not isinstance(current, dict) or seg.name not in current:
                raise ApplyError(f"Property '{seg.name}' not found: {path_str}")
            current = current[seg.name]
        elif isinstance(seg, IndexSegment):
            if not isinstance(current, list) or seg.index >= len(current):
                raise ApplyError(f"Index {seg.index} out of bounds: {path_str}")
            current = current[seg.index]
        elif isinstance(seg, KeyFilterSegment):
            idx = _find_key_filter_match(current, seg, path_str)
            current = current[idx]
        elif isinstance(seg, ValueFilterSegment):
            idx = _find_value_filter_match(current, seg, path_str)
            current = current[idx]
    return current


def _apply_move(obj: Any, op: Operation) -> Any:
    """Apply a move operation: read from source, remove, add at target."""
    from_path = op["from"]
    to_path = op["path"]

    # Read value at source
    value = _read_value_at_path(obj, from_path)

    # Remove from source
    remove_op = Operation(op="remove", path=from_path)
    obj = _apply_operation(obj, remove_op)

    # Add to target — no deepcopy needed, value was removed from source
    add_op = Operation(op="add", path=to_path, value=value)
    obj = _apply_operation(obj, add_op)

    return obj


def _apply_copy(obj: Any, op: Operation) -> Any:
    """Apply a copy operation: read from source, deep-clone to target."""
    from_path = op["from"]
    to_path = op["path"]

    # Read and deep-clone value at source
    value = copy.deepcopy(_read_value_at_path(obj, from_path))

    # Add to target
    add_op = Operation(op="add", path=to_path, value=value)
    obj = _apply_operation(obj, add_op)

    return obj


# ---------------------------------------------------------------------------
# Root operations (spec Section 6.5)
# ---------------------------------------------------------------------------


def _apply_root_operation(obj: Any, op_type: str, op: Operation) -> Any:
    """Handle operations on the root path '$'."""
    if op_type == "add":
        if obj is not None:
            raise ApplyError("Root 'add' requires source to be null")
        return copy.deepcopy(op["value"])

    if op_type == "remove":
        if obj is None:
            raise ApplyError("Root 'remove' requires source to be non-null")
        return None

    if op_type == "replace":
        if obj is None:
            raise ApplyError("Root 'replace' requires source to be non-null")
        return copy.deepcopy(op["value"])

    raise ApplyError(f"Unknown operation type: {op_type!r}")


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def _resolve_parent(
    obj: Any,
    segments: list[Any],
    path_str: str,
) -> tuple[Any, Any]:
    """Navigate the object tree to find the parent container and the final segment.

    Returns (parent, final_segment).
    For filter segments, if there are trailing segments after the filter,
    the filter is resolved to the matched element and navigation continues.
    """
    current = obj

    for seg in segments[:-1]:
        if isinstance(seg, PropertySegment):
            if not isinstance(current, dict):
                raise ApplyError(f"Cannot access property '{seg.name}' on {_type_name(current)}: {path_str}")
            if seg.name not in current:
                raise ApplyError(f"Property '{seg.name}' does not exist: {path_str}")
            current = current[seg.name]

        elif isinstance(seg, IndexSegment):
            if not isinstance(current, list):
                raise ApplyError(f"Cannot access index [{seg.index}] on {_type_name(current)}: {path_str}")
            if seg.index >= len(current):
                raise ApplyError(f"Index [{seg.index}] out of range (length {len(current)}): {path_str}")
            current = current[seg.index]

        elif isinstance(seg, KeyFilterSegment):
            if not isinstance(current, list):
                raise ApplyError(f"Cannot apply key filter on {_type_name(current)}: {path_str}")
            matched_idx = _find_key_filter_match(current, seg, path_str)
            current = current[matched_idx]

        elif isinstance(seg, ValueFilterSegment):
            if not isinstance(current, list):
                raise ApplyError(f"Cannot apply value filter on {_type_name(current)}: {path_str}")
            matched_idx = _find_value_filter_match(current, seg, path_str)
            current = current[matched_idx]

        else:
            raise ApplyError(f"Unexpected segment type during navigation: {type(seg).__name__}")

    return current, segments[-1]


# ---------------------------------------------------------------------------
# Filter matching
# ---------------------------------------------------------------------------


_SENTINEL = object()


def _resolve_property(obj: Any, key: str, *, literal: bool = False) -> Any:
    """Resolve a property on a dict.

    When ``literal`` is False and the key contains dots, traverses nested segments.
    When ``literal`` is True, treats the key as a literal property name.
    Returns ``_SENTINEL`` if the property is missing (distinguishes from ``None``).
    """
    if literal or "." not in key:
        if isinstance(obj, dict) and key in obj:
            return obj[key]
        return _SENTINEL
    current = obj
    for seg in key.split("."):
        if not isinstance(current, dict) or seg not in current:
            return _SENTINEL
        current = current[seg]
    return current


def _find_key_filter_match(arr: list[Any], seg: KeyFilterSegment, path_str: str) -> int:
    """Find exactly one element matching a key filter. Returns its index.

    Supports nested property paths (e.g. 'positionNumber.value').
    When ``seg.literal_key`` is True, treats the property as a literal name.
    Raises ApplyError if zero or multiple elements match.
    """
    matches: list[int] = []
    for idx, elem in enumerate(arr):
        resolved = _resolve_property(elem, seg.property, literal=seg.literal_key)
        if resolved is not _SENTINEL and json_equal(resolved, seg.value):
            matches.append(idx)

    if len(matches) == 0:
        raise ApplyError(f"Key filter matched zero elements: {path_str}")
    if len(matches) > 1:
        raise ApplyError(f"Key filter matched {len(matches)} elements (must be exactly one): {path_str}")
    return matches[0]


def _find_value_filter_match(arr: list[Any], seg: ValueFilterSegment, path_str: str) -> int:
    """Find exactly one element matching a value filter. Returns its index.

    Raises ApplyError if zero or multiple elements match.
    """
    matches: list[int] = []
    for idx, elem in enumerate(arr):
        if json_equal(elem, seg.value):
            matches.append(idx)

    if len(matches) == 0:
        raise ApplyError(f"Value filter matched zero elements: {path_str}")
    if len(matches) > 1:
        raise ApplyError(f"Value filter matched {len(matches)} elements (must be exactly one): {path_str}")
    return matches[0]


# ---------------------------------------------------------------------------
# Property operations (spec Section 6.1-6.3)
# ---------------------------------------------------------------------------


def _apply_property_op(
    parent: Any, name: str, op_type: str, op: Operation, path_str: str
) -> None:
    """Apply an operation on an object property."""
    if not isinstance(parent, dict):
        raise ApplyError(f"Cannot apply property operation on {_type_name(parent)}: {path_str}")

    if op_type == "add":
        if name in parent:
            raise ApplyError(f"Property '{name}' already exists (use 'replace'): {path_str}")
        parent[name] = copy.deepcopy(op["value"])

    elif op_type == "remove":
        if name not in parent:
            raise ApplyError(f"Property '{name}' does not exist (cannot remove): {path_str}")
        del parent[name]

    elif op_type == "replace":
        if name not in parent:
            raise ApplyError(f"Property '{name}' does not exist (cannot replace): {path_str}")
        parent[name] = copy.deepcopy(op["value"])

    else:
        raise ApplyError(f"Unknown operation type: {op_type!r}")


# ---------------------------------------------------------------------------
# Index operations (spec Section 7.1)
# ---------------------------------------------------------------------------


def _apply_index_op(
    parent: Any, index: int, op_type: str, op: Operation, path_str: str
) -> None:
    """Apply an operation on an array index."""
    if not isinstance(parent, list):
        raise ApplyError(f"Cannot apply index operation on {_type_name(parent)}: {path_str}")

    if op_type == "add":
        if index > len(parent):
            raise ApplyError(f"Index [{index}] out of range for insert (length {len(parent)}): {path_str}")
        parent.insert(index, copy.deepcopy(op["value"]))

    elif op_type == "remove":
        if index >= len(parent):
            raise ApplyError(f"Index [{index}] out of range (length {len(parent)}): {path_str}")
        parent.pop(index)

    elif op_type == "replace":
        if index >= len(parent):
            raise ApplyError(f"Index [{index}] out of range (length {len(parent)}): {path_str}")
        parent[index] = copy.deepcopy(op["value"])

    else:
        raise ApplyError(f"Unknown operation type: {op_type!r}")


# ---------------------------------------------------------------------------
# Key filter operations (spec Section 7.2)
# ---------------------------------------------------------------------------


def _apply_key_filter_op(
    parent: Any,
    seg: KeyFilterSegment,
    op_type: str,
    op: dict[str, Any],
    path_str: str,
    *,
    is_element_level: bool,
) -> None:
    """Apply an operation using a key filter on an array."""
    if not isinstance(parent, list):
        raise ApplyError(f"Cannot apply key filter operation on {_type_name(parent)}: {path_str}")

    if op_type == "add":
        # Filter must NOT match any existing element
        for elem in parent:
            resolved = _resolve_property(elem, seg.property, literal=seg.literal_key)
            if resolved is not _SENTINEL and json_equal(resolved, seg.value):
                raise ApplyError(f"Key filter already matches an element (use 'replace'): {path_str}")

        value = op["value"]
        # Keyed-array value consistency (spec Section 6.4)
        if is_element_level:
            _validate_keyed_array_consistency(value, seg, path_str)

        parent.append(copy.deepcopy(value))

    elif op_type == "remove":
        matched_idx = _find_key_filter_match(parent, seg, path_str)
        parent.pop(matched_idx)

    elif op_type == "replace":
        matched_idx = _find_key_filter_match(parent, seg, path_str)
        value = op["value"]
        # Keyed-array value consistency (spec Section 6.4)
        if is_element_level:
            _validate_keyed_array_consistency(value, seg, path_str)
        parent[matched_idx] = copy.deepcopy(value)

    else:
        raise ApplyError(f"Unknown operation type: {op_type!r}")


# ---------------------------------------------------------------------------
# Value filter operations (spec Section 7.3)
# ---------------------------------------------------------------------------


def _apply_value_filter_op(
    parent: Any,
    seg: ValueFilterSegment,
    op_type: str,
    op: dict[str, Any],
    path_str: str,
    *,
    is_element_level: bool,
) -> None:
    """Apply an operation using a value filter on an array."""
    if not isinstance(parent, list):
        raise ApplyError(f"Cannot apply value filter operation on {_type_name(parent)}: {path_str}")

    if op_type == "add":
        # Filter must NOT match any existing element
        for elem in parent:
            if json_equal(elem, seg.value):
                raise ApplyError(f"Value filter already matches an element: {path_str}")
        parent.append(copy.deepcopy(op["value"]))

    elif op_type == "remove":
        matched_idx = _find_value_filter_match(parent, seg, path_str)
        parent.pop(matched_idx)

    elif op_type == "replace":
        matched_idx = _find_value_filter_match(parent, seg, path_str)
        parent[matched_idx] = copy.deepcopy(op["value"])

    else:
        raise ApplyError(f"Unknown operation type: {op_type!r}")


# ---------------------------------------------------------------------------
# Keyed-array value consistency (spec Section 6.4)
# ---------------------------------------------------------------------------


def _validate_keyed_array_consistency(
    value: Any, seg: KeyFilterSegment, path_str: str
) -> None:
    """Validate that the value contains the identity property matching the filter.

    Applies to 'add' and element-level 'replace' on key-filtered paths
    (no trailing segments after filter).
    """
    if not isinstance(value, dict):
        raise ApplyError(
            f"Keyed-array value must be an object, got {_type_name(value)}: {path_str}"
        )
    resolved = _resolve_property(value, seg.property, literal=seg.literal_key)
    if resolved is _SENTINEL:
        raise ApplyError(
            f"Keyed-array value missing identity property '{seg.property}': {path_str}"
        )
    if not json_equal(resolved, seg.value):
        raise ApplyError(
            f"Keyed-array value identity mismatch: "
            f"filter expects {seg.value!r} but value has {resolved!r}: {path_str}"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _type_name(value: Any) -> str:
    """Return a readable type name for error messages."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return type(value).__name__
