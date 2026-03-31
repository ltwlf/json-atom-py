# CLAUDE.md — Developer Guide for json-atom-py

## Build & Test Commands

```bash
uv sync                          # Install dependencies
uv run pytest tests/             # Run all tests
uv run pytest tests/ -v          # Verbose output
uv run pytest tests/ --cov=json_atom  # With coverage
uv run ruff check src/           # Lint
uv run mypy src/                 # Type check
uv run python examples/keyed_arrays.py  # Run an example
uv build                         # Build wheel + sdist
```

## Project Structure

```
src/json_atom/
    __init__.py       # Public API re-exports and __all__
    errors.py         # Exception hierarchy (JsonDeltaError → PathError, ApplyError, etc.)
    models.py         # PathSegment dataclasses, ValidationResult, ChangeType, ComparisonNode, Delta/Operation
    _utils.py         # Internal helpers: json_equal, json_type_of
    _identity.py      # Shared identity resolution (IdentityResolver, resolve_identity, extract_identity)
    path.py           # Path parser/builder + describe_path, resolve_path
    validate.py       # Structural validation (validate_delta)
    apply.py          # Delta application (apply_delta)
    invert.py         # Delta inversion (invert_delta, revert_delta)
    diff.py           # Delta computation (diff_delta) — callable keys, regex routing, exclude_paths
    compare.py        # Enriched comparison tree (compare) — visual diff rendering
    json_patch.py     # JSON Patch (RFC 6902) interop: to_json_patch, from_json_patch
    py.typed          # PEP 561 marker

tests/
    conftest.py       # Shared helpers: load_fixture, deep_clone
    fixtures/         # Conformance fixtures from json-atom-format repo
    test_models.py    # PathSegment, ValidationResult, Delta/Operation types
    test_utils.py     # json_equal edge cases (bool vs int, int vs float)
    test_path.py      # Path parser/builder, describe_path, resolve_path
    test_validate.py  # Delta validation
    test_apply.py     # Delta application + Level 1 conformance
    test_invert.py    # Inversion + revert round-trips
    test_extensions.py  # Extension property preservation
    test_conformance.py # Level 1 + Level 2 conformance fixtures
    test_diff.py      # Diff computation + all identity models + callable/regex/exclude_paths
    test_compare.py   # Enriched comparison tree tests
    test_cross_validation.py # Cross-validation with json-diff-ts
    test_edge_cases.py  # Cross-module edge cases
    test_json_patch.py  # JSON Patch (RFC 6902) interop
    test_pydantic.py    # Pydantic v2 integration (conditional on pydantic)
```

## Architecture

- **Zero runtime dependencies** — uses only stdlib (re, copy, math, dataclasses)
- **Delta/Operation are dict subclasses** — typed property access (`delta.operations`, `op.path`) + full dict compat (`json.dumps`, `[]` access, extensions)
- **Extension properties** accessible as attributes (`op.x_editor`) or dict syntax (`op["x_editor"]`), via `__getattr__` fallback. `op.extensions` returns all non-spec keys
- **Pydantic v2 native** — `__get_pydantic_core_schema__` on both classes, zero runtime dependency on pydantic. Use as `BaseModel` fields without `arbitrary_types_allowed`
- **Cached properties** — `op.segments` and `op.filter_values` are `cached_property` (parsed once per instance)
- **Path segments are frozen dataclasses** — immutable, hashable, printable
- **apply_delta mutates in place** — always use the return value (root ops return new objects)
- **json_equal handles Python's bool⊂int** — `True != 1` in JSON semantics

## Spec Compliance

- **Specification**: [JSON Atom v0](https://github.com/ltwlf/json-atom-format/blob/main/spec/v0.md)
- **Conformance**: Level 2 (Apply + Reversible) — passes all fixtures
- **Spec is source of truth** — when spec and TypeScript reference diverge, follow the spec
- **Spec-faithful divergence from TS**: digit-after-dot (`$.items.0`) is a PathError per spec grammar
- **remove without oldValue**: valid per spec (OPTIONAL), unlike TS which requires it

## Coding Conventions

- Python 3.12+ — uses `type` statement, `X | Y` union syntax, `@dataclass(slots=True)`
- Strict mypy on library source (`uv run mypy src/`; tests are not strict-checked)
- Ruff for linting (line-length=120)
- All public functions have docstrings
- Tests organized by module with descriptive class names
