"""
What the renderer writes for a row: its blanks, and how big it is.

A blank at the end of a row costs nothing to draw, and the renderer
leaves it out so that a person who copies the output gets no trailing
spaces. A control that draws the screen of another program cannot take
that guess: a space the program wrote is content. `KeepWhitespace` on
the cell is how such a control says so.

The second half is the DEC line attributes. Those belong to the row and
not to a cell, so the renderer diffs them against the previous screen on
its own. A row can take one while every cell stays as it was, and it can
give one back the same way.
"""
from __future__ import annotations

import io

from prompt_toolkit.application.dummy import DummyApplication
from prompt_toolkit.data_structures import Point, Size
from prompt_toolkit.layout.screen import Screen, _CHAR_CACHE
from prompt_toolkit.line_attributes import LineAttribute
from prompt_toolkit.output import ColorDepth, DummyOutput
from prompt_toolkit.output.vt100 import Vt100_Output
from prompt_toolkit.renderer import (
    _KeepABlankCellCache,
    _StyleStringToAttrsCache,
    _output_screen_diff,
)
from prompt_toolkit.styles import DummyStyleTransformation, Style
from prompt_toolkit.token import KeepWhitespace


class _Recorder(DummyOutput):
    "An output that keeps the characters and drops everything else."

    def __init__(self) -> None:
        self.written: list[str] = []

    def write(self, data: str) -> None:
        self.written.append(data)

    def set_line_attribute(self, line_attribute: LineAttribute) -> None:
        """
        Keep the name of the attribute, and not the sequence for it.

        What the renderer decides is which attribute a row takes and
        when. Which bytes carry it is the business of `Vt100_Output`,
        and `test_the_sequences_of_the_line_attributes` reads those.
        """
        self.written.append("<%s>" % line_attribute.value)


def render(row):
    """
    The characters that one row of (character, style) pairs writes.

    Only `write` is recorded, so a cursor move and an erase leave
    nothing behind. That is the question here: does the last blank of
    the row reach the terminal at all?

    The screen is wider than the row. A cursor that stands on the last
    column goes back with a carriage return, and that one is a `write`.
    """
    width = len(row) + 4
    screen = Screen()
    for column, (char, style) in enumerate(row):
        screen.data_buffer[0][column] = _CHAR_CACHE[char, style]
    screen.width = width
    screen.height = 1

    output = _Recorder()
    style = Style([])
    attrs_for_style_string = _StyleStringToAttrsCache(
        style.get_attrs_for_style_str, DummyStyleTransformation()
    )
    _output_screen_diff(
        DummyApplication(),
        output,
        screen,
        Point(x=0, y=0),
        ColorDepth.DEPTH_8_BIT,
        None,
        None,
        False,
        False,
        attrs_for_style_string,
        _KeepABlankCellCache(attrs_for_style_string),
        Size(rows=1, columns=width),
        0,
    )
    return "".join(output.written)


def test_a_blank_at_the_end_of_a_row_is_left_out():
    assert render([("a", ""), (" ", "")]) == "a"


def test_a_blank_that_asks_to_stay_is_written():
    assert render([("a", ""), (" ", KeepWhitespace)]) == "a "


def test_a_styled_blank_is_written_as_it_always_was():
    "A background colour has to reach the terminal, token or no token."
    assert render([("a", ""), (" ", "bg:#ff0000")]) == "a "


def test_the_token_keeps_only_the_cell_that_carries_it():
    "The blank after it is still the end of the row, and still goes."
    assert render([("a", ""), (" ", KeepWhitespace), (" ", "")]) == "a "


def test_a_row_of_blanks_that_ask_to_stay_is_written_whole():
    assert render([(" ", KeepWhitespace)] * 3) == "   "


# ----------------------------------------------------------------------
# The DEC line attributes.


def _screen(rows, attributes, width):
    "One screen: the text of each row, and how each row is drawn."
    screen = Screen()
    for y, text in enumerate(rows):
        for x, char in enumerate(text):
            screen.data_buffer[y][x] = _CHAR_CACHE[char, ""]
    screen.line_attributes = dict(attributes)
    screen.width = width
    screen.height = len(rows)
    return screen


def frames(screens, width=8):
    """
    What the terminal sees for a run of screens, one string per frame.

    The first frame is drawn against nothing, which is what a renderer
    does when it starts. Every frame after it is a diff against the one
    before, and that is where a line attribute has to be found.
    """
    style = Style([])
    attrs_for_style_string = _StyleStringToAttrsCache(
        style.get_attrs_for_style_str, DummyStyleTransformation()
    )

    seen = []
    previous = None
    for rows, attributes in screens:
        screen = _screen(rows, attributes, width)
        output = _Recorder()
        _output_screen_diff(
            DummyApplication(),
            output,
            screen,
            Point(x=0, y=0),
            ColorDepth.DEPTH_8_BIT,
            previous,
            None,
            False,
            False,
            attrs_for_style_string,
            _KeepABlankCellCache(attrs_for_style_string),
            Size(rows=len(rows), columns=width),
            width if previous else 0,
        )
        seen.append("".join(output.written))
        previous = screen
    return seen


def test_a_row_that_asks_for_double_width_says_so_before_its_cells():
    "The line takes the attribute, and then the cells go on it."
    assert frames(
        [(["abcde"], {0: LineAttribute.DOUBLE_WIDTH})]
    ) == ["<double-width>abcde"]


def test_a_row_that_asks_for_nothing_says_nothing():
    assert frames([(["abcde"], {})]) == ["abcde"]


def test_a_row_takes_an_attribute_while_its_cells_stay():
    """
    The late change: the text lands first and the attribute after it.

    No cell differs between the two frames, so a diff of the cells
    alone writes nothing. The row still has to say how big it is now,
    and it writes its cells again: a line drawn twice as wide shows
    half its columns, and a terminal may keep the other half or drop
    it.
    """
    assert frames(
        [
            (["abcde"], {}),
            (["abcde"], {0: LineAttribute.DOUBLE_WIDTH}),
        ]
    ) == ["abcde", "<double-width>abcde"]


def test_a_row_gives_the_attribute_back():
    """
    The other direction, which only the renderer can see.

    A control says what a row is now. It does not say what the row was,
    so nothing but the previous screen knows that the terminal is still
    drawing this line twice as wide.
    """
    assert frames(
        [
            (["abcde"], {0: LineAttribute.DOUBLE_WIDTH}),
            (["abcde"], {}),
        ]
    ) == ["<double-width>abcde", "<single>abcde"]


def test_a_row_that_keeps_its_attribute_writes_nothing_again():
    assert frames(
        [
            (["abcde"], {0: LineAttribute.DOUBLE_WIDTH}),
            (["abcde"], {0: LineAttribute.DOUBLE_WIDTH}),
        ]
    ) == ["<double-width>abcde", ""]


def test_the_two_halves_of_a_double_height_line():
    "A program writes the same text twice, and the halves differ."
    assert frames(
        [
            (
                ["abcde", "abcde"],
                {
                    0: LineAttribute.DOUBLE_HEIGHT_TOP,
                    1: LineAttribute.DOUBLE_HEIGHT_BOTTOM,
                },
            )
        ]
    ) == ["<double-height-top>abcde\r\n<double-height-bottom>abcde"]


def test_the_sequences_of_the_line_attributes():
    "What `Vt100_Output` writes for each of the four."
    output = Vt100_Output(
        stdout=io.StringIO(), get_size=lambda: Size(rows=1, columns=1)
    )
    for attribute in LineAttribute:
        output.set_line_attribute(attribute)
    assert output._buffer == ["\x1b#5", "\x1b#6", "\x1b#3", "\x1b#4"]
