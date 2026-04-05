"""Tests for json_atom.path — path parsing, building, and filter literals."""

import pytest

from json_atom.errors import PathError
from json_atom.models import (
    IndexSegment,
    KeyFilterSegment,
    PropertySegment,
    RootSegment,
    ValueFilterSegment,
)
from json_atom.path import (
    build_path,
    describe_path,
    format_filter_literal,
    parse_filter_literal,
    parse_path,
    resolve_path,
)


# ===========================================================================
# format_filter_literal
# ===========================================================================


class TestFormatFilterLiteral:
    def test_string(self) -> None:
        assert format_filter_literal("Alice") == "'Alice'"

    def test_string_with_single_quote(self) -> None:
        assert format_filter_literal("O'Brien") == "'O''Brien'"

    def test_empty_string(self) -> None:
        assert format_filter_literal("") == "''"

    def test_integer(self) -> None:
        assert format_filter_literal(42) == "42"

    def test_zero(self) -> None:
        assert format_filter_literal(0) == "0"

    def test_negative_integer(self) -> None:
        assert format_filter_literal(-5) == "-5"

    def test_float(self) -> None:
        assert format_filter_literal(3.14) == "3.14"

    def test_bool_true(self) -> None:
        assert format_filter_literal(True) == "true"

    def test_bool_false(self) -> None:
        assert format_filter_literal(False) == "false"

    def test_none(self) -> None:
        assert format_filter_literal(None) == "null"

    def test_infinity_raises(self) -> None:
        with pytest.raises(PathError, match="Non-finite"):
            format_filter_literal(float("inf"))

    def test_nan_raises(self) -> None:
        with pytest.raises(PathError, match="Non-finite"):
            format_filter_literal(float("nan"))

    def test_negative_infinity_raises(self) -> None:
        with pytest.raises(PathError, match="Non-finite"):
            format_filter_literal(float("-inf"))

    def test_unsupported_type_raises(self) -> None:
        with pytest.raises(PathError, match="Cannot format"):
            format_filter_literal([1, 2, 3])

        with pytest.raises(PathError, match="Cannot format"):
            format_filter_literal({"a": 1})


# ===========================================================================
# parse_filter_literal
# ===========================================================================


class TestParseFilterLiteral:
    def test_string(self) -> None:
        assert parse_filter_literal("'Alice'") == "Alice"

    def test_string_with_escaped_quotes(self) -> None:
        assert parse_filter_literal("'O''Brien'") == "O'Brien"

    def test_empty_string(self) -> None:
        assert parse_filter_literal("''") == ""

    def test_integer(self) -> None:
        assert parse_filter_literal("42") == 42
        assert isinstance(parse_filter_literal("42"), int)

    def test_zero(self) -> None:
        assert parse_filter_literal("0") == 0

    def test_negative_integer(self) -> None:
        assert parse_filter_literal("-5") == -5

    def test_float(self) -> None:
        assert parse_filter_literal("3.14") == 3.14
        assert isinstance(parse_filter_literal("3.14"), float)

    def test_float_with_exponent(self) -> None:
        assert parse_filter_literal("1e10") == 1e10
        assert isinstance(parse_filter_literal("1e10"), float)

    def test_float_with_negative_exponent(self) -> None:
        assert parse_filter_literal("1.5E-3") == 1.5e-3

    def test_bool_true(self) -> None:
        result = parse_filter_literal("true")
        assert result is True

    def test_bool_false(self) -> None:
        result = parse_filter_literal("false")
        assert result is False

    def test_null(self) -> None:
        result = parse_filter_literal("null")
        assert result is None

    def test_empty_raises(self) -> None:
        with pytest.raises(PathError, match="Empty filter literal"):
            parse_filter_literal("")

    def test_hex_raises(self) -> None:
        with pytest.raises(PathError, match="Invalid filter literal"):
            parse_filter_literal("0x1A")

    def test_octal_raises(self) -> None:
        with pytest.raises(PathError, match="Invalid filter literal"):
            parse_filter_literal("0o77")

    def test_binary_raises(self) -> None:
        with pytest.raises(PathError, match="Invalid filter literal"):
            parse_filter_literal("0b101")

    def test_leading_zeros_raises(self) -> None:
        with pytest.raises(PathError, match="Invalid filter literal"):
            parse_filter_literal("042")

    def test_invalid_string_raises(self) -> None:
        with pytest.raises(PathError, match="Invalid filter literal"):
            parse_filter_literal("notALiteral")

    def test_leading_plus_raises(self) -> None:
        with pytest.raises(PathError, match="Invalid filter literal"):
            parse_filter_literal("+5")


# ===========================================================================
# parse_path — valid paths
# ===========================================================================


class TestParsePath:
    def test_root_only(self) -> None:
        segments = parse_path("$")
        assert segments == []

    def test_single_dot_property(self) -> None:
        segments = parse_path("$.name")
        assert segments == [PropertySegment("name")]

    def test_chained_dot_properties(self) -> None:
        segments = parse_path("$.user.address.city")
        assert segments == [
            PropertySegment("user"),
            PropertySegment("address"),
            PropertySegment("city"),
        ]

    def test_property_with_underscore(self) -> None:
        segments = parse_path("$._private")
        assert segments == [PropertySegment("_private")]

    def test_property_with_digits(self) -> None:
        segments = parse_path("$.item2")
        assert segments == [PropertySegment("item2")]

    def test_bracket_property_simple(self) -> None:
        segments = parse_path("$['name']")
        assert segments == [PropertySegment("name")]

    def test_bracket_property_with_dot(self) -> None:
        segments = parse_path("$['a.b']")
        assert segments == [PropertySegment("a.b")]

    def test_bracket_property_with_escaped_quote(self) -> None:
        """$['O''Brien'] → property O'Brien (spec Appendix G.1)."""
        segments = parse_path("$['O''Brien']")
        assert segments == [PropertySegment("O'Brien")]

    def test_bracket_property_digit_starting_name(self) -> None:
        """$['0'] is a property named '0', not an array index (spec G.1)."""
        segments = parse_path("$['0']")
        assert segments == [PropertySegment("0")]

    def test_array_index_zero(self) -> None:
        segments = parse_path("$.items[0]")
        assert segments == [PropertySegment("items"), IndexSegment(0)]

    def test_array_index_multidigit(self) -> None:
        segments = parse_path("$.items[42]")
        assert segments == [PropertySegment("items"), IndexSegment(42)]

    def test_key_filter_with_number(self) -> None:
        segments = parse_path("$.items[?(@.id==42)]")
        assert segments == [PropertySegment("items"), KeyFilterSegment("id", 42)]

    def test_key_filter_with_string(self) -> None:
        segments = parse_path("$.items[?(@.id=='abc')]")
        assert segments == [PropertySegment("items"), KeyFilterSegment("id", "abc")]

    def test_key_filter_with_boolean_true(self) -> None:
        segments = parse_path("$.items[?(@.active==true)]")
        assert segments == [PropertySegment("items"), KeyFilterSegment("active", True)]

    def test_key_filter_with_boolean_false(self) -> None:
        segments = parse_path("$.items[?(@.active==false)]")
        assert segments == [PropertySegment("items"), KeyFilterSegment("active", False)]

    def test_key_filter_with_null(self) -> None:
        segments = parse_path("$.items[?(@.status==null)]")
        assert segments == [PropertySegment("items"), KeyFilterSegment("status", None)]

    def test_key_filter_with_negative_number(self) -> None:
        segments = parse_path("$.items[?(@.offset==-3)]")
        assert segments == [PropertySegment("items"), KeyFilterSegment("offset", -3)]

    def test_key_filter_with_bracket_property(self) -> None:
        """$[?(@['dotted.key']==42)] — bracket property in filter."""
        segments = parse_path("$.items[?(@['dotted.key']==42)]")
        assert segments == [PropertySegment("items"), KeyFilterSegment("dotted.key", 42, literal_key=True)]

    def test_value_filter_with_string(self) -> None:
        segments = parse_path("$.tags[?(@=='urgent')]")
        assert segments == [PropertySegment("tags"), ValueFilterSegment("urgent")]

    def test_value_filter_with_number(self) -> None:
        segments = parse_path("$.scores[?(@==100)]")
        assert segments == [PropertySegment("scores"), ValueFilterSegment(100)]

    def test_deep_path_after_key_filter(self) -> None:
        segments = parse_path("$.items[?(@.id==1)].name")
        assert segments == [
            PropertySegment("items"),
            KeyFilterSegment("id", 1),
            PropertySegment("name"),
        ]

    def test_deep_path_after_key_filter_multiple_levels(self) -> None:
        segments = parse_path("$.items[?(@.id==1)].address.city")
        assert segments == [
            PropertySegment("items"),
            KeyFilterSegment("id", 1),
            PropertySegment("address"),
            PropertySegment("city"),
        ]

    def test_non_canonical_bracket_for_everything(self) -> None:
        """$['user']['name'] — non-canonical but must be accepted (spec 5.5)."""
        segments = parse_path("$['user']['name']")
        assert segments == [PropertySegment("user"), PropertySegment("name")]

    def test_filter_with_string_containing_close_paren_bracket(self) -> None:
        """Filter with string literal containing )] must not confuse parser."""
        segments = parse_path("$.items[?(@.name=='a)]b')]")
        assert segments == [PropertySegment("items"), KeyFilterSegment("name", "a)]b")]

    def test_key_filter_with_float_literal(self) -> None:
        segments = parse_path("$.items[?(@.score==3.14)]")
        assert segments == [PropertySegment("items"), KeyFilterSegment("score", 3.14)]

    def test_mixed_segments(self) -> None:
        """Complex path with multiple segment types."""
        segments = parse_path("$.users[?(@.id==1)].contacts[0].email")
        assert segments == [
            PropertySegment("users"),
            KeyFilterSegment("id", 1),
            PropertySegment("contacts"),
            IndexSegment(0),
            PropertySegment("email"),
        ]


# ===========================================================================
# parse_path — error cases
# ===========================================================================


class TestParsePathErrors:
    def test_empty_path(self) -> None:
        with pytest.raises(PathError, match="Empty path"):
            parse_path("")

    def test_missing_dollar(self) -> None:
        with pytest.raises(PathError, match="must start with"):
            parse_path(".user.name")

    def test_trailing_dot(self) -> None:
        """$. (trailing dot) → error (spec Appendix G.1)."""
        with pytest.raises(PathError, match="Empty property name"):
            parse_path("$.")

    def test_leading_zeros_in_index(self) -> None:
        """$[01] → error (spec Appendix G.1)."""
        with pytest.raises(PathError, match="Leading zeros"):
            parse_path("$[01]")

    def test_digit_after_dot(self) -> None:
        """$.items.0 → error (spec Section 5.5, Appendix G.1)."""
        with pytest.raises(PathError, match="must start with a letter or underscore"):
            parse_path("$.items.0")

    def test_unexpected_character(self) -> None:
        with pytest.raises(PathError, match="Unexpected character"):
            parse_path("$#foo")

    def test_unexpected_after_bracket(self) -> None:
        with pytest.raises(PathError, match="Unexpected character"):
            parse_path("$[!foo]")

    def test_unterminated_bracket_property(self) -> None:
        with pytest.raises(PathError, match="Unterminated quoted string"):
            parse_path("$['unterminated")

    def test_unterminated_array_index(self) -> None:
        with pytest.raises(PathError, match="Unterminated array index"):
            parse_path("$[42")

    def test_unterminated_filter(self) -> None:
        with pytest.raises(PathError, match="Unterminated filter|missing"):
            parse_path("$[?(@.id==42")

    def test_invalid_filter_missing_eq(self) -> None:
        with pytest.raises(PathError, match="missing '=='|Invalid filter"):
            parse_path("$[?(@.id)]")

    def test_double_dot(self) -> None:
        with pytest.raises(PathError):
            parse_path("$..name")

    def test_only_dollar_dot(self) -> None:
        """$. is invalid."""
        with pytest.raises(PathError, match="Empty property name"):
            parse_path("$.")

    def test_bracket_missing_closing(self) -> None:
        with pytest.raises(PathError, match="Unterminated|Expected"):
            parse_path("$['key'")

    def test_path_ending_with_bracket(self) -> None:
        with pytest.raises(PathError, match="Unexpected end"):
            parse_path("$[")


# ===========================================================================
# build_path
# ===========================================================================


class TestBuildPath:
    def test_root_only(self) -> None:
        assert build_path([]) == "$"

    def test_root_segment_ignored(self) -> None:
        """RootSegment in the list is skipped (root is always implicit)."""
        assert build_path([RootSegment()]) == "$"

    def test_simple_property(self) -> None:
        assert build_path([PropertySegment("name")]) == "$.name"

    def test_chained_properties(self) -> None:
        segments = [PropertySegment("user"), PropertySegment("address"), PropertySegment("city")]
        assert build_path(segments) == "$.user.address.city"

    def test_property_needing_brackets(self) -> None:
        """Property with a dot must use bracket notation."""
        assert build_path([PropertySegment("a.b")]) == "$['a.b']"

    def test_property_starting_with_digit(self) -> None:
        """Property starting with digit must use bracket notation."""
        assert build_path([PropertySegment("0key")]) == "$['0key']"

    def test_property_with_space(self) -> None:
        assert build_path([PropertySegment("my key")]) == "$['my key']"

    def test_property_with_single_quote(self) -> None:
        assert build_path([PropertySegment("O'Brien")]) == "$['O''Brien']"

    def test_array_index(self) -> None:
        segments = [PropertySegment("items"), IndexSegment(0)]
        assert build_path(segments) == "$.items[0]"

    def test_key_filter_number(self) -> None:
        segments = [PropertySegment("items"), KeyFilterSegment("id", 42)]
        assert build_path(segments) == "$.items[?(@.id==42)]"

    def test_key_filter_string(self) -> None:
        segments = [PropertySegment("items"), KeyFilterSegment("id", "abc")]
        assert build_path(segments) == "$.items[?(@.id=='abc')]"

    def test_key_filter_boolean(self) -> None:
        segments = [PropertySegment("items"), KeyFilterSegment("active", True)]
        assert build_path(segments) == "$.items[?(@.active==true)]"

    def test_key_filter_null(self) -> None:
        segments = [PropertySegment("items"), KeyFilterSegment("status", None)]
        assert build_path(segments) == "$.items[?(@.status==null)]"

    def test_key_filter_nested_path(self) -> None:
        """Key filter with nested path uses dot notation per RFC 9535."""
        segments = [PropertySegment("items"), KeyFilterSegment("positionNumber.value", 42)]
        assert build_path(segments) == "$.items[?(@.positionNumber.value==42)]"

    def test_key_filter_bracket_property(self) -> None:
        """Key filter with non-identifier property uses bracket notation."""
        segments = [PropertySegment("items"), KeyFilterSegment("a-b", 42)]
        assert build_path(segments) == "$.items[?(@['a-b']==42)]"

    def test_value_filter_string(self) -> None:
        segments = [PropertySegment("tags"), ValueFilterSegment("urgent")]
        assert build_path(segments) == "$.tags[?(@=='urgent')]"

    def test_value_filter_number(self) -> None:
        segments = [PropertySegment("scores"), ValueFilterSegment(100)]
        assert build_path(segments) == "$.scores[?(@==100)]"

    def test_deep_path_after_filter(self) -> None:
        segments = [PropertySegment("items"), KeyFilterSegment("id", 1), PropertySegment("name")]
        assert build_path(segments) == "$.items[?(@.id==1)].name"


# ===========================================================================
# Round-trip: build_path(parse_path(p)) == p for canonical paths
# ===========================================================================


CANONICAL_PATHS = [
    "$",
    "$.name",
    "$.user.name",
    "$.user.address.city",
    "$['a.b']",
    "$['O''Brien']",
    "$.items[0]",
    "$.items[42]",
    "$.items[?(@.id==42)]",
    "$.items[?(@.id=='abc')]",
    "$.items[?(@.active==true)]",
    "$.items[?(@.status==null)]",
    "$.tags[?(@=='urgent')]",
    "$.scores[?(@==100)]",
    "$.items[?(@.id==1)].name",
    "$.items[?(@.id==1)].address.city",
    "$.users[?(@.id==1)].contacts[0].email",
    "$.items[?(@.positionNumber.value==42)]",
    "$.items[?(@['literal.key']==42)]",
]


@pytest.mark.parametrize("path", CANONICAL_PATHS)
def test_round_trip_canonical(path: str) -> None:
    """build_path(parse_path(canonical_path)) == canonical_path."""
    segments = parse_path(path)
    rebuilt = build_path(segments)
    assert rebuilt == path, f"Round-trip failed: {path!r} → {segments} → {rebuilt!r}"


# Non-canonical → canonical normalization
class TestNonCanonicalNormalization:
    def test_bracket_for_simple_property(self) -> None:
        """$['user']['name'] → $.user.name when built canonically."""
        segments = parse_path("$['user']['name']")
        assert build_path(segments) == "$.user.name"

    def test_bracket_for_property_that_needs_bracket(self) -> None:
        """$['a.b'] stays as $['a.b']."""
        segments = parse_path("$['a.b']")
        assert build_path(segments) == "$['a.b']"


# ---------------------------------------------------------------------------
# describe_path
# ---------------------------------------------------------------------------


class TestDescribePath:
    def test_root(self) -> None:
        assert describe_path("$") == "(root)"

    def test_single_property(self) -> None:
        assert describe_path("$.name") == "name"

    def test_nested_properties(self) -> None:
        assert describe_path("$.user.name") == "user > name"

    def test_deep_properties(self) -> None:
        assert describe_path("$.a.b.c.d") == "a > b > c > d"

    def test_array_index(self) -> None:
        assert describe_path("$.items[0].name") == "items[0] > name"

    def test_key_filter_string(self) -> None:
        assert describe_path("$.items[?(@.id=='1')].name") == "items[id='1'] > name"

    def test_key_filter_number(self) -> None:
        assert describe_path("$.items[?(@.id==42)].price") == "items[id=42] > price"

    def test_value_filter(self) -> None:
        assert describe_path("$.tags[?(@=='urgent')]") == "tags[='urgent']"

    def test_bracket_property(self) -> None:
        assert describe_path("$['a.b'].value") == "a.b > value"

    def test_nested_filters(self) -> None:
        result = describe_path("$.articles[?(@.id=='art-3')].clauses[?(@.id=='cl-1')].text")
        assert result == "articles[id='art-3'] > clauses[id='cl-1'] > text"

    def test_filter_only(self) -> None:
        assert describe_path("$.items[?(@.id==1)]") == "items[id=1]"

    def test_malformed_path_raises(self) -> None:
        with pytest.raises(PathError):
            describe_path("")


# ---------------------------------------------------------------------------
# resolve_path
# ---------------------------------------------------------------------------


class TestResolvePath:
    def test_root(self) -> None:
        assert resolve_path("$", {"x": 1}) == ""

    def test_single_property(self) -> None:
        assert resolve_path("$.name", {"name": "Alice"}) == "/name"

    def test_nested_properties(self) -> None:
        doc = {"user": {"name": "Alice"}}
        assert resolve_path("$.user.name", doc) == "/user/name"

    def test_array_index(self) -> None:
        doc = {"items": ["a", "b", "c"]}
        assert resolve_path("$.items[0]", doc) == "/items/0"

    def test_key_filter(self) -> None:
        doc = {"items": [{"id": 1, "name": "Widget"}, {"id": 2, "name": "Gadget"}]}
        assert resolve_path("$.items[?(@.id==1)].name", doc) == "/items/0/name"
        assert resolve_path("$.items[?(@.id==2)].name", doc) == "/items/1/name"

    def test_key_filter_string_key(self) -> None:
        doc = {"items": [{"id": "a"}, {"id": "b"}]}
        assert resolve_path("$.items[?(@.id=='b')]", doc) == "/items/1"

    def test_value_filter(self) -> None:
        doc = {"tags": ["urgent", "review", "draft"]}
        assert resolve_path("$.tags[?(@=='review')]", doc) == "/tags/1"

    def test_nested_filters(self) -> None:
        doc = {
            "articles": [
                {"id": "art-1", "clauses": [{"id": "cl-1", "text": "hello"}]},
                {"id": "art-2", "clauses": [{"id": "cl-2", "text": "world"}]},
            ]
        }
        assert resolve_path("$.articles[?(@.id=='art-2')].clauses[?(@.id=='cl-2')].text", doc) == "/articles/1/clauses/0/text"

    def test_json_pointer_escaping_tilde(self) -> None:
        doc = {"a~b": 1}
        assert resolve_path("$['a~b']", doc) == "/a~0b"

    def test_json_pointer_escaping_slash(self) -> None:
        doc = {"a/b": 1}
        assert resolve_path("$['a/b']", doc) == "/a~1b"

    def test_key_filter_no_match_raises(self) -> None:
        doc = {"items": [{"id": 1}]}
        with pytest.raises(PathError, match="matched zero elements"):
            resolve_path("$.items[?(@.id==99)]", doc)

    def test_value_filter_no_match_raises(self) -> None:
        doc = {"tags": ["a", "b"]}
        with pytest.raises(PathError, match="matched zero elements"):
            resolve_path("$.tags[?(@=='missing')]", doc)

    def test_key_filter_multiple_match_raises(self) -> None:
        doc = {"items": [{"id": 1}, {"id": 1}]}
        with pytest.raises(PathError, match="matched 2 elements"):
            resolve_path("$.items[?(@.id==1)]", doc)

    def test_filter_on_non_array_raises(self) -> None:
        doc = {"items": "not-an-array"}
        with pytest.raises(PathError, match="expected array"):
            resolve_path("$.items[?(@.id==1)]", doc)
