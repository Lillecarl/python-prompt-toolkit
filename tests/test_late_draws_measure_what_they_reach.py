"""
Draws past the copies measure what they reach.

The copies tell the renderer how far each row reaches, and the
renderer reads that instead of walking the cells. Anything else
that writes cells past the copies has to speak too: the area and
last-line fills, and the cursorline, cursorcolumn and colorcolumn
highlights. A row they reached but nobody measured ends early, and
the trim erases what they just drew, or never paints it at all.
"""

from __future__ import annotations

from prompt_toolkit.data_structures import Point
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.controls import UIContent, UIControl
from prompt_toolkit.layout.mouse_handlers import MouseHandlers
from prompt_toolkit.layout.screen import Screen, WritePosition

WIDTH, HEIGHT = 60, 6

#: Two columns of content on the first row, blanks below it.
ROWS = [[("", "hi")]] + [[]] * (HEIGHT - 1)


class _Short(UIControl):
    "Two columns of content on the first row, and a cursor to find."

    def __init__(self, rows: list) -> None:
        self.rows = rows

    def create_content(self, width: int, height: int) -> UIContent:
        # The cursor stands on the first cell, which the copy
        # records, so the highlights land where the test looks.
        return UIContent(
            get_line=lambda number: self.rows[number],
            line_count=len(self.rows),
            cursor_position=Point(x=0, y=0),
        )

    def is_focusable(self) -> bool:
        return False


def _draw(window: Window) -> Screen:
    "One frame of the window on a screen of its own."
    screen = Screen()
    window.write_to_screen(
        screen,
        MouseHandlers(),
        WritePosition(xpos=0, ypos=0, width=WIDTH, height=HEIGHT),
        "",
        False,
        None,
    )
    return screen


def test_an_area_style_measures_the_whole_width() -> None:
    window = Window(content=_Short(ROWS), style="bold")
    screen = _draw(window)
    assert [screen.max_column_index[y] for y in range(HEIGHT)] == [WIDTH - 1] * HEIGHT


def test_the_last_line_measures_the_whole_width() -> None:
    window = Window(content=_Short(ROWS))
    screen = _draw(window)
    assert screen.max_column_index[HEIGHT - 1] == WIDTH - 1


def test_a_cursorline_measures_the_whole_width() -> None:
    window = Window(content=_Short(ROWS), cursorline=True)
    screen = _draw(window)
    assert screen.max_column_index[0] == WIDTH - 1


def test_a_cursorcolumn_measures_its_column() -> None:
    window = Window(content=_Short(ROWS), cursorcolumn=True)
    screen = _draw(window)
    # The last row is the last-line fill's, which reaches further.
    assert [screen.max_column_index[y] for y in range(HEIGHT)] == [1, 0, 0, 0, 0, WIDTH - 1]
