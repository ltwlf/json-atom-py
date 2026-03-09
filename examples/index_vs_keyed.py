"""Index-based vs key-based — why stable array identity matters.

Demonstrates the core problem JSON Delta solves: index-based diffs break
when arrays are reordered, while key-based diffs remain correct.

Run: uv run python examples/index_vs_keyed.py
"""

import copy
import json

from json_delta import apply_delta, diff_delta

# --- Setup: a simple task list ---

original = {
    "tasks": [
        {"id": "t1", "title": "Design API", "done": True},
        {"id": "t2", "title": "Write tests", "done": False},
        {"id": "t3", "title": "Deploy v1", "done": False},
    ]
}

# Change: mark "Write tests" as done
updated = {
    "tasks": [
        {"id": "t1", "title": "Design API", "done": True},
        {"id": "t2", "title": "Write tests", "done": True},
        {"id": "t3", "title": "Deploy v1", "done": False},
    ]
}

# --- Index-based diff (default) ---

print("=" * 60)
print("INDEX-BASED (default) — paths use position")
print("=" * 60)

index_delta = diff_delta(original, updated)

print(f"\n{len(index_delta.operations)} operations:")
for op in index_delta:
    print(f"  {op.op:>7s}  {op.path}")

print(f"\nAffected paths: {index_delta.affected_paths}")
print("Problem: paths like $.tasks[1] break if another client")
print("         inserts or removes an element before index 1.")

# Verify forward apply works
result = apply_delta(copy.deepcopy(original), index_delta)
assert result == updated

# --- Key-based diff — paths use identity ---

print(f"\n{'=' * 60}")
print("KEY-BASED (array_keys) — paths use stable identity")
print("=" * 60)

keyed_delta = diff_delta(original, updated, array_keys={"tasks": "id"})

print(f"\n{len(keyed_delta.operations)} operations:")
for op in keyed_delta:
    print(f"  {op.op:>7s}  {op.describe()}")
    if op.filter_values:
        print(f"           key: {op.filter_values}")

print(f"\nAffected paths: {keyed_delta.affected_paths}")
print("Paths like $.tasks[?(@.id=='t2')].done survive reordering,")
print("concurrent inserts, and deletions.")

# Verify forward apply works
result = apply_delta(copy.deepcopy(original), keyed_delta)
assert result == updated

# --- Payload comparison ---

index_size = len(json.dumps(index_delta))
keyed_size = len(json.dumps(keyed_delta))
print(f"\nPayload: index={index_size}B  keyed={keyed_size}B")

# --- The real test: key-based survives concurrent reorder ---

print(f"\n{'=' * 60}")
print("CONCURRENT REORDER — the key difference")
print("=" * 60)

# Another client reordered the array independently
reordered = {
    "tasks": [
        {"id": "t3", "title": "Deploy v1", "done": False},
        {"id": "t1", "title": "Design API", "done": True},
        {"id": "t2", "title": "Write tests", "done": False},
    ]
}

# Key-based delta still applies correctly — t2.done becomes True
keyed_result = apply_delta(copy.deepcopy(reordered), keyed_delta)
t2 = next(t for t in keyed_result["tasks"] if t["id"] == "t2")
assert t2["done"] is True, "Key-based delta should work on reordered array"
print("\nKey-based delta applied to reordered array:")
print(f"  t2.done = {t2['done']} ✓  (correct — matched by id, not position)")

# Index-based delta applies to the WRONG element
index_result = apply_delta(copy.deepcopy(reordered), index_delta)
t2_index = next(t for t in index_result["tasks"] if t["id"] == "t2")
t1_index = next(t for t in index_result["tasks"] if t["id"] == "t1")
print("\nIndex-based delta applied to reordered array:")
print(f"  t2.done = {t2_index['done']}  (wrong — $.tasks[1] hit t1, not t2)")
print(f"  t1.done = {t1_index['done']}  (t1 was modified instead)")

print(f"\n{'=' * 60}")
print("RESULT: Key-based diffs are stable across reordering.")
print("        Use array_keys for any array with identity keys.")
print("=" * 60)
