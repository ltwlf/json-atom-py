"""Quick start — raw dict in, validate, apply, revert, serialize out.

The minimum viable workflow for an API endpoint that receives
a delta payload, validates it, applies it, and can revert if needed.
"""

import copy
import json

from json_delta import Delta, apply_delta, revert_delta, validate_delta

# --- 1. Receive a raw JSON payload (e.g., from an API request body) ---

raw_json = """
{
  "format": "json-delta",
  "version": 1,
  "operations": [
    {"op": "replace", "path": "$.user.role", "value": "admin", "oldValue": "viewer"},
    {"op": "add", "path": "$.user.permissions", "value": ["read", "write", "delete"]}
  ]
}
"""

# --- 2. Parse and validate ---

payload = json.loads(raw_json)
delta = Delta.from_dict(payload)  # checks envelope keys

validation = validate_delta(delta)
assert validation.valid, f"Invalid: {validation.errors}"

print("=== Received Delta ===")
print(f"Operations: {len(delta.operations)}")
print(f"Reversible: {all(op.old_value is not None for op in delta if op.op != 'add')}")
print(f"Affected:   {delta.affected_paths}")
print(f"\n{delta.summary()}")

# --- 3. Apply to current state ---

current = {"user": {"name": "Alice", "role": "viewer"}}
print(f"\nBefore: {json.dumps(current)}")

result = apply_delta(copy.deepcopy(current), delta)
print(f"After:  {json.dumps(result)}")

assert result["user"]["role"] == "admin"
assert result["user"]["permissions"] == ["read", "write", "delete"]

# --- 4. Revert if needed ---

reverted = revert_delta(copy.deepcopy(result), delta)
print(f"Revert: {json.dumps(reverted)}")

assert reverted == current, "Revert should restore original state"

# --- 5. Serialize back to JSON for storage or HTTP response ---

response = json.dumps(delta, indent=2)
print(f"\nDelta payload: {len(response)} bytes")
print("Round-trip: receive → validate → apply → revert → serialize ✓")
