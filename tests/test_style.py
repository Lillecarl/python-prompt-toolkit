from __future__ import annotations

import pytest

from prompt_toolkit.output.color_depth import ColorDepth
from prompt_toolkit.output.vt100 import _EscapeCodeCache
from prompt_toolkit.styles import (
    Attrs,
    Style,
    SwapLightAndDarkStyleTransformation,
    parse_color,
)


def test_style_from_dict():
    style = Style.from_dict(
        {
            "a": "#ff0000 bold underline strike italic",
            "b": "bg:#00ff00 blink reverse",
        }
    )

    # Lookup of class:a.
    expected = Attrs(
        color="ff0000",
        bgcolor="",
        bold=True,
        underline=True,
        strike=True,
        italic=True,
        blink=False,
        reverse=False,
        hidden=False,
        dim=False,
    )
    assert style.get_attrs_for_style_str("class:a") == expected

    # Lookup of class:b.
    expected = Attrs(
        color="",
        bgcolor="00ff00",
        bold=False,
        underline=False,
        strike=False,
        italic=False,
        blink=True,
        reverse=True,
        hidden=False,
        dim=False,
    )
    assert style.get_attrs_for_style_str("class:b") == expected

    # Test inline style.
    expected = Attrs(
        color="ff0000",
        bgcolor="",
        bold=False,
        underline=False,
        strike=False,
        italic=False,
        blink=False,
        reverse=False,
        hidden=False,
        dim=False,
    )
    assert style.get_attrs_for_style_str("#ff0000") == expected

    # Combine class name and inline style (Whatever is defined later gets priority.)
    expected = Attrs(
        color="00ff00",
        bgcolor="",
        bold=True,
        underline=True,
        strike=True,
        italic=True,
        blink=False,
        reverse=False,
        hidden=False,
        dim=False,
    )
    assert style.get_attrs_for_style_str("class:a #00ff00") == expected

    expected = Attrs(
        color="ff0000",
        bgcolor="",
        bold=True,
        underline=True,
        strike=True,
        italic=True,
        blink=False,
        reverse=False,
        hidden=False,
        dim=False,
    )
    assert style.get_attrs_for_style_str("#00ff00 class:a") == expected


def test_class_combinations_1():
    # In this case, our style has both class 'a' and 'b'.
    # Given that the style for 'a b' is defined at the end, that one is used.
    style = Style(
        [
            ("a", "#0000ff"),
            ("b", "#00ff00"),
            ("a b", "#ff0000"),
        ]
    )
    expected = Attrs(
        color="ff0000",
        bgcolor="",
        bold=False,
        underline=False,
        strike=False,
        italic=False,
        blink=False,
        reverse=False,
        hidden=False,
        dim=False,
    )
    assert style.get_attrs_for_style_str("class:a class:b") == expected
    assert style.get_attrs_for_style_str("class:a,b") == expected
    assert style.get_attrs_for_style_str("class:a,b,c") == expected

    # Changing the order shouldn't matter.
    assert style.get_attrs_for_style_str("class:b class:a") == expected
    assert style.get_attrs_for_style_str("class:b,a") == expected


def test_class_combinations_2():
    # In this case, our style has both class 'a' and 'b'.
    # The style that is defined the latest get priority.
    style = Style(
        [
            ("a b", "#ff0000"),
            ("b", "#00ff00"),
            ("a", "#0000ff"),
        ]
    )
    expected = Attrs(
        color="00ff00",
        bgcolor="",
        bold=False,
        underline=False,
        strike=False,
        italic=False,
        blink=False,
        reverse=False,
        hidden=False,
        dim=False,
    )
    assert style.get_attrs_for_style_str("class:a class:b") == expected
    assert style.get_attrs_for_style_str("class:a,b") == expected
    assert style.get_attrs_for_style_str("class:a,b,c") == expected

    # Defining 'a' latest should give priority to 'a'.
    expected = Attrs(
        color="0000ff",
        bgcolor="",
        bold=False,
        underline=False,
        strike=False,
        italic=False,
        blink=False,
        reverse=False,
        hidden=False,
        dim=False,
    )
    assert style.get_attrs_for_style_str("class:b class:a") == expected
    assert style.get_attrs_for_style_str("class:b,a") == expected


def test_substyles():
    style = Style(
        [
            ("a.b", "#ff0000 bold"),
            ("a", "#0000ff"),
            ("b", "#00ff00"),
            ("b.c", "#0000ff italic"),
        ]
    )

    # Starting with a.*
    expected = Attrs(
        color="0000ff",
        bgcolor="",
        bold=False,
        underline=False,
        strike=False,
        italic=False,
        blink=False,
        reverse=False,
        hidden=False,
        dim=False,
    )
    assert style.get_attrs_for_style_str("class:a") == expected

    expected = Attrs(
        color="ff0000",
        bgcolor="",
        bold=True,
        underline=False,
        strike=False,
        italic=False,
        blink=False,
        reverse=False,
        hidden=False,
        dim=False,
    )
    assert style.get_attrs_for_style_str("class:a.b") == expected
    assert style.get_attrs_for_style_str("class:a.b.c") == expected

    # Starting with b.*
    expected = Attrs(
        color="00ff00",
        bgcolor="",
        bold=False,
        underline=False,
        strike=False,
        italic=False,
        blink=False,
        reverse=False,
        hidden=False,
        dim=False,
    )
    assert style.get_attrs_for_style_str("class:b") == expected
    assert style.get_attrs_for_style_str("class:b.a") == expected

    expected = Attrs(
        color="0000ff",
        bgcolor="",
        bold=False,
        underline=False,
        strike=False,
        italic=True,
        blink=False,
        reverse=False,
        hidden=False,
        dim=False,
    )
    assert style.get_attrs_for_style_str("class:b.c") == expected
    assert style.get_attrs_for_style_str("class:b.c.d") == expected


def test_swap_light_and_dark_style_transformation():
    transformation = SwapLightAndDarkStyleTransformation()

    # Test with 6 digit hex colors.
    before = Attrs(
        color="440000",
        bgcolor="888844",
        bold=True,
        underline=True,
        strike=True,
        italic=True,
        blink=False,
        reverse=False,
        hidden=False,
        dim=False,
    )
    after = Attrs(
        color="ffbbbb",
        bgcolor="bbbb76",
        bold=True,
        underline=True,
        strike=True,
        italic=True,
        blink=False,
        reverse=False,
        hidden=False,
        dim=False,
    )

    assert transformation.transform_attrs(before) == after

    # Test with ANSI colors.
    before = Attrs(
        color="ansired",
        bgcolor="ansiblack",
        bold=True,
        underline=True,
        strike=True,
        italic=True,
        blink=False,
        reverse=False,
        hidden=False,
        dim=False,
    )
    after = Attrs(
        color="ansibrightred",
        bgcolor="ansiwhite",
        bold=True,
        underline=True,
        strike=True,
        italic=True,
        blink=False,
        reverse=False,
        hidden=False,
        dim=False,
    )

    assert transformation.transform_attrs(before) == after


def test_underline_shape_and_colour():
    style = Style.from_dict(
        {
            "a": "undercurl ul:#ff0000",
            "b": "underdouble",
            "c": "underline",
        }
    )

    attrs = style.get_attrs_for_style_str("class:a")
    assert attrs.underline is True
    assert attrs.underline_style == "curly"
    assert attrs.underline_color == "ff0000"

    attrs = style.get_attrs_for_style_str("class:b")
    assert attrs.underline is True
    assert attrs.underline_style == "double"
    assert attrs.underline_color == ""

    # "underline" says nothing about the shape, so an empty shape
    # stays empty and draws a single line.
    attrs = style.get_attrs_for_style_str("class:c")
    assert attrs.underline is True
    assert attrs.underline_style == ""


def test_underline_escape_sequences():
    cache = _EscapeCodeCache(ColorDepth.DEPTH_24_BIT)

    def code(style_str: str) -> str:
        style = Style.from_dict({"a": style_str})
        return cache[style.get_attrs_for_style_str("class:a")]

    assert code("underline") == "\x1b[0;4m"
    assert code("undercurl") == "\x1b[0;4:3m"
    assert code("underdotted ul:ansired") == "\x1b[0;4:4;58:5:1m"
    assert code("undercurl ul:#ff0000") == "\x1b[0;4:3;58:2::255:0:0m"
    # No line, so no colour of a line either.
    assert code("ul:#ff0000") == "\x1b[0m"


def test_where_a_glyph_sits():
    style = Style.from_dict(
        {
            "a": "superscript",
            "b": "subscript",
            "c": "superscript nobaseline",
        }
    )

    assert style.get_attrs_for_style_str("class:a").baseline == "superscript"
    assert style.get_attrs_for_style_str("class:b").baseline == "subscript"
    # "nobaseline" puts the glyph back on the line.
    assert style.get_attrs_for_style_str("class:c").baseline == ""


def test_the_baseline_escape_sequences():
    cache = _EscapeCodeCache(ColorDepth.DEPTH_24_BIT)

    def code(style_str: str) -> str:
        style = Style.from_dict({"a": style_str})
        return cache[style.get_attrs_for_style_str("class:a")]

    assert code("superscript") == "\x1b[0;73m"
    assert code("subscript") == "\x1b[0;74m"
    assert code("bold superscript") == "\x1b[0;1;73m"
    # The reset at the head of the sequence is the whole of "SGR 75".
    assert code("superscript nobaseline") == "\x1b[0m"


def test_a_colour_of_the_palette_keeps_its_number():
    "\"ansi234\" is the number 234 and not the colour xterm paints for it."
    assert parse_color("ansi234") == "ansi234"
    assert parse_color("#ansi234") == "ansi234"
    assert parse_color("ansi255") == "ansi255"


def test_the_first_sixteen_keep_their_name():
    "One colour has one spelling, so a number under sixteen becomes a name."
    assert parse_color("ansi0") == "ansiblack"
    assert parse_color("ansi1") == "ansired"
    assert parse_color("ansi9") == "ansibrightred"
    assert parse_color("ansi15") == "ansiwhite"


def test_a_number_above_the_palette_is_not_a_colour():
    "The palette holds 256 colours, so 256 is not one of them."
    with pytest.raises(ValueError):
        parse_color("ansi256")


def test_a_style_carries_a_colour_of_the_palette():
    style = Style.from_dict({"a": "ansi234 bg:ansi16"})

    attrs = style.get_attrs_for_style_str("class:a")
    assert attrs.color == "ansi234"
    assert attrs.bgcolor == "ansi16"


def test_a_palette_colour_reaches_the_wire_as_a_number():
    """
    A number of the palette travels as a number, at every depth that
    can carry one. The terminal of the user paints it from its theme.
    """

    def code(style_str: str, depth: ColorDepth) -> str:
        style = Style.from_dict({"a": style_str})
        return _EscapeCodeCache(depth)[style.get_attrs_for_style_str("class:a")]

    assert code("ansi234", ColorDepth.DEPTH_24_BIT) == "\x1b[0;38;5;234m"
    assert code("ansi234", ColorDepth.DEPTH_8_BIT) == "\x1b[0;38;5;234m"
    assert code("bg:ansi234", ColorDepth.DEPTH_24_BIT) == "\x1b[0;48;5;234m"
    assert code("underline ul:ansi234", ColorDepth.DEPTH_24_BIT) == "\x1b[0;4;58:5:234m"


def test_four_bits_paint_the_closest_of_the_sixteen():
    """
    A terminal of four bits cannot take the number, so the colour that
    xterm paints for it becomes one of the sixteen. Colour 234 is a
    dark grey, and the closest of the sixteen is black.
    """
    style = Style.from_dict({"a": "ansi234"})
    cache = _EscapeCodeCache(ColorDepth.DEPTH_4_BIT)
    assert cache[style.get_attrs_for_style_str("class:a")] == "\x1b[0;30m"
