"""Data models for json-delta path segments, validation results, and delta types."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class RootSegment:
    """The root segment '$'."""


@dataclass(frozen=True, slots=True)
class PropertySegment:
    """A property access segment: .name or ['name']."""

    name: str


@dataclass(frozen=True, slots=True)
class IndexSegment:
    """An array index segment: [0]."""

    index: int


@dataclass(frozen=True, slots=True)
class KeyFilterSegment:
    """A key filter segment: [?(@.key==value)].

    The value field holds the filter literal as a typed Python value:
    str, int, float, bool, or None.
    """

    property: str
    value: Any


@dataclass(frozen=True, slots=True)
class ValueFilterSegment:
    """A value filter segment: [?(@==value)].

    The value field holds the filter literal as a typed Python value:
    str, int, float, bool, or None.
    """

    value: Any


type PathSegment = RootSegment | PropertySegment | IndexSegment | KeyFilterSegment | ValueFilterSegment


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Result of delta structural validation.

    Attributes:
        valid: Whether the delta document is structurally valid.
        errors: Tuple of error messages (empty if valid).
    """

    valid: bool
    errors: tuple[str, ...]


# ---------------------------------------------------------------------------
# Delta and Operation types
# ---------------------------------------------------------------------------

type OpType = Literal["add", "remove", "replace"]


class Operation(dict[str, Any]):
    """A single JSON Delta operation with typed property access and convenience methods.

    Subclasses ``dict`` — all dict operations (``json.dumps``, ``[]`` access,
    ``.items()``) work as expected. Extension properties (``x_*``) are accessed
    via normal dict syntax: ``op["x_editor"]``.

    Create operations via factory methods for full IDE support::

        op = Operation.add("$.name", "Alice")
        op = Operation.replace("$.name", "Bob", old_value="Alice")
        op = Operation.remove("$.name", old_value="Alice")

    For typed extension access, subclass ``Operation``::

        class AuditOp(Operation):
            @property
            def x_editor(self) -> str:
                return self["x_editor"]
    """

    @classmethod
    def add(cls, path: str, value: Any, **extensions: Any) -> Operation:
        """Create an ``add`` operation.

        Args:
            path: JSON Delta path (e.g., ``"$.name"``).
            value: The value to add.
            **extensions: Extension properties (``x_*`` keys).
        """
        return cls(op="add", path=path, value=value, **extensions)

    @classmethod
    def replace(cls, path: str, value: Any, *, old_value: Any = None, **extensions: Any) -> Operation:
        """Create a ``replace`` operation.

        Args:
            path: JSON Delta path (e.g., ``"$.name"``).
            value: The new value.
            old_value: The previous value (for reversible deltas).
            **extensions: Extension properties (``x_*`` keys).
        """
        op = cls(op="replace", path=path, value=value, **extensions)
        if old_value is not None:
            op["oldValue"] = old_value
        return op

    @classmethod
    def remove(cls, path: str, *, old_value: Any = None, **extensions: Any) -> Operation:
        """Create a ``remove`` operation.

        Args:
            path: JSON Delta path (e.g., ``"$.name"``).
            old_value: The removed value (for reversible deltas).
            **extensions: Extension properties (``x_*`` keys).
        """
        op = cls(op="remove", path=path, **extensions)
        if old_value is not None:
            op["oldValue"] = old_value
        return op

    @property
    def op(self) -> OpType:
        """The operation type: ``"add"``, ``"remove"``, or ``"replace"``."""
        return self["op"]  # type: ignore[no-any-return]

    @property
    def path(self) -> str:
        """The JSON Delta path targeting this operation."""
        return self["path"]  # type: ignore[no-any-return]

    @property
    def value(self) -> Any:
        """The new value (present on ``add`` and ``replace``, ``None`` otherwise)."""
        return self.get("value")

    @property
    def old_value(self) -> Any:
        """The previous value (present on ``replace`` and ``remove`` for reversible deltas)."""
        return self.get("oldValue")

    def describe(self) -> str:
        """Human-readable description of this operation's path.

        Delegates to :func:`json_delta.path.describe_path`.
        """
        from json_delta.path import describe_path

        return describe_path(self.path)

    def resolve(self, document: Any) -> str:
        """Resolve this operation's path to an RFC 6901 JSON Pointer.

        Delegates to :func:`json_delta.path.resolve_path`.

        Raises:
            PathError: If a filter matches zero or multiple elements.
        """
        from json_delta.path import resolve_path

        return resolve_path(self.path, document)

    def to_json_patch_op(self, document: Any) -> dict[str, Any]:
        """Convert this operation to a single RFC 6902 JSON Patch operation.

        Args:
            document: The source document (needed to resolve filter paths).

        Returns:
            A dict with ``op``, ``path``, and optionally ``value``.
        """
        from json_delta.json_patch import _operation_to_json_patch

        return _operation_to_json_patch(self, document)

    def __repr__(self) -> str:
        return f"Operation({dict.__repr__(self)})"


class Delta(dict[str, Any]):
    """A JSON Delta document with typed property access and convenience methods.

    Subclasses ``dict`` — ``json.dumps(delta)``, ``delta["operations"]``, and
    all standard dict operations work as expected. Extension properties are
    accessed via normal dict syntax: ``delta["x_agent"]``.

    Operations are automatically wrapped as :class:`Operation` instances on
    construction, giving typed access to ``op.path``, ``op.value``, etc.

    Create deltas conveniently::

        delta = Delta.create(
            Operation.add("$.name", "Alice"),
            Operation.replace("$.age", 31, old_value=30),
        )

    Iterate and inspect::

        for op in delta:
            print(f"{op.op}: {op.describe()}")

        if delta:  # truthy when non-empty
            print(f"{len(delta)} changes")
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Wrap raw dicts as Operation instances
        if "operations" in self:
            self["operations"] = [
                op if isinstance(op, Operation) else Operation(op)
                for op in self["operations"]
            ]

    @classmethod
    def create(cls, *operations: Operation | dict[str, Any], **extensions: Any) -> Delta:
        """Create a delta with the standard envelope.

        Args:
            *operations: Operation instances or raw dicts.
            **extensions: Extension properties (``x_*`` keys) on the envelope.

        Returns:
            A new :class:`Delta` with ``format="json-delta"`` and ``version=1``.

        Example::

            delta = Delta.create(
                Operation.add("$.name", "Alice"),
                Operation.replace("$.age", 31, old_value=30),
            )
        """
        d: dict[str, Any] = {"format": "json-delta", "version": 1, "operations": list(operations)}
        d.update(extensions)
        return cls(d)

    @property
    def format(self) -> str:
        """The format discriminator (always ``"json-delta"``)."""
        return self["format"]  # type: ignore[no-any-return]

    @property
    def version(self) -> int:
        """The format version number."""
        return self["version"]  # type: ignore[no-any-return]

    @property
    def operations(self) -> list[Operation]:
        """The ordered list of operations."""
        return self["operations"]  # type: ignore[no-any-return]

    @property
    def is_reversible(self) -> bool:
        """``True`` if all ``replace`` and ``remove`` operations include ``oldValue``."""
        return all("oldValue" in op for op in self.operations if op.op in ("replace", "remove"))

    @property
    def is_empty(self) -> bool:
        """``True`` if there are no operations."""
        return len(self.operations) == 0

    @property
    def affected_paths(self) -> set[str]:
        """The set of paths touched by all operations."""
        return {op.path for op in self.operations}

    # -- Iteration protocol --------------------------------------------------

    def __iter__(self) -> Iterator[Operation]:  # type: ignore[override]
        """Iterate over operations (not dict keys).

        This makes ``for op in delta:`` work naturally.
        """
        return iter(self.operations)

    def __len__(self) -> int:
        """Number of operations."""
        return len(self.operations)

    def __bool__(self) -> bool:
        """``True`` if the delta has operations."""
        return not self.is_empty

    def __add__(self, other: Delta) -> Delta:
        """Combine two deltas by concatenating their operations.

        Preserves envelope-level extension properties from both sides
        (``other`` wins on conflict). The result is a new ``Delta``.
        """
        if not isinstance(other, Delta):
            return NotImplemented
        merged: dict[str, Any] = {}
        for key, value in self.items():
            if key != "operations":
                merged[key] = value
        for key, value in other.items():
            if key != "operations":
                merged[key] = value
        merged["format"] = self.get("format", other.get("format", "json-delta"))
        merged["version"] = self.get("version", other.get("version", 1))
        merged["operations"] = [*self.operations, *other.operations]
        return Delta(merged)

    # -- Filtering -----------------------------------------------------------

    def filter(self, predicate: Callable[[Operation], bool]) -> Delta:
        """Return a new delta with only operations matching the predicate.

        Preserves all envelope-level properties.

        Example::

            adds_only = delta.filter(lambda op: op.op == "add")
            user_changes = delta.filter(lambda op: op.path.startswith("$.user"))
        """
        filtered_ops = [op for op in self.operations if predicate(op)]
        result: dict[str, Any] = {k: v for k, v in self.items() if k != "operations"}
        result["operations"] = filtered_ops
        return Delta(result)

    def summary(self, document: Any = None) -> str:
        """Human-readable summary of all operations.

        Args:
            document: Optional source document. When provided, each line also
                includes the resolved JSON Pointer path.

        Returns:
            A multi-line string, one line per operation.

        Example::

            >>> delta.summary()
            'replace: user > name = "Bob"'
        """
        if not self.operations:
            return "(no changes)"
        lines: list[str] = []
        for op in self.operations:
            desc = op.describe()
            line = f"{op.op}: {desc}"
            if op.op in ("add", "replace") and "value" in op:
                line += f" = {op['value']!r}"
            if document is not None:
                try:
                    pointer = op.resolve(document)
                    line += f"  [{pointer}]"
                except Exception:
                    pass
            lines.append(line)
        return "\n".join(lines)

    def apply(self, obj: Any) -> Any:
        """Apply this delta to a document.

        Delegates to :func:`json_delta.apply.apply_delta`.
        """
        from json_delta.apply import apply_delta

        return apply_delta(obj, self)

    def invert(self) -> Delta:
        """Compute the inverse of this delta.

        The inverse, when applied to the target document, recovers the source.

        Delegates to :func:`json_delta.invert.invert_delta`.
        """
        from json_delta.invert import invert_delta

        return invert_delta(self)

    def revert(self, obj: Any) -> Any:
        """Revert this delta by applying its inverse.

        Delegates to :func:`json_delta.invert.revert_delta`.
        """
        from json_delta.invert import revert_delta

        return revert_delta(obj, self)

    def to_json_patch(self, document: Any) -> list[dict[str, Any]]:
        """Convert this delta to an RFC 6902 JSON Patch.

        Requires the source document to resolve filter paths to positional indices.

        Delegates to :func:`json_delta.json_patch.to_json_patch`.
        """
        from json_delta.json_patch import to_json_patch

        return to_json_patch(self, document)

    @classmethod
    def from_json_patch(cls, patch: list[dict[str, Any]]) -> Delta:
        """Create a Delta from an RFC 6902 JSON Patch.

        Converts JSON Pointer paths to JSON Delta paths (index-based).
        Supports ``add``, ``remove``, ``replace`` operations.

        Raises:
            ValueError: For unsupported operations (``move``, ``copy``, ``test``).
        """
        from json_delta.json_patch import from_json_patch

        return from_json_patch(patch)

    def __repr__(self) -> str:
        ops = len(self.operations) if "operations" in self else 0
        return f"Delta({ops} operations)"
