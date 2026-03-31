"""Advanced identity — callable keys, regex routing, and enriched comparison.

Shows JSON Atom's advanced array identity features: custom identity
resolvers, regex-based key routing, exclude_paths, and the enriched
comparison tree for visual diff rendering.

Run: uv run python examples/advanced_identity.py
"""

import copy
import re

from json_atom import (
    ChangeType,
    IdentityResolver,
    apply_delta,
    compare,
    diff_delta,
)

# ---------------------------------------------------------------------------
# 1. Callable identity keys — composite identity
# ---------------------------------------------------------------------------

print("=" * 60)
print("CALLABLE IDENTITY — custom key extraction logic")
print("=" * 60)

source = {
    "assets": [
        {"ref": "IMG-001-v2", "name": "Hero Banner", "size": 1024},
        {"ref": "IMG-002-v1", "name": "Logo", "size": 512},
        {"ref": "VID-003-v1", "name": "Intro Clip", "size": 8192},
    ]
}

target = {
    "assets": [
        {"ref": "IMG-001-v2", "name": "Hero Banner", "size": 2048},
        {"ref": "IMG-002-v1", "name": "Logo", "size": 512},
        {"ref": "VID-003-v1", "name": "Intro Clip", "size": 4096},
    ]
}

# Use the ref field but with custom extraction logic
# (e.g. normalize the version suffix for matching)
delta = diff_delta(
    source,
    target,
    array_identity_keys={
        "assets": ("ref", lambda e: e["ref"]),
    },
)

print(f"\n{len(delta.operations)} operations:")
for op in delta:
    print(f"  {op.op:>7s}  {op.describe()}")
    if op.filter_values:
        print(f"           key: {op.filter_values}")

result = apply_delta(copy.deepcopy(source), delta)
assert result == target
print("Round-trip: apply verified")

# ---------------------------------------------------------------------------
# 2. IdentityResolver — named resolver class
# ---------------------------------------------------------------------------

print(f"\n{'=' * 60}")
print("IDENTITY RESOLVER — explicit resolver with named property")
print("=" * 60)

source2 = {
    "catalog": [
        {"sku": "W-100", "category": "widget", "price": 9.99},
        {"sku": "G-200", "category": "gadget", "price": 24.99},
    ]
}

target2 = {
    "catalog": [
        {"sku": "W-100", "category": "widget", "price": 12.99},
        {"sku": "G-200", "category": "gadget", "price": 24.99},
    ]
}

resolver = IdentityResolver(
    property="sku",
    resolve=lambda item: item["sku"],
)

delta2 = diff_delta(source2, target2, array_identity_keys={"catalog": resolver})

print(f"\n{len(delta2.operations)} operations:")
for op in delta2:
    print(f"  {op.op:>7s}  {op.describe()}")

result2 = apply_delta(copy.deepcopy(source2), delta2)
assert result2 == target2
print("Round-trip: apply verified")

# ---------------------------------------------------------------------------
# 3. Regex-based key routing — one pattern for many arrays
# ---------------------------------------------------------------------------

print(f"\n{'=' * 60}")
print("REGEX ROUTING — one pattern matches multiple array paths")
print("=" * 60)

source3 = {
    "departments": {
        "engineering": {
            "employees": [
                {"id": "e1", "name": "Alice", "level": "senior"},
                {"id": "e2", "name": "Bob", "level": "mid"},
            ]
        },
        "design": {
            "employees": [
                {"id": "d1", "name": "Carol", "level": "lead"},
            ]
        },
    }
}

target3 = {
    "departments": {
        "engineering": {
            "employees": [
                {"id": "e1", "name": "Alice", "level": "staff"},
                {"id": "e2", "name": "Bob", "level": "mid"},
            ]
        },
        "design": {
            "employees": [
                {"id": "d1", "name": "Carol", "level": "lead"},
                {"id": "d2", "name": "Dan", "level": "junior"},
            ]
        },
    }
}

# Single regex matches all "employees" arrays at any depth
delta3 = diff_delta(
    source3,
    target3,
    array_identity_keys={re.compile(r"employees$"): "id"},
)

print(f"\n{len(delta3.operations)} operations:")
for op in delta3:
    print(f"  {op.op:>7s}  {op.describe()}")

result3 = apply_delta(copy.deepcopy(source3), delta3)
assert result3 == target3
print("Round-trip: apply verified")

# ---------------------------------------------------------------------------
# 4. exclude_paths — skip specific paths from comparison
# ---------------------------------------------------------------------------

print(f"\n{'=' * 60}")
print("EXCLUDE PATHS — skip specific dotted paths")
print("=" * 60)

source4 = {
    "user": {"name": "Alice", "cache": {"token": "abc123"}, "role": "viewer"},
    "product": {"name": "Widget", "cache": {"etag": "xyz"}, "price": 9.99},
}

target4 = {
    "user": {"name": "Alice", "cache": {"token": "NEW_TOKEN"}, "role": "admin"},
    "product": {"name": "Widget", "cache": {"etag": "NEW_ETAG"}, "price": 12.99},
}

# Skip user.cache but still diff product.cache
delta4 = diff_delta(source4, target4, exclude_paths={"user.cache"})

print(f"\n{len(delta4.operations)} operations:")
for op in delta4:
    print(f"  {op.op:>7s}  {op.describe()}")

# user.cache changes are excluded, product.cache changes are included
paths = {op.path for op in delta4}
assert not any("user.cache" in p for p in paths), "user.cache should be excluded"
assert any("product.cache" in p for p in paths), "product.cache should be included"
print("Exclusion verified: user.cache skipped, product.cache included")

# ---------------------------------------------------------------------------
# 5. Enriched comparison tree — for visual diff rendering
# ---------------------------------------------------------------------------

print(f"\n{'=' * 60}")
print("COMPARISON TREE — enriched diff for visual rendering")
print("=" * 60)

old_doc = {
    "title": "Project Alpha",
    "status": "draft",
    "tags": ["important", "q1"],
    "owner": {"name": "Alice", "email": "alice@example.com"},
}

new_doc = {
    "title": "Project Alpha",
    "status": "active",
    "tags": ["important", "q2"],
    "owner": {"name": "Alice", "email": "alice@newdomain.com"},
    "priority": "high",
}

tree = compare(old_doc, new_doc, array_identity_keys={"tags": "$value"})


def print_tree(node, indent=0):
    """Recursively print the comparison tree."""
    prefix = "  " * indent
    if node.type == ChangeType.CONTAINER:
        if isinstance(node.value, dict):
            for key, child in node.value.items():
                if child.type == ChangeType.CONTAINER:
                    print(f"{prefix}{key}:")
                    print_tree(child, indent + 1)
                elif child.type == ChangeType.UNCHANGED:
                    print(f"{prefix}{key}: {child.value}  (unchanged)")
                elif child.type == ChangeType.REPLACED:
                    print(f"{prefix}{key}: {child.old_value} -> {child.value}  (replaced)")
                elif child.type == ChangeType.ADDED:
                    print(f"{prefix}{key}: {child.value}  (added)")
                elif child.type == ChangeType.REMOVED:
                    print(f"{prefix}{key}: {child.old_value}  (removed)")
        elif isinstance(node.value, list):
            for i, child in enumerate(node.value):
                if child.type == ChangeType.UNCHANGED:
                    print(f"{prefix}[{i}]: {child.value}  (unchanged)")
                elif child.type == ChangeType.ADDED:
                    print(f"{prefix}[{i}]: {child.value}  (added)")
                elif child.type == ChangeType.REMOVED:
                    print(f"{prefix}[{i}]: {child.old_value}  (removed)")
                elif child.type == ChangeType.CONTAINER:
                    print(f"{prefix}[{i}]:")
                    print_tree(child, indent + 1)


print("\nComparison tree:")
print_tree(tree)

assert tree.type == ChangeType.CONTAINER
assert tree.value["title"].type == ChangeType.UNCHANGED
assert tree.value["status"].type == ChangeType.REPLACED
assert tree.value["priority"].type == ChangeType.ADDED

print(f"\n{'=' * 60}")
print("All advanced identity features verified.")
print("=" * 60)
