"""
Where a full redraw starts: the position the renderer names, and the
frames that reach the terminal around it.
"""
from __future__ import annotations

from prompt_toolkit.application.dummy import DummyApplication
from prompt_toolkit.data_structures import Point, Size
from prompt_toolkit.layout.screen import Screen, _CHAR_CACHE
from prompt_toolkit.output import ColorDepth, DummyOutput
from prompt_toolkit.renderer import (
    _StyleStringHasStyleCache,
    _StyleStringToAttrsCache,
    _output_screen_diff,
)
from prompt_toolkit.styles import DummyStyleTransformation, Style


class _Recorder(DummyOutput):
    "An output that keeps the characters and drops everything else."

    def __init__(self) -> None:
        self.written: list[str] = []

    def write(self, data: str) -> None:
        self.written.append(data)

    def cursor_goto(self, row: int = 0, column: int = 0) -> None:
        "An absolute move, which a relative one can never be confused with."
        self.written.append("<goto %d,%d>" % (row, column))


# ----------------------------------------------------------------------
# Where a full redraw starts.


def _screen(rows, width):
    "One screen: the text of each row."
    screen = Screen()
    for y, text in enumerate(rows):
        for x, char in enumerate(text):
            screen.data_buffer[y][x] = _CHAR_CACHE[char, ""]
    screen.width = width
    screen.height = len(rows)
    return screen


def frames(screens, width=8, full_screen=False):
    """
    What the terminal sees for a run of screens, one string per frame.

    The first frame is drawn against nothing, which is what a renderer
    does when it starts. Every frame after it is a diff against the one
    before.

    A screen is `(rows,)`, or `(rows, width)` when it is a different
    size from the one before it.
    """
    style = Style([])
    attrs_for_style_string = _StyleStringToAttrsCache(
        style.get_attrs_for_style_str, DummyStyleTransformation()
    )

    seen = []
    previous = None
    previous_width = 0
    for rows, *rest in screens:
        this_width = rest[0] if rest else width
        screen = _screen(rows, this_width)
        output = _Recorder()
        _output_screen_diff(
            DummyApplication(),
            output,
            screen,
            Point(x=0, y=0),
            ColorDepth.DEPTH_8_BIT,
            None if previous_width != this_width else previous,
            None,
            False,
            full_screen,
            attrs_for_style_string,
            _StyleStringHasStyleCache(attrs_for_style_string),
            Size(rows=len(rows), columns=this_width),
            previous_width,
        )
        seen.append("".join(output.written))
        previous = screen
        previous_width = this_width
    return seen


def test_a_full_screen_redraw_says_where_the_cursor_goes():
    """
    A terminal that changes size moves the cursor itself.

    It reflows the lines it had wrapped and carries the cursor with
    them, or it clamps the cursor to the new width. Either way the
    position the last frame left is gone, so a relative move lands
    somewhere else and the erase that follows keeps a piece of the old
    screen.

    A full screen application owns the screen, so it names the position
    instead of walking to it.
    """
    assert frames(
        [(["AAAAAAAAAA", "AA"], 10), (["AAAAAAAAAAAA"], 15)],
        full_screen=True,
    )[1].startswith("<goto 0,0>")


def test_a_redraw_that_does_not_own_the_screen_still_walks():
    "The layout starts wherever the cursor stands, so it cannot say."
    assert "<goto" not in frames(
        [(["AAAAAAAAAA", "AA"], 10), (["AAAAAAAAAAAA"], 15)]
    )[1]
