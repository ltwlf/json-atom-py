"""JSON Patch (RFC 6902) interop — convert between JSON Atom and JSON Patch.

JSON Patch uses JSON Pointer (RFC 6901) paths with positional array indices.
JSON Atom uses JSONPath-based paths with identity-based array selection.

Converting from JSON Atom to JSON Patch requires a source document to
resolve filter paths to positional indices.
"""

from __future__ import annotations

import re
from typing import Any

from json_atom.errors import PathError
from json_atom.models import Delta, Operation
from json_atom.path import resolve_path

# JSON Patch ops that map directly to JSON Atom
_SUPPORTED_OPS = {"add", "remove", "replace"}

# JSON Patch ops with no JSON Atom equivalent (yet)
_UNSUPPORTED_OPS = {"move", "copy", "test"}

# Regex to detect whether a JSON Pointer segment is a pure array index
_INDEX_RE = re.compile(r"^(?:0|[1-9]\d*)$")


# ---------------------------------------------------------------------------
# JSON Atom → JSON Patch
# ---------------------------------------------------------------------------


def to_json_patch(delta: Delta, document: Any) -> list[dict[str, Any]]:
    """Convert a JSON Atom to an RFC 6902 JSON Patch array.

    Requires the source document to resolve filter-based paths to positional
    JSON Pointer paths.

    For ``add`` operations where the filter target does not yet exist in the
    document (new array element), the JSON Pointer ``-`` (append) sentinel
    is used for the array index.

    Args:
        delta: A JSON Atom document.
        document: The source document to resolve filter paths against.

    Returns:
        A list of RFC 6902 JSON Patch operation dicts.
    """
    patch: list[dict[str, Any]] = []
    for op in delta.operations:
        patch.append(_operation_to_json_patch(op, document))
    return patch


def _operation_to_json_patch(op: Operation, document: Any) -> dict[str, Any]:
    """Convert a single JSON Atom operation to a JSON Patch operation.

    This is the internal implementation used by both ``to_json_patch`` and
    ``Operation.to_json_patch_op``.
    """
    op_type = op.op
    path_str = op.path

    # Resolve the path to a JSON Pointer
    try:
        pointer = resolve_path(path_str, document)
    except PathError:
        if op_type == "add":
            # For add operations, the target element may not exist yet.
            # Resolve the parent path and append '-' for the array.
            pointer = _resolve_add_path(path_str, document)
        else:
            raise

    patch_op: dict[str, Any] = {"op": op_type, "path": pointer}
    if "value" in op:
        patch_op["value"] = op["value"]

    return patch_op


def _resolve_add_path(path_str: str, document: Any) -> str:
    """Resolve an add-operation path where the target doesn't exist yet.

    For key/value-filtered adds, the element is new so the filter won't match.
    We resolve the parent path and use '-' (append to array) for the final segment.
    """
    from json_atom.models import KeyFilterSegment, ValueFilterSegment
    from json_atom.path import parse_path

    segments = parse_path(path_str)

    if not segments:
        return ""

    # Check if the last segment is a filter (common case for array add)
    last = segments[-1]
    if isinstance(last, (KeyFilterSegment, ValueFilterSegment)):
        # Resolve parent segments, append '-'
        if len(segments) == 1:
            return "/-"
        from json_atom.path import build_path

        parent_path = build_path(segments[:-1])
        parent_pointer = resolve_path(parent_path, document)
        return f"{parent_pointer}/-"

    raise PathError(f"Cannot resolve path for add operation: {path_str}")


# ---------------------------------------------------------------------------
# JSON Patch → JSON Atom
# ---------------------------------------------------------------------------


def from_json_patch(patch: list[dict[str, Any]]) -> Delta:
    """Convert an RFC 6902 JSON Patch array to a JSON Atom.

    Converts JSON Pointer paths (``/foo/0/bar``) to JSON Atom paths
    (``$.foo[0].bar``). Only index-based array addressing is possible
    since JSON Pointers don't carry identity information.

    Supports ``add``, ``remove``, ``replace`` operations.

    Args:
        patch: A list of RFC 6902 JSON Patch operation dicts.

    Returns:
        A :class:`Delta` document.

    Raises:
        ValueError: For unsupported operations (``move``, ``copy``, ``test``).
            These may be supported in a future JSON Atom spec revision.
    """
    operations: list[Operation] = []

    for i, patch_op in enumerate(patch):
        op_type = patch_op.get("op", "")
        if op_type in _UNSUPPORTED_OPS:
            raise ValueError(
                f"patch[{i}]: '{op_type}' operation is not supported by JSON Atom. "
                f"Only add, remove, replace are supported. "
                f"This may change in a future spec revision."
            )
        if op_type not in _SUPPORTED_OPS:
            raise ValueError(f"patch[{i}]: unknown operation '{op_type}'")

        pointer = patch_op.get("path", "")
        delta_path = _pointer_to_delta_path(pointer)

        op_dict: dict[str, Any] = {"op": op_type, "path": delta_path}
        if "value" in patch_op:
            op_dict["value"] = patch_op["value"]

        operations.append(Operation(op_dict))

    return Delta({
        "format": "json-atom",
        "version": 1,
        "operations": operations,
    })


def _pointer_to_delta_path(pointer: str) -> str:
    """Convert an RFC 6901 JSON Pointer to a JSON Atom path.

    ``/foo/0/bar``  → ``$.foo[0].bar``
    ``/a~1b/~0c``   → ``$['a/b']['~c']``
    ``""``           → ``$``
    ``/``            → ``$['']``
    """
    if not pointer:
        return "$"

    if not pointer.startswith("/"):
        raise ValueError(f"JSON Pointer must start with '/': {pointer!r}")

    # Split and unescape per RFC 6901
    raw_segments = pointer[1:].split("/")
    parts: list[str] = ["$"]

    # Regex for safe dot-notation property names
    safe_name_re = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

    for raw in raw_segments:
        # Unescape: ~1 → /, ~0 → ~  (order matters per RFC 6901)
        unescaped = raw.replace("~1", "/").replace("~0", "~")

        if _INDEX_RE.match(raw):
            parts.append(f"[{int(raw)}]")
        elif raw == "-":
            # JSON Pointer '-' means "past the end" — preserve as index
            # This is typically used for append in JSON Patch add operations
            parts.append("[-]")
        elif safe_name_re.match(unescaped):
            parts.append(f".{unescaped}")
        else:
            escaped = unescaped.replace("'", "''")
            parts.append(f"['{escaped}']")

    return "".join(parts)
