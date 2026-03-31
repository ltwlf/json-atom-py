"""Key-based array identity — track inventory changes by SKU, not position.

Shows how JSON Atom handles arrays where elements have a stable identity
key, producing diffs that survive insertions, deletions, and reordering.

Run: uv run python examples/keyed_arrays.py
"""

import copy
import json

from json_atom import apply_delta, diff_delta, invert_delta

# Current product inventory
source = {
    "products": [
        {"sku": "LAPTOP-001", "name": "ProBook 14", "price": 999.00, "stock": 45},
        {"sku": "MOUSE-003", "name": "ErgoClick Pro", "price": 49.99, "stock": 200},
        {"sku": "MONITOR-002", "name": "UltraWide 34", "price": 599.00, "stock": 30},
    ]
}

# Updated inventory: price cut, discontinued monitor, new keyboard
target = {
    "products": [
        {"sku": "LAPTOP-001", "name": "ProBook 14", "price": 899.00, "stock": 45},
        {"sku": "MOUSE-003", "name": "ErgoClick Pro", "price": 49.99, "stock": 200},
        {"sku": "KEYBOARD-004", "name": "MechType Ultra", "price": 129.00, "stock": 75},
    ]
}

# Compute a delta using SKU as the identity key
delta = diff_delta(source, target, array_identity_keys={"products": "sku"})

print("=== Inventory Changes ===")
for op in delta:
    print(f"  {op.op:>7s}  {op.describe()}")
    if op.value is not None:
        print(f"           -> {op.value}")
    if op.filter_values:
        print(f"           key: {op.filter_values}")

# Metrics
full_size = len(json.dumps(target))
delta_size = len(json.dumps(delta))
print(f"\nOperations: {len(delta.operations)}")
print(f"Affected:   {delta.affected_paths}")
print(f"Payload:    {delta_size}B delta vs {full_size}B full ({delta_size * 100 // full_size}%)")

# Forward: apply changes to get the new inventory
result = apply_delta(copy.deepcopy(source), delta)
assert result == target, "apply(source, delta) != target"

# Backward: roll back to previous inventory
inverse = invert_delta(delta)
recovered = apply_delta(copy.deepcopy(target), inverse)
assert recovered == source, "apply(target, inverse) != source"

print(f"\n{delta.summary()}")
print("Round-trip: apply ✓  invert ✓")
