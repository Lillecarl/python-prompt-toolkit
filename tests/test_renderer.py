"""
What the renderer writes for a row: its blanks, and where it starts.

A blank at the end of a row costs nothing to draw, and the renderer
leaves it out so that a person who copies the output gets no trailing
spaces. A control that draws the screen of another program cannot take
that guess: a space the program wrote is content. `KeepWhitespace` on
the cell is how such a control says so.
"""

from __future__ import annotations

import time

from prompt_toolkit.application import application as application_module
from prompt_toolkit.application.dummy import DummyApplication
from prompt_toolkit.data_structures import Point, Size
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.layout.screen import _CHAR_CACHE, Screen
from prompt_toolkit.output import ColorDepth, DummyOutput
from prompt_toolkit.renderer import (
    Renderer,
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

    def erase_end_of_line(self) -> None:
        self.written.append("<erase>")

    def set_attributes(self, attrs, color_depth) -> None:
        self.written.append(f"<attrs {attrs.bgcolor}>")


def _run(rows_list, width, full_screen=True):
    """
    What the terminal hears for each of a run of screens, keeping the
    screens so a test can ask what the diff measured.
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
    screens = []
    for rows in rows_list:
        screen = _screen(rows, width)
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
        screens.append(screen)
        previous = screen
        previous_width = width
    return seen, screens


def test_the_diff_carries_the_widths_it_measured():
    """
    Pinning, not discriminating.

    The widths the diff measures ride on the screen for the next
    frame, so a row is walked once and not twice. Any width the carry
    returns equals a fresh scan of the same row, so no output can tell
    the carry apart from the walk -- this pins that the carry is
    filled, forwarded across a frame that changes nothing, and still
    trims when a later frame shrinks the row.
    """
    seen, screens = _run([["hello"], ["hi"], ["hi"], ["h"]], 8)

    assert screens[0].max_column_index[0] == 4
    assert screens[1].max_column_index[0] == 1
    assert screens[2].max_column_index[0] == 1
    assert screens[3].max_column_index[0] == 0

    # The frame that changes nothing writes nothing, carry or no.
    assert seen[2] == ""

    # Both shrinks trim the stale tail. The second one can only fire
    # with the width the frame before it carried: nothing walks the
    # row the third frame left behind.
    assert "<erase>" in seen[1]
    assert "<erase>" in seen[3]


def test_a_tail_erase_carries_the_background_it_erases():
    """
    A row a fill painted keeps its background to the end of the line.

    The diff used to reset before it erased, which blotted the tail
    out with the terminal's default on every row the program left
    empty -- and a judge that drops erased cells could not see the
    absence, so the pictures stayed green over a leaking screen. The
    erase carries the tail's own background now, on a row the first
    frame reaches as well as on one that shrinks, and a tail nobody
    styled erases as before.
    """
    style = Style([])
    attrs_for_style_string = _StyleStringToAttrsCache(
        style.get_attrs_for_style_str, DummyStyleTransformation()
    )
    app = DummyApplication()
    output = _FullRecorder()

    # One row of content over styled blanks, the way a fill paints
    # behind a short program line. The width the copy reached rides
    # along, shorter than what the row holds.
    first = Screen()
    for x, char in enumerate("hello"):
        first.data_buffer[0][x] = _CHAR_CACHE[char, ""]
    for x in range(5, 8):
        first.data_buffer[0][x] = _CHAR_CACHE[" ", "bg:#ff0000"]
    first.width = 10
    first.height = 1

    second = Screen()
    for x, char in enumerate("hi"):
        second.data_buffer[0][x] = _CHAR_CACHE[char, ""]
    for x in range(2, 8):
        second.data_buffer[0][x] = _CHAR_CACHE[" ", "bg:#ff0000"]
    second.width = 10
    second.height = 1
    second.max_column_index[0] = 1

    seen = []
    pos = Point(x=0, y=0)
    previous = None
    previous_width = 0
    for screen in (first, second):
        pos, _last_style = _output_screen_diff(
            app,
            output,
            screen,
            pos,
            ColorDepth.DEPTH_8_BIT,
            previous,
            None,
            False,
            True,
            attrs_for_style_string,
            _KeepABlankCellCache(attrs_for_style_string),
            Size(rows=1, columns=10),
            previous_width,
        )
        seen.append("".join(output.written))
        del output.written[:]
        previous = screen
        previous_width = 10

    # The first frame reaches a row it never drew by erasing its tail;
    # there is no earlier row to be shorter than.
    assert "<erase>" in seen[0]

    # The shrink sets the tail's background and then erases, with no
    # reset blotting it out in between. The reset the frame ends with
    # is the frame's own, past the erase.
    start = seen[1].index("<attrs ff0000>")
    end = seen[1].index("<erase>")
    assert start < end
    assert "<reset>" not in seen[1][start:end]


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


def test_a_frame_asked_for_before_input_is_skipped():
    """
    A redraw is scheduled, and input arrives before it runs: the frame
    it would draw predates the input, so drawing it first would only
    delay what the input changes. The render asks for another frame
    instead, which the input's own handling brings, and the committed
    screen stays what the last painted frame left.
    """
    output = _FullRecorder()
    renderer = Renderer(Style([]), output)
    app = DummyApplication()
    invalidated = []
    app.invalidate = lambda: invalidated.append(True)

    app.layout = Layout(Window(FormattedTextControl("hi")))
    app.should_skip_render = lambda: False
    renderer.render(app, app.layout)
    assert "hi" in "".join(output.written)
    del output.written[:]

    # Input arrived after this frame was scheduled: nothing goes out,
    # and another frame is asked for instead.
    app.layout = Layout(Window(FormattedTextControl("yo")))
    app.should_skip_render = lambda: True
    renderer.render(app, app.layout)
    assert output.written == []
    assert invalidated == [True]

    # The input handled, the same content draws against the screen
    # the skip left committed: the frame was skipped, not painted.
    app.should_skip_render = lambda: False
    renderer.render(app, app.layout)
    assert "yo" in "".join(output.written)


class _RecordingLoop:
    "A loop that keeps scheduled callbacks instead of running them."

    def __init__(self) -> None:
        self.calls = []

    def call_soon_threadsafe(self, callback, *args, **kwargs):
        self.calls.append((callback, kwargs))

    def is_closed(self):
        return False


def _invalidate_at_cap(app, monkeypatch):
    """
    What `invalidate` asks the postpone wrapper for, on a running app
    whose last redraw was just now and whose rate cap says to wait a
    minute. The sleep path never reaches the wrapper: it goes to the
    loop itself.
    """
    scheduled = []

    def record(*args, **kwargs):
        scheduled.append((args, kwargs))

    monkeypatch.setattr(application_module, "call_soon_threadsafe", record)
    app._is_running = True
    app.min_redraw_interval = 60.0
    app._last_redraw_time = time.time()
    app.loop = _RecordingLoop()
    app.invalidate()
    return scheduled


# ----------------------------------------------------------------------
# Scroll sequences for shifted rows.


class _ScrollRecorder(_FullRecorder):
    "An output that hears raw sequences too, and scrolls regions."

    scroll_regions_support = True

    def write_raw(self, data: str) -> None:
        self.written.append(f"<raw {data}>")


class _NoScrollRecorder(_ScrollRecorder):
    "The same ear, on a terminal that scrolls nothing."

    scroll_regions_support = False


def _scroll_frames(previous_rows, new_rows, width, regions, output=None):
    """
    What the terminal hears painting one screen and diffing a scrolled
    one, as one entry per output call. The new screen carries the
    scrolled regions, the way the copy records them.
    """
    style = Style([])
    attrs_for_style_string = _StyleStringToAttrsCache(
        style.get_attrs_for_style_str, DummyStyleTransformation()
    )
    app = DummyApplication()
    output = output or _ScrollRecorder()
    pos = Point(x=0, y=0)
    previous = None
    previous_width = 0

    seen = []
    for rows in (previous_rows, new_rows):
        screen = _screen(rows, width)
        if rows is new_rows and regions is not None:
            screen.scroll_regions = regions
        pos, _last_style = _output_screen_diff(
            app,
            output,
            screen,
            pos,
            ColorDepth.DEPTH_8_BIT,
            previous,
            None,
            False,
            True,
            attrs_for_style_string,
            _KeepABlankCellCache(attrs_for_style_string),
            Size(rows=len(rows), columns=width),
            previous_width,
        )
        seen.append(list(output.written))
        del output.written[:]
        previous = screen
        previous_width = width
    return seen, previous


def test_a_scrolled_region_goes_out_as_a_scroll():
    """
    Rows shifted up by one go out as one region set-up and one scroll,
    and only the uncovered row repaints. Lillecarl/pymux#518.
    """
    previous = [f"row{number}....." for number in range(8)]
    new = [previous[0]] + previous[2:7] + ["new......."]
    _first, second = _scroll_frames(previous, new, 10, [(1, 6, 1)])[0]

    assert "".join(second) == (
        "<hide><reset>\r\n<forward 0><raw \x1b[2;7r><raw \x1b[S><raw \x1b[r>"
        "<reset>\r\n\r\n\r\n\r\n\r\n\r\n<forward 0><attrs >new......\r<forward 9>."
        "<up 6>\r<forward 0><reset><show>"
    )


def test_a_scrolled_region_down_goes_out_as_SD():
    previous = [f"row{number}....." for number in range(8)]
    new = [previous[0]] + ["new......."] + previous[1:6] + [previous[7]]
    _first, second = _scroll_frames(previous, new, 10, [(1, 6, -1)])[0]

    assert "".join(second) == (
        "<hide><reset>\r\n<forward 0><raw \x1b[2;7r><raw \x1b[T><raw \x1b[r>"
        "<reset>\r\n<forward 0><attrs >new......\r<forward 9>."
        "<up 1>\r<forward 0><reset><show>"
    )


def test_a_whole_screen_scroll_sets_no_region():
    """
    The whole screen scrolls with a bare SU: there is no region to set
    and none to give back.
    """
    previous = [f"row{number}....." for number in range(8)]
    new = previous[1:] + ["new......."]
    _first, second = _scroll_frames(previous, new, 10, [(0, 7, 1)])[0]

    assert "".join(second) == (
        "<hide><raw \x1b[S><reset>\r\n\r\n\r\n\r\n\r\n\r\n\r\n<forward 0>"
        "<attrs >new......\r<forward 9>.<up 7>\r<forward 0><reset><show>"
    )


def test_damage_inside_the_region_repaints():
    """
    A shifted row that changed beyond shifting proves nothing, so the
    region stays a repaint: no scroll sequence goes out at all.
    """
    previous = [f"row{number}....." for number in range(8)]
    new = [previous[0]] + previous[2:7] + ["new......."]
    new[4] = "EDITED...."
    _first, second = _scroll_frames(previous, new, 10, [(1, 6, 1)])[0]

    joined = "".join(second)
    assert "<raw " not in joined
    assert "EDITED" in joined


def test_escapes_inside_the_region_repaint():
    """
    An injected escape is terminal state, not a cell, so scrolling
    would leave it behind. The region repaints instead.
    """
    previous = [f"row{number}....." for number in range(8)]
    new = [previous[0]] + previous[2:7] + ["new......."]

    style = Style([])
    attrs_for_style_string = _StyleStringToAttrsCache(
        style.get_attrs_for_style_str, DummyStyleTransformation()
    )
    app = DummyApplication()
    output = _ScrollRecorder()
    pos = Point(x=0, y=0)
    previous_screen = None
    previous_width = 0

    seen = []
    for rows in (previous, new):
        screen = _screen(rows, 10)
        if rows is new:
            screen.scroll_regions = [(1, 6, 1)]
            screen.zero_width_escapes[3][0] = "\x1b]8;;http://x\x1b\\"
        pos, _last_style = _output_screen_diff(
            app,
            output,
            screen,
            pos,
            ColorDepth.DEPTH_8_BIT,
            previous_screen,
            None,
            False,
            True,
            attrs_for_style_string,
            _KeepABlankCellCache(attrs_for_style_string),
            Size(rows=len(rows), columns=10),
            previous_width,
        )
        seen.append("".join(output.written))
        del output.written[:]
        previous_screen = screen
        previous_width = 10

    assert "<raw " not in seen[1]


def test_an_output_without_scroll_support_repaints():
    """
    A console that draws through an API instead of escapes cannot move
    a region, so the scroll stays a repaint there.
    """
    previous = [f"row{number}....." for number in range(8)]
    new = [previous[0]] + previous[2:7] + ["new......."]
    _first, second = _scroll_frames(
        previous, new, 10, [(1, 6, 1)], _NoScrollRecorder()
    )[0]

    assert "<raw " not in "".join(second)
    assert "new." in "".join(second)


def test_stacked_regions_scroll_each_and_reset_each():
    """
    Two panes scrolling opposite ways: one set-up, one scroll and one
    give-back per region. The give-back is per region and not per
    frame: a move below walks through set margins, and every linefeed
    at the bottom margin would scroll them again.
    """
    previous = [f"row{number}....." for number in range(10)]
    new = [
        previous[0],
        previous[2],
        previous[3],
        previous[4],
        "fresh one.",
        previous[5],
        "fresh two.",
        previous[6],
        previous[7],
        previous[9],
    ]
    _first, second = _scroll_frames(previous, new, 10, [(1, 4, 1), (6, 8, -1)])[0]

    joined = "".join(second)
    assert joined.count("<raw \x1b[") == 6
    assert "<raw \x1b[S>" in joined
    assert "<raw \x1b[T>" in joined
    assert joined.count("<raw \x1b[r>") == 2


def test_a_half_width_scroll_stays_a_repaint():
    """
    A pane beside another scrolls a rectangle, and a scroll sequence
    moves whole rows: the region never proves, so no sequence goes out
    and the rows repaint as before. Rectangles would need column
    margins too, which is not this issue.
    """
    width = 20
    left = [f"L{n:02d}......" for n in range(6)]
    right = [f"R{n:02d}......" for n in range(6)]
    previous = [l + r for l, r in zip(left, right)]
    new = [l + r for l, r in zip(left[1:] + ["Lnew....."], right)]
    _first, second = _scroll_frames(previous, new, width, [(0, 5, 1)])[0]

    joined = "".join(second)
    assert "<raw " not in joined
    assert "new" in joined


def test_a_frame_after_a_scroll_writes_nothing():
    """
    The committed rows followed the terminal: shifted rows moved and
    uncovered rows were adopted as painted, so a frame with no changes
    finds everything and writes nothing.
    """
    previous = [f"row{number}....." for number in range(8)]
    new = [previous[0]] + previous[2:7] + ["new......."]

    style = Style([])
    attrs_for_style_string = _StyleStringToAttrsCache(
        style.get_attrs_for_style_str, DummyStyleTransformation()
    )
    app = DummyApplication()
    output = _ScrollRecorder()
    pos = Point(x=0, y=0)
    committed = None
    previous_width = 0

    screens = []
    for rows in (previous, new):
        screen = _screen(rows, 10)
        if rows is new:
            screen.scroll_regions = [(1, 6, 1)]
        pos, _last_style = _output_screen_diff(
            app,
            output,
            screen,
            pos,
            ColorDepth.DEPTH_8_BIT,
            committed,
            None,
            False,
            True,
            attrs_for_style_string,
            _KeepABlankCellCache(attrs_for_style_string),
            Size(rows=len(rows), columns=10),
            previous_width,
        )
        del output.written[:]
        screens.append(screen)
        committed = screen
        previous_width = 10

    pos, _last_style = _output_screen_diff(
        app,
        output,
        screens[1],
        pos,
        ColorDepth.DEPTH_8_BIT,
        screens[0],
        None,
        False,
        True,
        attrs_for_style_string,
        _KeepABlankCellCache(attrs_for_style_string),
        Size(rows=len(new), columns=10),
        previous_width,
    )
    assert "".join(output.written) == ""


# ----------------------------------------------------------------------
# One write per span, and no move a gap does not pay for.


def _two_frames(previous_rows, new_rows, width):
    """
    What the terminal hears painting one screen and diffing the next,
    as one entry per output call so a test can count the moves and
    the writes separately.
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
    for rows in (previous_rows, new_rows):
        screen = _screen(rows, width)
        pos, _last_style = _output_screen_diff(
            app,
            output,
            screen,
            pos,
            ColorDepth.DEPTH_8_BIT,
            previous,
            None,
            False,
            True,
            attrs_for_style_string,
            _KeepABlankCellCache(attrs_for_style_string),
            Size(rows=len(rows), columns=width),
            previous_width,
        )
        seen.append(list(output.written))
        del output.written[:]
        previous = screen
        previous_width = width
    return seen


def test_a_small_gap_is_written_through():
    """
    Two changed cells with two unchanged columns of the same style
    between them go out in one move and one write.

    The gap costs two characters written; the move across it would
    cost four (`\\x1b[3C`). The cells it holds are unchanged, so
    writing what the row holds says what the terminal shows.
    Lillecarl/pymux#522.
    """
    _first, second = _two_frames(["........"], [".X..Y..."], 8)

    assert "".join(second) == "<hide><forward 1><attrs >X..Y<backward 5><reset><show>"
    assert second.count("<forward 1>") == 1
    assert "X..Y" in second


def test_a_gap_that_costs_more_keeps_its_move():
    """
    Five unchanged columns cost five characters written; the move
    across (`\\x1b[5C`) costs four. The islands keep a move each.
    """
    _first, second = _two_frames(["........"], [".X.....Y"], 8)

    assert (
        "".join(second)
        == "<hide><forward 1><attrs >X<forward 5>Y\r<forward 0><reset><show>"
    )


def test_a_gap_tied_with_its_move_is_written_through():
    """
    Four columns against a four-byte move (`\\x1b[4C`): the tie goes
    to the content, which also spares the terminal an escape to
    parse.
    """
    _first, second = _two_frames([".........."], [".X....Y..."], 10)

    assert "".join(second) == "<hide><forward 1><attrs >X....Y<backward 7><reset><show>"
    assert "X....Y" in second


def test_adjacent_changes_arrive_in_one_write():
    """
    One move opens the span and one write carries it: three cells of
    one style are one `write`, not three.
    """
    _first, second = _two_frames(["........"], ["..XYZ..."], 8)

    assert "".join(second) == "<hide><forward 2><attrs >XYZ<backward 5><reset><show>"
    assert "XYZ" in second


def test_a_styled_gap_keeps_its_move():
    """
    A gap in another style is not written through: that would owe a
    switch to it and a switch back, dearer than the move, and the
    islands on either side draw in the running style with no switch
    of their own.
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

    green = [("a", "bg:#00ff00")] * 8
    islands = list(green)
    islands[1] = ("X", "")
    islands[4] = ("Y", "")

    seen = []
    for cells in (green, islands):
        screen = Screen()
        for x, (char, cell_style) in enumerate(cells):
            screen.data_buffer[0][x] = _CHAR_CACHE[char, cell_style]
        screen.width = 8
        screen.height = 1
        pos, _last_style = _output_screen_diff(
            app,
            output,
            screen,
            pos,
            ColorDepth.DEPTH_8_BIT,
            previous,
            None,
            False,
            True,
            attrs_for_style_string,
            _KeepABlankCellCache(attrs_for_style_string),
            Size(rows=1, columns=8),
            previous_width,
        )
        seen.append("".join(output.written))
        del output.written[:]
        previous = screen
        previous_width = 8

    assert seen[1] == "<hide><forward 1><attrs >X<forward 2>Y<backward 5><reset><show>"


def test_a_capped_redraw_waits_out_the_rate(monkeypatch):
    """
    A redraw that arrives inside the rate cap is held, not dropped:
    it sleeps out the interval and then draws.
    """
    app = DummyApplication()
    app._urgent_until = 0.0
    assert _invalidate_at_cap(app, monkeypatch) == []


def test_an_urgent_redraw_skips_the_rate_cap(monkeypatch):
    """
    A redraw that answers input goes now, past the postpone and past
    the rate cap alike: a flood paces itself against the cap either
    way, and only what answers a person waits for nothing.
    Lillecarl/pymux#507.
    """
    app = DummyApplication()
    app._urgent_until = time.time() + 100.0
    [(args, kwargs)] = _invalidate_at_cap(app, monkeypatch)
    (callback,) = args
    assert getattr(callback, "__name__", "") == "redraw"
    assert kwargs["max_postpone_time"] is None
