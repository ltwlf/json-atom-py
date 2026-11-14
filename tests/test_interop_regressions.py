import copy

import pytest

from json_atom import apply_delta, diff_delta, validate_delta
from json_atom.errors import ApplyError
from json_atom.path import build_path, parse_path, resolve_path


def atom(*ops):
    return {"format": "json-atom", "version": 1, "operations": list(ops)}


@pytest.mark.parametrize(
    "path", ["$.items[?(@.meta['a.b']==42)].value", "$['items'][?(@['meta']['a.b']==42)]['value']"]
)
def test_mixed_member_paths(path):
    before = {"items": [{"meta": {"a.b": 42}, "value": 1}]}
    expected = {"items": [{"meta": {"a.b": 42}, "value": 2}]}
    assert apply_delta(copy.deepcopy(before), atom({"op": "replace", "path": path, "value": 2})) == expected
    assert build_path(parse_path(path)) == "$.items[?(@.meta['a.b']==42)].value"
    assert resolve_path(path, before) == "/items/0/value"


@pytest.mark.parametrize("before,after", [({"x": [True]}, {"x": [1]}), ({"x": {"a": False}}, {"x": {"a": 0}})])
def test_nested_boolean_number_changes(before, after):
    delta = diff_delta(before, after)
    assert delta["operations"]
    actual = apply_delta(copy.deepcopy(before), delta)
    import json

    assert json.dumps(actual) == json.dumps(after)


def test_failed_move_preserves_source():
    before = {"a": 1, "b": 2}
    saved = copy.deepcopy(before)
    with pytest.raises(ApplyError):
        apply_delta(before, atom({"op": "move", "from": "$.a", "path": "$.b"}))
    assert before == saved


@pytest.mark.parametrize("source,target", [("$", "$.a"), ("$.a", "$['a'].b"), ("$.a", "$['a']")])
def test_invalid_move_aliases(source, target):
    assert not validate_delta(atom({"op": "move", "from": source, "path": target})).valid


@pytest.mark.parametrize("version", [0, 2, -1])
def test_unsupported_version(version):
    delta = atom()
    delta["version"] = version
    assert not validate_delta(delta).valid


@pytest.mark.parametrize("source,target", [(None, {"x": 1}), ({"x": 1}, None), (None, 0), (False, None)])
def test_root_lifecycle_round_trip(source, target):
    from json_atom import revert_delta

    delta = diff_delta(source, target)
    assert delta["operations"][0]["op"] == ("add" if source is None else "remove")
    assert apply_delta(copy.deepcopy(source), delta) == target
    assert revert_delta(copy.deepcopy(target), delta) == source


def test_empty_delta_streaming_serialization():
    import io
    import json

    delta = diff_delta({}, {})
    stream = io.StringIO()
    json.dump(dict(delta), stream, indent=2)
    assert json.loads(stream.getvalue()) == {"format": "json-atom", "version": 1, "operations": []}
