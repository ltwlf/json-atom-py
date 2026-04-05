"""Data models for json-atom path segments, validation results, and delta types."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from enum import StrEnum
from functools import cached_property
from typing import TYPE_CHECKING, Any, Literal

# Matches simple identifiers safe for dot-notation display paths.
# Consistent with path.py _PROPERTY_NAME_RE (spec Section 5.5).
_IDENT_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

if TYPE_CHECKING:
    from json_atom._identity import ArrayIdentityKeys


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
    """A key filter segment: [?(@.key==value)] or [?(@['key']==value)].

    The value field holds the filter literal as a typed Python value:
    str, int, float, bool, or None.

    When ``literal_key`` is True, the property was parsed from bracket
    notation (``@['key']``) and represents a literal property name.
    ``build_path`` emits bracket notation only when needed to preserve
    semantics (i.e. when dot notation would change meaning); simple
    identifiers are canonicalized to dot notation regardless.
    """

    property: str
    value: Any
    literal_key: bool = False


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
# Enriched comparison tree
# ---------------------------------------------------------------------------


class ChangeType(StrEnum):
    """Classification of a comparison tree node."""

    UNCHANGED = "unchanged"
    ADDED = "added"
    REMOVED = "removed"
    REPLACED = "replaced"
    CONTAINER = "container"


@dataclass(frozen=True, slots=True)
class ComparisonNode:
    """A node in the enriched comparison tree.

    For ``CONTAINER`` nodes, ``value`` holds ``dict[str, ComparisonNode]``
    (objects) or ``list[ComparisonNode]`` (arrays).  For leaf nodes,
    ``value`` holds the actual JSON value.

    Example::

        node = compare(old_doc, new_doc)
        if node.type == ChangeType.CONTAINER:
            for key, child in node.value.items():
                print(f"{key}: {child.type}")
    """

    type: ChangeType
    value: Any = None
    old_value: Any | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize this node to a plain dict for JSON serialization.

        For ``CONTAINER`` nodes, ``value`` is recursively serialized.
        For leaf nodes, ``value`` and ``old_value`` are included based
        on the change type (not truthiness — ``None``/``null`` is a
        valid JSON value).

        Returns:
            A JSON-serializable dict with ``type`` as a string.
        """
        result: dict[str, Any] = {"type": self.type.value}
        if self.type == ChangeType.CONTAINER:
            if isinstance(self.value, dict):
                result["value"] = {k: v.to_dict() for k, v in self.value.items()}
            elif isinstance(self.value, list):
                result["value"] = [v.to_dict() for v in self.value]
        else:
            if self.type in (ChangeType.UNCHANGED, ChangeType.ADDED, ChangeType.REPLACED):
                result["value"] = self.value
            if self.type in (ChangeType.REMOVED, ChangeType.REPLACED):
                result["old_value"] = self.old_value
        return result

    def to_flat_list(
        self,
        *,
        prefix: str = "$",
        include_unchanged: bool = False,
    ) -> list[dict[str, Any]]:
        """Flatten this tree into a list of leaf changes with paths.

        Each entry contains ``path``, ``type``, and optionally ``value``
        and ``old_value`` based on the change type.

        .. warning::

            For keyed-array comparison trees, paths use structural display
            positions (e.g., ``$.items[0]``), **not** stable identity-based
            locators.  Do not use these paths to address elements in a
            document — use :func:`diff_delta` for addressable filter paths.

        Args:
            prefix: The path prefix for this node (default ``"$"``).
            include_unchanged: If ``True``, include ``UNCHANGED`` leaves.
                Defaults to ``False`` (only changed leaves).

        Returns:
            A list of dicts, one per leaf node.
        """
        results: list[dict[str, Any]] = []
        self._flatten(prefix, include_unchanged, results)
        return results

    def _flatten(
        self,
        path: str,
        include_unchanged: bool,
        results: list[dict[str, Any]],
    ) -> None:
        """Recursively flatten the comparison tree into *results*."""
        if self.type == ChangeType.CONTAINER:
            if isinstance(self.value, dict):
                for key, child in self.value.items():
                    if _IDENT_RE.match(key):
                        child_path = f"{path}.{key}"
                    else:
                        escaped = key.replace("'", "''")
                        child_path = f"{path}['{escaped}']"
                    child._flatten(child_path, include_unchanged, results)
            elif isinstance(self.value, list):
                for i, child in enumerate(self.value):
                    child_path = f"{path}[{i}]"
                    child._flatten(child_path, include_unchanged, results)
            return

        if self.type == ChangeType.UNCHANGED and not include_unchanged:
            return

        entry: dict[str, Any] = {"path": path, "type": self.type.value}
        if self.type in (ChangeType.UNCHANGED, ChangeType.ADDED, ChangeType.REPLACED):
            entry["value"] = self.value
        if self.type in (ChangeType.REMOVED, ChangeType.REPLACED):
            entry["old_value"] = self.old_value
        results.append(entry)


# ---------------------------------------------------------------------------
# Delta and Operation types
# ---------------------------------------------------------------------------

# Fields defined by the spec — everything else is an extension (Section 11)
_OP_SPEC_KEYS = frozenset({"op", "path", "from", "value", "oldValue"})
_DELTA_SPEC_KEYS = frozenset({"format", "version", "operations"})

type OpType = Literal["add", "remove", "replace", "move", "copy"]


class Operation(dict[str, Any]):
    """A single JSON Atom operation with typed property access and convenience methods.

    Subclasses ``dict`` — all dict operations (``json.dumps``, ``[]`` access,
    ``.items()``) work as expected. Extension properties are accessible as
    attributes (``op.x_editor``) or via dict syntax (``op["x_editor"]``).

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
            path: JSON Atom path (e.g., ``"$.name"``).
            value: The value to add.
            **extensions: Extension properties (``x_*`` keys).
        """
        return cls(op="add", path=path, value=value, **extensions)

    @classmethod
    def replace(cls, path: str, value: Any, *, old_value: Any = None, **extensions: Any) -> Operation:
        """Create a ``replace`` operation.

        Args:
            path: JSON Atom path (e.g., ``"$.name"``).
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
            path: JSON Atom path (e.g., ``"$.name"``).
            old_value: The removed value (for reversible deltas).
            **extensions: Extension properties (``x_*`` keys).
        """
        op = cls(op="remove", path=path, **extensions)
        if old_value is not None:
            op["oldValue"] = old_value
        return op

    _MISSING: Any = object()

    @classmethod
    def move(cls, from_path: str, path: str, **extensions: Any) -> Operation:
        """Create a ``move`` operation.

        Args:
            from_path: Source JSON Atom path.
            path: Target JSON Atom path.
            **extensions: Extension properties (``x_*`` keys).
        """
        return cls(op="move", path=path, **{"from": from_path, **extensions})

    @classmethod
    def copy_op(cls, from_path: str, path: str, *, value: Any = _MISSING, **extensions: Any) -> Operation:
        """Create a ``copy`` operation.

        Named ``copy_op`` to avoid conflict with ``dict.copy()``.

        Args:
            from_path: Source JSON Atom path.
            path: Target JSON Atom path.
            value: The copied value (optional, for reversibility).
            **extensions: Extension properties (``x_*`` keys).
        """
        op = cls(op="copy", path=path, **{"from": from_path, **extensions})
        if value is not cls._MISSING:
            op["value"] = value
        return op

    @property
    def from_path(self) -> str | None:
        """The source path for ``move`` and ``copy`` operations."""
        return self.get("from")

    @property
    def op(self) -> OpType:
        """The operation type."""
        return self["op"]  # type: ignore[no-any-return]

    @property
    def path(self) -> str:
        """The JSON Atom path targeting this operation."""
        return self["path"]  # type: ignore[no-any-return]

    @property
    def value(self) -> Any:
        """The new value (present on ``add`` and ``replace``, ``None`` otherwise)."""
        return self.get("value")

    @property
    def old_value(self) -> Any:
        """The previous value (present on ``replace`` and ``remove`` for reversible deltas)."""
        return self.get("oldValue")

    def _invalidate_path_cache(self) -> None:
        """Drop cached ``segments``, ``filter_values``, and ``leaf_property`` so they are re-parsed."""
        self.__dict__.pop("segments", None)
        self.__dict__.pop("filter_values", None)
        self.__dict__.pop("leaf_property", None)

    @cached_property
    def segments(
        self,
    ) -> list[RootSegment | PropertySegment | IndexSegment | KeyFilterSegment | ValueFilterSegment]:
        """The parsed path segments for this operation's path (cached).

        Delegates to :func:`json_atom.path.parse_path`.  The result is
        computed once and cached for the lifetime of the Operation instance.
        """
        from json_atom.path import parse_path

        return parse_path(self.path)

    @cached_property
    def filter_values(self) -> dict[str, Any]:
        """Extract filter identity values from this operation's path (cached).

        Returns a dict mapping the parent array property name to its filter
        match value.  This eliminates manual path parsing when you need to know
        *which* keyed element an operation targets.

        Example::

            op = Operation(op="replace",
                           path="$.articles[?(@.id=='art-3')].clauses[?(@.id=='cl-1')].text",
                           value="new")
            op.filter_values  # {"articles": "art-3", "clauses": "cl-1"}
        """
        segs = self.segments
        result: dict[str, Any] = {}
        for i, seg in enumerate(segs):
            if isinstance(seg, (KeyFilterSegment, ValueFilterSegment)) and i > 0:
                prev = segs[i - 1]
                if isinstance(prev, PropertySegment):
                    result[prev.name] = seg.value
        return result

    def describe(self) -> str:
        """Human-readable description of this operation's path.

        Delegates to :func:`json_atom.path.describe_path`.
        """
        from json_atom.path import describe_path

        return describe_path(self.path)

    def resolve(self, document: Any) -> str:
        """Resolve this operation's path to an RFC 6901 JSON Pointer.

        Delegates to :func:`json_atom.path.resolve_path`.

        Raises:
            PathError: If a filter matches zero or multiple elements.
        """
        from json_atom.path import resolve_path

        return resolve_path(self.path, document)

    def to_json_patch_op(self, document: Any) -> dict[str, Any]:
        """Convert this operation to a single RFC 6902 JSON Patch operation.

        Args:
            document: The source document (needed to resolve filter paths).

        Returns:
            A dict with ``op``, ``path``, and optionally ``value``.
        """
        from json_atom.json_patch import _operation_to_json_patch

        return _operation_to_json_patch(self, document)

    @property
    def extensions(self) -> dict[str, Any]:
        """All non-spec properties on this operation (per JSON Atom v0 Section 11).

        The ``x_`` prefix is recommended for future-safety but not enforced.
        """
        return {k: v for k, v in self.items() if k not in _OP_SPEC_KEYS}

    def spec_dict(self) -> dict[str, Any]:
        """Spec-only fields (``op``, ``path``, ``value``, ``oldValue``).

        Complement of :attr:`extensions` — together they partition all keys.
        Useful for stripping extension metadata before serialization.
        """
        return {k: v for k, v in self.items() if k in _OP_SPEC_KEYS}

    @cached_property
    def leaf_property(self) -> str | None:
        """Name of the terminal property, or ``None`` for whole-element/root ops.

        Example::

            Operation(op="replace", path="$.items[?(@.id=='1')].title", value="x").leaf_property
            # "title"
            Operation(op="remove", path="$.items[?(@.id=='1')]", value=None).leaf_property
            # None
            Operation(op="replace", path="$", value={}).leaf_property
            # None
        """
        segs = self.segments
        if segs and isinstance(segs[-1], PropertySegment):
            return segs[-1].name
        return None

    def __getattr__(self, name: str) -> Any:
        """Fall back to dict lookup for extension attribute access."""
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'") from None

    def __dir__(self) -> list[str]:
        """Include dict keys for tab-completion in IPython/Jupyter."""
        return sorted(set(super().__dir__()) | set(self.keys()))

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: Any) -> Any:
        """Pydantic v2 native support — zero runtime dependency on pydantic.

        Allows ``Operation`` to be used as a Pydantic field type without
        ``arbitrary_types_allowed=True``.  Accepts dicts or existing instances;
        serializes as a plain dict.
        """
        from pydantic_core import core_schema as cs

        def validate(value: Any) -> Operation:
            if isinstance(value, cls):
                return value
            if isinstance(value, dict):
                return cls(value)
            raise ValueError(f"Expected dict or {cls.__name__}, got {type(value).__name__}")

        return cs.json_or_python_schema(
            json_schema=cs.chain_schema([
                cs.dict_schema(),
                cs.no_info_plain_validator_function(validate),
            ]),
            python_schema=cs.union_schema([
                cs.is_instance_schema(cls),
                cs.chain_schema([
                    cs.dict_schema(),
                    cs.no_info_plain_validator_function(validate),
                ]),
            ]),
            serialization=cs.plain_serializer_function_ser_schema(
                dict, when_used='always'
            ),
        )

    def __repr__(self) -> str:
        return f"Operation({dict.__repr__(self)})"

    # -- Dict mutator overrides: invalidate path cache when "path" changes --

    def __setitem__(self, key: str, value: Any) -> None:
        super().__setitem__(key, value)
        if key == "path":
            self._invalidate_path_cache()

    def __delitem__(self, key: str) -> None:
        super().__delitem__(key)
        if key == "path":
            self._invalidate_path_cache()

    def update(self, __m: Any = (), **kwargs: Any) -> None:
        had_path = self.get("path")
        super().update(__m, **kwargs)
        if self.get("path") != had_path:
            self._invalidate_path_cache()

    def pop(self, key: str, *args: Any) -> Any:
        result = super().pop(key, *args)
        if key == "path":
            self._invalidate_path_cache()
        return result

    def popitem(self) -> tuple[str, Any]:
        key, value = super().popitem()
        if key == "path":
            self._invalidate_path_cache()
        return key, value

    def clear(self) -> None:
        super().clear()
        self._invalidate_path_cache()


class Delta(dict[str, Any]):
    """A JSON Atom document with typed property access and convenience methods.

    Subclasses ``dict`` — ``json.dumps(delta)``, ``delta["operations"]``, and
    all standard dict operations work as expected. Extension properties are
    accessible as attributes (``delta.x_agent``) or via dict syntax.

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
            A new :class:`Delta` with ``format="json-atom"`` and ``version=1``.

        Example::

            delta = Delta.create(
                Operation.add("$.name", "Alice"),
                Operation.replace("$.age", 31, old_value=30),
            )
        """
        d: dict[str, Any] = {"format": "json-atom", "version": 1, "operations": list(operations)}
        d.update(extensions)
        return cls(d)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Delta:
        """Create a Delta from a raw dict, checking that required envelope keys exist.

        This is a lightweight gate — it verifies that ``format``, ``version``,
        and ``operations`` are present but does **not** validate types or
        operation shapes.  For full structural validation, call
        :func:`json_atom.validate.validate_delta` on the result.

        Raises:
            ValueError: If the dict is missing required envelope keys
                (``format``, ``version``, ``operations``).

        Example::

            raw = json.loads(payload)
            delta = Delta.from_dict(raw)          # checks keys
            result = validate_delta(delta)         # full validation
        """
        missing = {"format", "version", "operations"} - d.keys()
        if missing:
            raise ValueError(f"Not a valid delta envelope — missing keys: {', '.join(sorted(missing))}")
        return cls(d)

    @property
    def format(self) -> str:
        """The format discriminator (always ``"json-atom"``)."""
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
        """``True`` if all ``replace``/``remove`` include ``oldValue`` and all ``copy`` include ``value``."""
        return all(
            "oldValue" in op for op in self.operations if op.op in ("replace", "remove")
        ) and all("value" in op for op in self.operations if op.op == "copy")

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
        merged["format"] = self.get("format", other.get("format", "json-atom"))
        merged["version"] = self.get("version", other.get("version", 1))
        merged["operations"] = [*self.operations, *other.operations]
        return Delta(merged)

    # -- Filtering and transformation ----------------------------------------

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

    def map(self, fn: Callable[[Operation], Operation | dict[str, Any]]) -> Delta:
        """Return a new delta with each operation transformed by *fn*.

        Preserves all envelope-level properties. The function receives an
        :class:`Operation` and should return an ``Operation`` or raw ``dict``
        (which will be auto-wrapped).

        Example::

            # Strip oldValue for compact sync payloads
            compact = delta.map(lambda op: Operation(
                {k: v for k, v in op.items() if k != "oldValue"}
            ))
        """
        mapped_ops = [fn(op) for op in self.operations]
        result: dict[str, Any] = {k: v for k, v in self.items() if k != "operations"}
        result["operations"] = mapped_ops
        return Delta(result)

    def stamp(self, **extensions: Any) -> Delta:
        """Return a new delta with *extensions* set on every operation.

        Immutable — returns a new delta; the original is not modified.
        Preserves ``Operation`` subclasses where the subclass constructor
        accepts a dict.

        Example::

            tagged = delta.stamp(x_batch_id=batch_id, x_timestamp=now)
        """
        return self.map(lambda op: type(op)({**op, **extensions}))

    def group_by(self, key: Callable[[Operation], str]) -> dict[str, Delta]:
        """Group operations by a key function, returning a dict of sub-deltas.

        Each sub-delta preserves envelope-level properties.

        Example::

            # Group by top-level property (segments[0] — parse_path omits RootSegment)
            groups = delta.group_by(
                lambda op: op.segments[0].name
                if op.segments and isinstance(op.segments[0], PropertySegment)
                else "$"
            )
        """
        groups: dict[str, list[Operation]] = {}
        for op in self.operations:
            k = key(op)
            groups.setdefault(k, []).append(op)
        envelope = {k: v for k, v in self.items() if k != "operations"}
        return {k: Delta({**envelope, "operations": ops}) for k, ops in groups.items()}

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

        Delegates to :func:`json_atom.apply.apply_delta`.
        """
        from json_atom.apply import apply_delta

        return apply_delta(obj, self)

    def invert(self) -> Delta:
        """Compute the inverse of this delta.

        The inverse, when applied to the target document, recovers the source.

        Delegates to :func:`json_atom.invert.invert_delta`.
        """
        from json_atom.invert import invert_delta

        return invert_delta(self)

    def revert(self, obj: Any) -> Any:
        """Revert this delta by applying its inverse.

        Delegates to :func:`json_atom.invert.revert_delta`.
        """
        from json_atom.invert import revert_delta

        return revert_delta(obj, self)

    def to_json_patch(self, document: Any) -> list[dict[str, Any]]:
        """Convert this delta to an RFC 6902 JSON Patch.

        Requires the source document to resolve filter paths to positional indices.

        Delegates to :func:`json_atom.json_patch.to_json_patch`.
        """
        from json_atom.json_patch import to_json_patch

        return to_json_patch(self, document)

    @classmethod
    def from_json_patch(cls, patch: list[dict[str, Any]]) -> Delta:
        """Create a Delta from an RFC 6902 JSON Patch.

        Converts JSON Pointer paths to JSON Atom paths (index-based).
        Supports ``add``, ``remove``, ``replace`` operations.

        Raises:
            ValueError: For unsupported operations (``move``, ``copy``, ``test``).
        """
        from json_atom.json_patch import from_json_patch

        return from_json_patch(patch)

    @property
    def extensions(self) -> dict[str, Any]:
        """All non-spec properties on this delta envelope (per JSON Atom v0 Section 11).

        The ``x_`` prefix is recommended for future-safety but not enforced.
        """
        return {k: v for k, v in self.items() if k not in _DELTA_SPEC_KEYS}

    def spec_dict(self) -> dict[str, Any]:
        """Spec-only envelope with spec-only operations.

        Complement of :attr:`extensions` — strips all non-spec keys from both
        the envelope and each operation.
        """
        result = {k: v for k, v in self.items() if k in _DELTA_SPEC_KEYS}
        result["operations"] = [op.spec_dict() for op in self.operations]
        return result

    @classmethod
    def squash(
        cls,
        source: Any,
        *deltas: Delta,
        target: Any | None = None,
        array_identity_keys: ArrayIdentityKeys | None = None,
        exclude_keys: set[str] | None = None,
        exclude_paths: set[str] | None = None,
        reversible: bool = True,
        verify_target: bool = True,
    ) -> Delta:
        """Compute the net-effect delta of applying all deltas sequentially.

        This is state compaction, not history-preserving merge — intermediate
        operation metadata (extensions, granularity, ordering) is lost.

        Delegates to :func:`json_atom.diff.squash_deltas`.
        """
        from json_atom.diff import squash_deltas

        return squash_deltas(
            source,
            *deltas,
            target=target,
            array_identity_keys=array_identity_keys,
            exclude_keys=exclude_keys,
            exclude_paths=exclude_paths,
            reversible=reversible,
            verify_target=verify_target,
        )

    def __getattr__(self, name: str) -> Any:
        """Fall back to dict lookup for extension attribute access."""
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'") from None

    def __dir__(self) -> list[str]:
        """Include dict keys for tab-completion in IPython/Jupyter."""
        return sorted(set(super().__dir__()) | set(self.keys()))

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: Any) -> Any:
        """Pydantic v2 native support — zero runtime dependency on pydantic.

        Allows ``Delta`` to be used as a Pydantic field type without
        ``arbitrary_types_allowed=True``.  Accepts dicts or existing instances;
        serializes as a fully plain dict (nested Operations flattened).
        """
        from pydantic_core import core_schema as cs

        def validate(value: Any) -> Delta:
            if isinstance(value, cls):
                return value
            if isinstance(value, dict):
                return cls(value)
            raise ValueError(f"Expected dict or {cls.__name__}, got {type(value).__name__}")

        def serialize(v: Any) -> dict[str, Any]:
            result = dict(v)
            if "operations" in result:
                result["operations"] = [dict(op) for op in result["operations"]]
            return result

        return cs.json_or_python_schema(
            json_schema=cs.chain_schema([
                cs.dict_schema(),
                cs.no_info_plain_validator_function(validate),
            ]),
            python_schema=cs.union_schema([
                cs.is_instance_schema(cls),
                cs.chain_schema([
                    cs.dict_schema(),
                    cs.no_info_plain_validator_function(validate),
                ]),
            ]),
            serialization=cs.plain_serializer_function_ser_schema(
                serialize, when_used='always'
            ),
        )

    def __repr__(self) -> str:
        ops = len(self.operations) if "operations" in self else 0
        return f"Delta({ops} operations)"
