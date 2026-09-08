"""
What a `ScrollablePane` puts on the screen, and what it leaves alone.

A pane shows a tall content in a short area. It draws the content where
the scroll puts it, which is above the pane when anything is scrolled
past, and it must leave every row outside itself to the containers that
own them.

The other half is what a render leaves *on* the screen besides cells:
where each window went, where the cursor is, which handler answers a
click. Those are in one coordinate space, the screen's own, so a window
that is only partly visible reports its whole size at its real place.
"""

from __future__ import annotations

from contextlib import contextmanager

from prompt_toolkit.application import Application
from prompt_toolkit.application.current import set_app
from prompt_toolkit.data_structures import Point
from prompt_toolkit.input import DummyInput
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.mouse_handlers import MouseHandlers
from prompt_toolkit.layout.screen import Char, Screen, WritePosition
from prompt_toolkit.layout.scrollable_pane import ScrollablePane
from prompt_toolkit.mouse_events import MouseButton, MouseEvent, MouseEventType
from prompt_toolkit.output import DummyOutput

WIDTH, HEIGHT = 20, 8

#: Where the pane sits in the layout below, and how tall it is. Two rows
#: above it and two below belong to other windows.
PANE_TOP, PANE_HEIGHT = 2, 4

LINES = 20


class _Line(FormattedTextControl):
    "One line of the content, which says when it is clicked."

    def __init__(self, number: int, clicked: list[int]) -> None:
        super().__init__("line %d" % number, focusable=True)
        self.number = number
        self.clicked = clicked

    def mouse_handler(self, mouse_event: MouseEvent) -> None:
        self.clicked.append(self.number)


def a_layout(lines: int = LINES, show_scrollbar: bool = False):
    """
    A pane between two other windows, holding one window per line.

    The content is taller than the pane, so most of it is off the pane
    at any time and the scroll decides which part is not.
    """
    clicked: list[int] = []
    windows = [Window(_Line(number, clicked), height=1) for number in range(lines)]
    pane = ScrollablePane(HSplit(windows), show_scrollbar=show_scrollbar)
    root = HSplit(
        [
            Window(FormattedTextControl("above"), height=PANE_TOP),
            pane,
            Window(FormattedTextControl("below"), height=2),
        ]
    )
    return root, pane, windows, clicked


@contextmanager
def an_application(container, focus):
    """
    The container in an application, so that `get_app()` answers.

    A pane asks the application which window has the focus, and scrolls
    to it. Nothing else here needs the application.
    """
    app = Application(
        layout=Layout(container, focused_element=focus),
        input=DummyInput(),
        output=DummyOutput(),
    )
    # A running application does this after every render. A window that
    # does not know its parents is its own modal area, and then it turns
    # every mouse event down.
    app.layout.update_parents_relations()

    with set_app(app):
        yield app


def draw(container) -> tuple[Screen, MouseHandlers]:
    "One frame of the container, on a screen of its own."
    screen = Screen()
    mouse_handlers = MouseHandlers()
    container.write_to_screen(
        screen,
        mouse_handlers,
        WritePosition(xpos=0, ypos=0, width=WIDTH, height=HEIGHT),
        "",
        False,
        None,
    )
    screen.draw_all_floats()
    return screen, mouse_handlers


def drawn(container, focus) -> tuple[Screen, MouseHandlers]:
    "One frame, with the focus on this window."
    with an_application(container, focus):
        return draw(container)


def cells(screen: Screen, y: int) -> str:
    """
    One row as a string.

    It reads through `get`, because reading a row of a `Screen` the
    usual way creates it, and half of these tests ask which rows exist.
    """
    row = screen.data_buffer.get(y, {})
    return "".join(row.get(x, Char()).char for x in range(WIDTH))


def a_click(container, focus, x: int, y: int) -> Screen:
    """
    Draw a frame, then click whatever is drawn at this point.

    The click happens inside the application, because a window refuses
    a mouse event that does not reach it through the layout it is in.
    """
    with an_application(container, focus):
        screen, mouse_handlers = draw(container)
        mouse_handlers.mouse_handlers[y][x](
            MouseEvent(
                position=Point(x=x, y=y),
                event_type=MouseEventType.MOUSE_UP,
                button=MouseButton.LEFT,
                modifiers=frozenset(),
            )
        )
        return screen


# ----------------------------------------------------------------------
# The pane keeps to its own rows.


def test_the_pane_draws_no_row_but_its_own():
    """
    The content is twenty rows tall and the pane is four. The rest of
    it is drawn above and below the pane, where the renderer never
    reads, and not on the rows the other two windows own.
    """
    root, _, windows, _ = a_layout()

    screen, _ = drawn(root, windows[15])

    assert cells(screen, 0).strip() == "above"
    assert cells(screen, PANE_TOP + PANE_HEIGHT).strip() == "below"
    assert set(screen.data_buffer) <= set(range(HEIGHT))


def test_the_pane_leaves_no_escape_sequence_outside_itself():
    "The second thing a render hangs on a screen, and the same rule."
    root, _, windows, _ = a_layout()

    screen, _ = drawn(root, windows[15])

    assert set(screen.zero_width_escapes) <= set(
        range(PANE_TOP, PANE_TOP + PANE_HEIGHT)
    )


def test_a_click_above_the_pane_reaches_no_line_of_it():
    """
    The third. A mouse handler is a row of callables like the cells,
    and a click on the window above the pane must not run a line's
    handler.
    """
    root, _, windows, clicked = a_layout()

    a_click(root, windows[15], x=0, y=0)

    assert clicked == []


def test_a_click_below_the_pane_reaches_no_line_of_it():
    root, _, windows, clicked = a_layout()

    a_click(root, windows[15], x=0, y=PANE_TOP + PANE_HEIGHT)

    assert clicked == []


# ----------------------------------------------------------------------
# One coordinate space.


def test_a_click_reaches_the_line_drawn_under_it():
    """
    The point of one coordinate space: the handler at a point belongs
    to the window the screen says is drawn there.
    """
    root, _, windows, clicked = a_layout()

    screen = a_click(root, windows[15], x=0, y=PANE_TOP)
    where = screen.visible_windows_to_write_positions
    under = [window for window in windows if where[window].ypos == PANE_TOP]

    assert clicked == [windows.index(under[0])]


def test_a_line_scrolled_out_of_sight_is_still_recorded_where_it_is():
    """
    The first line is above the pane, so it is recorded at a row above
    the pane's own. That answer is what a caller asking "what is beside
    this one" needs, and a position off the screen is still a position.
    """
    root, _, windows, _ = a_layout()

    screen, _ = drawn(root, windows[15])
    where = screen.visible_windows_to_write_positions

    assert where[windows[0]].ypos < PANE_TOP
    assert where[windows[1]].ypos == where[windows[0]].ypos + 1


def test_a_line_out_of_sight_reports_its_whole_size():
    "Nothing is truncated to the part that shows."
    root, _, windows, _ = a_layout()

    screen, _ = drawn(root, windows[15])
    where = screen.visible_windows_to_write_positions

    assert where[windows[0]].height == 1
    assert where[windows[0]].width == where[windows[15]].width


def test_the_lines_are_one_row_apart_from_end_to_end():
    "One space, so the whole content is a single ladder of rows."
    root, _, windows, _ = a_layout()

    screen, _ = drawn(root, windows[15])
    where = screen.visible_windows_to_write_positions
    rows = [where[window].ypos for window in windows]

    assert rows == list(range(rows[0], rows[0] + LINES))


# ----------------------------------------------------------------------
# The scroll.


def test_the_focused_line_is_inside_the_pane():
    root, _, windows, _ = a_layout()

    screen, _ = drawn(root, windows[15])
    where = screen.visible_windows_to_write_positions[windows[15]]

    assert PANE_TOP <= where.ypos < PANE_TOP + PANE_HEIGHT


def test_the_focus_is_visible_on_the_frame_it_moves():
    """
    The scroll is decided before the content is drawn, not read back
    afterwards. A pane that drew first and scrolled after would show
    the old view for one frame, which is a flicker on the very key that
    scrolls.
    """
    root, _, windows, _ = a_layout()

    with an_application(root, windows[0]) as app:
        draw(root)
        app.layout.focus(windows[19])
        screen, _ = draw(root)

    where = screen.visible_windows_to_write_positions[windows[19]]

    assert PANE_TOP <= where.ypos < PANE_TOP + PANE_HEIGHT


def test_a_pane_that_fits_its_content_does_not_scroll():
    root, pane, windows, _ = a_layout(lines=PANE_HEIGHT)

    drawn(root, windows[-1])

    assert pane.vertical_scroll == 0


# ----------------------------------------------------------------------
# The area the pane owns.


def test_the_pane_does_not_stretch_the_screen():
    """
    A window grows the height of the screen from its own write position,
    and the content of a pane is drawn past the bottom of the pane. The
    screen is as tall as the layout, never as tall as the content.

    The renderer moves the cursor up by that height when it is not
    running full screen, so a number too large writes over the terminal
    above it.
    """
    root, _, windows, _ = a_layout()

    screen, _ = drawn(root, windows[15])

    assert screen.height == HEIGHT


def test_a_pane_taller_than_its_content_still_paints_every_row():
    """
    The rows the content never reaches belong to the pane all the same.
    Leaving them out would show whatever the row behind them held.
    """
    root, _, windows, _ = a_layout(lines=1)

    screen, _ = drawn(root, windows[0])

    for y in range(PANE_TOP, PANE_TOP + PANE_HEIGHT):
        assert y in screen.data_buffer, y


def test_the_scrollbar_is_drawn_down_the_last_column():
    root, _, windows, _ = a_layout(show_scrollbar=True)

    screen, _ = drawn(root, windows[15])

    for y in range(PANE_TOP, PANE_TOP + PANE_HEIGHT):
        assert "scrollbar" in screen.data_buffer[y][WIDTH - 1].style, y


def test_the_scrollbar_takes_a_column_from_the_content():
    "The content is one narrower, so nothing is drawn under the bar."
    root, _, windows, _ = a_layout(show_scrollbar=True)

    screen, _ = drawn(root, windows[15])
    where = screen.visible_windows_to_write_positions[windows[15]]

    assert where.width == WIDTH - 1
