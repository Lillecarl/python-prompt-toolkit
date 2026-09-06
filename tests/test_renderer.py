"""
What the renderer writes for a row that ends in blanks.

A blank at the end of a row costs nothing to draw, and the renderer
leaves it out so that a person who copies the output gets no trailing
spaces. A control that draws the screen of another program cannot take
that guess: a space the program wrote is content. `KeepWhitespace` on
the cell is how such a control says so.
"""
from __future__ import annotations

from prompt_toolkit.application.dummy import DummyApplication
from prompt_toolkit.data_structures import Point, Size
from prompt_toolkit.layout.screen import Screen, _CHAR_CACHE
from prompt_toolkit.output import ColorDepth, DummyOutput
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
