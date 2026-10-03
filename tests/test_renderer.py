"""
What the renderer writes for a row: its blanks, and where it starts.

A blank at the end of a row costs nothing to draw, and the renderer
leaves it out so that a person who copies the output gets no trailing
spaces. A control that draws the screen of another program cannot take
that guess: a space the program wrote is content. `KeepWhitespace` on
the cell is how such a control says so.
"""
from __future__ import annotations

from prompt_toolkit.application.dummy import DummyApplication
from prompt_toolkit.data_structures import Point, Size
from prompt_toolkit.layout.screen import _CHAR_CACHE, Screen
from prompt_toolkit.output import ColorDepth, DummyOutput
from prompt_toolkit.renderer import (
    _KeepABlankCellCache,
    _output_screen_diff,
    _StyleStringToAttrsCache,
)
from prompt_toolkit.styles import DummyStyleTransformation, Style
from prompt_toolkit.token import KeepWhitespace


class _Recorder(DummyOutput):
    "An output that keeps the characters and drops everything else."

    def __init__(self) -> None:
        self.written: list[str] = []

    def write(self, data: str) -> None:
        self.written.append(data)

    def cursor_goto(self, row: int = 0, column: int = 0) -> None:
        "An absolute move, which a relative one can never be confused with."
        self.written.append(f"<goto {row},{column}>")


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
            _KeepABlankCellCache(attrs_for_style_string),
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
    assert (
        "<goto" not in frames([(["AAAAAAAAAA", "AA"], 10), (["AAAAAAAAAAAA"], 15)])[1]
    )


# ----------------------------------------------------------------------
# A frame that changes nothing writes nothing.


class _FullRecorder(_Recorder):
    "An output that hears the frame around the painting too."

    def __init__(self) -> None:
        super().__init__()
        self._visible: bool | None = None

    def hide_cursor(self) -> None:
        # Like the real output, which does not repeat an answer it gave.
        if self._visible in (True, None):
            self._visible = False
            self.written.append("<hide>")

    def show_cursor(self) -> None:
        if self._visible in (False, None):
            self._visible = True
            self.written.append("<show>")

    def reset_attributes(self) -> None:
        self.written.append("<reset>")

    def enable_autowrap(self) -> None:
        self.written.append("<autowrap on>")

    def disable_autowrap(self) -> None:
        self.written.append("<autowrap off>")

    def cursor_forward(self, amount: int) -> None:
        self.written.append(f"<forward {amount}>")

    def cursor_backward(self, amount: int) -> None:
        self.written.append(f"<backward {amount}>")

    def cursor_up(self, amount: int) -> None:
        self.written.append(f"<up {amount}>")


def _twice(rows, width, cursor=None, full_screen=True):
    """
    What the terminal hears for two frames that paint the same screen.

    One output hears both, the way one terminal does, and the cursor
    the second frame leaves behind is the one the first one placed.
    """
    style = Style([])
    attrs_for_style_string = _StyleStringToAttrsCache(
        style.get_attrs_for_style_str, DummyStyleTransformation()
    )
    app = DummyApplication()
    output = _FullRecorder()
    pos = Point(x=0, y=0)
    previous = None
    previous_width = 0

    seen = []
    for _ in range(2):
        screen = _screen(rows, width)
        if cursor is not None:
            screen.set_cursor_position(app.layout.current_window, cursor)
        pos, _last_style = _output_screen_diff(
            app,
            output,
            screen,
            pos,
            ColorDepth.DEPTH_8_BIT,
            previous,
            None,
            False,
            full_screen,
            attrs_for_style_string,
            _KeepABlankCellCache(attrs_for_style_string),
            Size(rows=len(rows), columns=width),
            previous_width,
        )
        seen.append("".join(output.written))
        del output.written[:]
        previous = screen
        previous_width = width
    return seen


def test_a_frame_that_changes_nothing_writes_nothing():
    """
    An application renders whenever something may have changed, and most
    of the time nothing has. The frame around the painting used to go
    out anyway -- hide the cursor, reset the attributes, show the
    cursor -- so such an application chattered constantly. The head of
    a frame waits for the first change now, and a frame with no changes
    says nothing at all.
    """
    first, second = _twice(["hello"], 8)

    assert first
    assert second == ""


def test_a_cursor_on_the_last_column_is_not_called_back():
    """
    `move_cursor` writes for a position it already holds when that is
    the last column -- it cannot tell whether the terminal wrapped --
    so the end of a frame asks for the move only when the screen wants
    the cursor somewhere else. A frame that changes nothing writes
    nothing even there.
    """
    first, second = _twice(["12345678"], 8, cursor=Point(x=7, y=0))

    assert first
    assert second == ""
