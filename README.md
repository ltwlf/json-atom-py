# json-delta-py

[![CI](https://github.com/ltwlf/json-delta-py/actions/workflows/ci.yml/badge.svg)](https://github.com/ltwlf/json-delta-py/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/json-delta-py.svg)](https://pypi.org/project/json-delta-py/)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Deterministic JSON state transitions for Python.** Compute, apply, validate, and revert JSON Delta documents with stable array identity and reversible operations. Built for audit logs, undo/redo systems, data synchronization, and agent/workflow state tracking.

Zero dependencies. Fully typed. Python 3.12+.

> **Ecosystem note:** This project implements the [JSON Delta specification](https://github.com/ltwlf/json-delta-format). It is unrelated to the older `json-delta` package on PyPI.

```text
json-delta-format  (specification)
    ├── json-diff-ts      (TypeScript implementation)
    └── json-delta-py     (Python implementation)  ← this package
```

The specification defines the wire format. Each language implementation produces and consumes compatible deltas. A TypeScript implementation is also available: [json-diff-ts](https://github.com/ltwlf/json-diff-ts).

## Installation

```bash
pip install json-delta-py
```

## Quick Start

```python
import copy
from json_delta import diff_delta, apply_delta, revert_delta

source = {"user": {"name": "Alice", "role": "viewer"}}
target = {"user": {"name": "Alice", "role": "admin"}}

# Compute a delta
delta = diff_delta(source, target)

# Apply it
result = apply_delta(copy.deepcopy(source), delta)
assert result == target

# Revert it
recovered = revert_delta(copy.deepcopy(target), delta)
assert recovered == source
```

The delta is a `Delta` instance (a `dict` subclass) — JSON-serializable, storable, and consumable in any language. For raw dicts from JSON payloads, wrap with `Delta(d)` or `Delta.from_dict(d)` to get typed access:

```json
{
  "format": "json-delta",
  "version": 1,
  "operations": [
    { "op": "replace", "path": "$.user.role", "value": "admin", "oldValue": "viewer" }
  ]
}
```

## Typed Models

Delta and Operation are dict subclasses with full IDE support — autocomplete, typed properties, factory methods, and extension attribute access:

```python
from json_delta import Delta, Operation

# Factory methods with IDE autocomplete
op = Operation.replace("$.user.role", "admin", old_value="viewer")
op.op            # "replace" — typed property
op.path          # "$.user.role"
op.describe()    # "user > role"
op.segments      # [PropertySegment("user"), PropertySegment("role")] — cached
op.filter_values # {} — cached

# Extension properties as attributes (spec Section 11)
op = Operation.add("$.x", 1, x_editor="Alice", x_reason="onboarding")
op.x_editor      # "Alice" — attribute access
op.extensions    # {"x_editor": "Alice", "x_reason": "onboarding"}

# Build deltas with the factory
delta = Delta.create(
    Operation.add("$.name", "Alice"),
    Operation.replace("$.role", "admin", old_value="viewer"),
)

for op in delta:              # iterate operations
    print(op.describe())

delta.filter(lambda op: op.op == "add")   # filter by predicate
delta.affected_paths                       # {"$.name", "$.role"}
delta.summary()                            # human-readable overview
```

Still plain dicts — `json.dumps(delta)`, `delta["format"]`, and all dict operations work as expected.

## Pydantic Integration

Operation and Delta work as native Pydantic v2 field types — no `arbitrary_types_allowed`, no custom validators:

```python
from pydantic import BaseModel
from json_delta import Delta

class AuditEntry(BaseModel):
    delta: Delta      # just works — no arbitrary_types_allowed needed
    actor: str = ""

# From a raw dict (e.g., API request body or JSON payload)
entry = AuditEntry(
    delta={
        "format": "json-delta",
        "version": 1,
        "operations": [
            {"op": "replace", "path": "$.user.role", "value": "admin", "oldValue": "viewer"},
            {"op": "add", "path": "$.user.verified", "value": True},
        ],
    },
    actor="admin",
)

entry.delta.operations[0].op     # "replace" — typed access
entry.delta.operations[0].path   # "$.user.role"
entry.model_dump()               # plain dicts, no subclass instances
entry.model_dump_json()          # clean JSON serialization
AuditEntry.model_validate_json(  # full round-trip
    entry.model_dump_json()
)
```

Pydantic is **not** a runtime dependency. The integration uses `__get_pydantic_core_schema__` which is only invoked when pydantic is installed.

## What Is JSON Delta

[JSON Delta](https://github.com/ltwlf/json-delta-format) is a format for describing deterministic state transitions between JSON documents. A delta captures the exact set of changes — adds, removes, and replacements — needed to transform a source document into a target. Deltas are plain JSON: they can be applied, stored, transmitted, replayed, and inverted in any language.

## Why JSON Delta Exists

Most JSON diff libraries track array changes by position. Insert one element at the start and every path shifts:

```text
Remove /items/0  ← was actually "Widget"
Add    /items/0  ← now it's "NewItem"
Update /items/1  ← this used to be /items/0
```

This makes diffs fragile. You can't store them, replay them reliably, or build audit logs on top of them. This is the fundamental problem with index-based formats like JSON Patch (RFC 6902): paths like `/items/0` are positional, so any insertion, deletion, or reorder invalidates every subsequent path.

**JSON Delta solves this with key-based identity.** Array elements are matched by a stable key, and paths use JSONPath filter expressions that survive insertions, deletions, and reordering:

- **Key-based array identity** — paths like `$.items[?(@.id==42)]` stay valid regardless of array order
- **Built-in reversibility** — `oldValue` fields let you invert any delta without external state
- **Self-describing** — the `format` field and path expressions make deltas discoverable without external context

## What JSON Delta Is Useful For

- **Audit logs** — record exactly what changed, revert any change on demand
- **Undo/redo** — invert deltas to move backward and forward through state history
- **Data synchronization** — send compact deltas instead of full documents
- **Configuration history** — track config changes with stable references across deployments
- **Agent and workflow state** — track state transitions in AI agent loops or workflow engines

## Array Identity Models

JSON Delta supports three ways to identify array elements:

```python
from json_delta import diff_delta

old = {"items": [{"id": 1, "name": "Widget"}, {"id": 2, "name": "Gadget"}]}
new = {"items": [{"id": 1, "name": "Widget Pro"}, {"id": 2, "name": "Gadget"}]}

# Key-based: track elements by a property value
delta = diff_delta(old, new, array_identity_keys={"items": "id"})
# Path: $.items[?(@.id==1)].name — stable across reordering

# Value-based: for primitive arrays with unique values
old_tags = {"tags": ["urgent", "draft"]}
new_tags = {"tags": ["urgent", "review"]}
delta = diff_delta(old_tags, new_tags, array_identity_keys={"tags": "$value"})
# Paths: $.tags[?(@=='draft')] (remove), $.tags[?(@=='review')] (add)
# Note: $value identity requires unique elements — duplicates raise DiffError

# Index-based (default): track elements by position
delta = diff_delta(old, new)
# Path: $.items[0].name — positional, fragile across concurrent changes
```

### Advanced Identity Keys

For complex scenarios, use callable identity keys or regex-based routing:

```python
import re
from json_delta import diff_delta, IdentityResolver

# Callable tuple: (property_name, extractor_function)
delta = diff_delta(old, new, array_identity_keys={
    "assets": ("ref", lambda e: e["ref"]),
})

# IdentityResolver: explicit resolver class
resolver = IdentityResolver(property="sku", resolve=lambda e: e["sku"])
delta = diff_delta(old, new, array_identity_keys={"catalog": resolver})

# Regex routing: one pattern matches multiple array paths
delta = diff_delta(old, new, array_identity_keys={
    re.compile(r"employees$"): "id",    # matches employees arrays at any depth
    re.compile(r"items$"): "sku",       # matches items arrays at any depth
})
```

### Excluding Properties

Skip properties by name (any depth) or by specific dotted path:

```python
# exclude_keys: skip a key name at any depth
delta = diff_delta(old, new, exclude_keys={"updatedAt", "_etag"})

# exclude_paths: skip at a specific path only
delta = diff_delta(old, new, exclude_paths={"user.cache", "meta.hash"})

# Combined: exclude_keys for noise, exclude_paths for targeted exclusion
delta = diff_delta(old, new,
    exclude_keys={"_etag"},
    exclude_paths={"user.cache"},
)
```

> **Note:** `exclude_paths` uses `.` as a segment separator, so it cannot
> unambiguously target keys that literally contain `.`. For such keys, use
> `exclude_keys` instead (which matches by name regardless of depth).

### Enriched Comparison Tree

The `compare()` function returns a full comparison tree including unchanged values — ideal for rendering side-by-side diffs or change-highlighted UIs:

```python
from json_delta import compare, ChangeType

tree = compare(
    {"name": "Alice", "role": "viewer", "email": "a@example.com"},
    {"name": "Alice", "role": "admin", "team": "eng"},
)

# tree.type == ChangeType.CONTAINER
# tree.value["name"].type == ChangeType.UNCHANGED
# tree.value["role"].type == ChangeType.REPLACED  (.value="admin", .old_value="viewer")
# tree.value["email"].type == ChangeType.REMOVED  (.old_value="a@example.com")
# tree.value["team"].type == ChangeType.ADDED     (.value="eng")
```

## API Reference

### Functions

| Function | Description |
| --- | --- |
| `diff_delta(old, new, *, array_identity_keys=None, exclude_keys=None, exclude_paths=None, reversible=True)` | Compute a delta between two objects |
| `apply_delta(obj, delta)` | Apply a delta to an object (mutates in place, use return value) |
| `validate_delta(delta)` | Validate delta structure, returns `ValidationResult` |
| `invert_delta(delta)` | Compute the inverse of a reversible delta |
| `revert_delta(obj, delta)` | Revert a delta (shorthand for `apply(obj, invert(delta))`) |
| `parse_path(path)` | Parse a JSON Delta Path string into typed segments |
| `build_path(segments)` | Build a canonical path string from segments |
| `describe_path(path)` | Human-readable description (`"$.user.name"` → `"user > name"`) |
| `resolve_path(path, document)` | Resolve filter path to RFC 6901 JSON Pointer |
| `compare(old, new, *, array_identity_keys=None, exclude_keys=None, exclude_paths=None)` | Enriched comparison tree for visual diff rendering |
| `to_json_patch(delta, document)` | Convert delta to RFC 6902 JSON Patch |
| `from_json_patch(patch)` | Create delta from RFC 6902 JSON Patch |

### Operation Factories

| Factory | Description |
| --- | --- |
| `Operation.add(path, value, **ext)` | Create an `add` operation |
| `Operation.replace(path, value, *, old_value=None, **ext)` | Create a `replace` operation |
| `Operation.remove(path, *, old_value=None, **ext)` | Create a `remove` operation |

### Delta Factories

| Factory | Description |
| --- | --- |
| `Delta.create(*operations, **ext)` | Create a delta with standard envelope |
| `Delta.from_dict(d)` | Create from raw dict with validation |
| `Delta.from_json_patch(patch)` | Create from RFC 6902 JSON Patch |

### Types

| Type | Description |
| --- | --- |
| `Delta` | Delta document (dict subclass with typed properties) |
| `Operation` | Single operation (dict subclass with typed properties) |
| `IdentityResolver` | Custom identity resolution: `IdentityResolver(property, resolve)` |
| `ComparisonNode` | Node in the enriched comparison tree |
| `ChangeType` | Change classification: `unchanged`, `added`, `removed`, `replaced`, `container` |
| `ValidationResult` | Structured validation result: `.valid`, `.errors` |
| `OpType` | Operation type literal: `"add"`, `"remove"`, `"replace"` |

## JSON Delta vs JSON Patch

| Feature | JSON Delta | JSON Patch (RFC 6902) |
| --- | --- | --- |
| Path syntax | JSONPath (`$.items[?(@.id==1)]`) | JSON Pointer (`/items/0`) |
| Array identity | Key-based — survives reorder | Index-based — breaks on insert/delete |
| Reversibility | Built-in via `oldValue` | Not supported |
| Self-describing | `format` field in envelope | No envelope |
| Extensions | `x_`-prefixed properties preserved | Not supported |
| Specification | [json-delta-format](https://github.com/ltwlf/json-delta-format) | [RFC 6902](https://tools.ietf.org/html/rfc6902) |

## Examples

Pick the example that matches your use case:

| Example | Use case | What it shows |
| --- | --- | --- |
| [quick_api_payload.py](examples/quick_api_payload.py) | **Getting started** | Raw JSON in → validate → apply → revert → serialize |
| [index_vs_keyed.py](examples/index_vs_keyed.py) | **Why key-based?** | Side-by-side: index-based breaks on reorder, key-based survives |
| [keyed_arrays.py](examples/keyed_arrays.py) | **Inventory / CRUD** | Key-based array diffs with payload size comparison |
| [audit_log.py](examples/audit_log.py) | **Compliance / history** | Reversible deltas with extension metadata, replay and revert |
| [undo_redo.py](examples/undo_redo.py) | **Editor / config** | Multi-step undo/redo stack built on delta inversion |
| [data_sync.py](examples/data_sync.py) | **Client-server sync** | Compute on client, serialize, validate + apply on server |
| [state_transitions.py](examples/state_transitions.py) | **Agent / workflow** | Track state changes between steps with affected paths |
| [advanced_identity.py](examples/advanced_identity.py) | **Advanced identity** | Callable keys, regex routing, exclude_paths, comparison tree |

```bash
uv run python examples/quick_api_payload.py   # start here
uv run python examples/index_vs_keyed.py      # see the differentiator
uv run python examples/keyed_arrays.py
uv run python examples/audit_log.py
uv run python examples/undo_redo.py
uv run python examples/data_sync.py
uv run python examples/state_transitions.py
uv run python examples/advanced_identity.py   # advanced features
```

## Specification

This library implements the [JSON Delta v0 specification](https://github.com/ltwlf/json-delta-format/blob/main/spec/v0.md). It passes all Level 1 (Apply) and Level 2 (Reversible) conformance fixtures.

## Requirements

- Python 3.12+
- Zero runtime dependencies

## License

MIT
