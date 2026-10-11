"""
A window whose control says nothing changed writes what it wrote before.

The control answers `content_version`; a window that fills its own area
and sees the same answer, with nothing of its own changed, takes the
cells of the frame before instead of asking for content and copying it.
Lillecarl/pymux#577.
"""

from __future__ import annotations

from prompt_toolkit.application import Application
from prompt_toolkit.application.current import set_app
from prompt_toolkit.data_structures import Point
from prompt_toolkit.input import DummyInput
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import _CHAR_CACHE, ScrollOffsets, Window
from prompt_toolkit.layout.controls import UIContent, UIControl
from prompt_toolkit.layout.mouse_handlers import MouseHandlers
from prompt_toolkit.layout.screen import Screen, WritePosition
from prompt_toolkit.output import DummyOutput

WIDTH, HEIGHT = 12, 3
POSITION = WritePosition(xpos=2, ypos=1, width=WIDTH, height=HEIGHT)


class _Versioned(UIControl):
    "A control that counts its versions, and how often it was asked."

    def __init__(self, rows: list[str]) -> None:
        self.rows = rows
        self.version: int | None = 0
        self.cursor = Point(x=1, y=0)
        self.created = 0

    def is_focusable(self) -> bool:
        return True

    def content_version(self, width: int, height: int):
        return self.version

    def create_content(self, width: int, height: int) -> UIContent:
        self.created += 1
        rows = list(self.rows)
        return UIContent(
            get_line=lambda number: [("", rows[number])],
            line_count=len(rows),
            cursor_position=self.cursor,
        )


def _set_up(control: _Versioned, **window_args) -> tuple[Window, Application]:
    window = Window(content=control, **window_args)
    app = Application(layout=Layout(window), input=DummyInput(), output=DummyOutput())
    app.layout.update_parents_relations()
    return window, app


def draw(window: Window, style: str = "", beside: str = "") -> tuple[Screen, MouseHandlers]:
    screen = Screen()
    if beside:
        screen.data_buffer[POSITION.ypos][0] = _CHAR_CACHE[beside, ""]
    mouse_handlers = MouseHandlers()
    window.write_to_screen(screen, mouse_handlers, POSITION, style, False, None)
    return screen, mouse_handlers


def text(screen: Screen, y: int) -> str:
    row = screen.data_buffer[y]
    return "".join(row[x].char for x in range(POSITION.xpos, POSITION.xpos + WIDTH))


def test_an_unchanged_window_writes_what_it_wrote():
    control = _Versioned(["first", "second"])
    window, app = _set_up(control, char=" ")
    with set_app(app):
        draw(window)
        second, _ = draw(window)
        info = window.render_info
        third, mouse_handlers = draw(window)

    # The third frame asked for no content: the second took the cells.
    assert control.created == 2
    for y in range(POSITION.ypos, POSITION.ypos + HEIGHT):
        assert dict(third.data_buffer[y]) == dict(second.data_buffer[y])
    assert text(third, 1).rstrip() == "first"
    assert third.get_cursor_position(window) == second.get_cursor_position(window)
    assert repr(third.visible_windows_to_write_positions[window]) == repr(POSITION)
    assert window.render_info is info
    handlers = mouse_handlers.mouse_handlers
    assert handlers[POSITION.ypos][POSITION.xpos] is not handlers[0][0]
    assert third.max_column_index == second.max_column_index


def test_a_new_version_draws_again():
    control = _Versioned(["first"])
    window, app = _set_up(control, char=" ")
    with set_app(app):
        draw(window)
        draw(window)
        control.rows = ["changed"]
        control.version = 1
        screen, _ = draw(window)

    assert text(screen, 1).rstrip() == "changed"


def test_a_cursor_that_moved_says_so_through_the_version():
    control = _Versioned(["first"])
    window, app = _set_up(control, char=" ")
    with set_app(app):
        draw(window)
        draw(window)
        control.cursor = Point(x=4, y=0)
        control.version = 1
        screen, _ = draw(window)

    assert screen.get_cursor_position(window) == Point(x=POSITION.xpos + 4, y=1)


def test_what_was_drawn_over_it_is_not_drawn_again():
    """
    A float covers the window after it drew. The cells kept are the
    window's own, and not the frame's: the float is gone next frame.
    """
    control = _Versioned(["first"])
    window, app = _set_up(control, char=" ")
    with set_app(app):
        draw(window)
        second, _ = draw(window)
        second.data_buffer[1][POSITION.xpos] = _CHAR_CACHE["X", ""]
        third, _ = draw(window)

    assert control.created == 2
    assert text(third, 1).rstrip() == "first"


def test_what_lies_beside_it_is_not_drawn_again():
    "The cells beside the window, on its rows, belong to whatever drew them."
    control = _Versioned(["first"])
    window, app = _set_up(control, char=" ")
    with set_app(app):
        draw(window)
        draw(window, beside="L")
        third, _ = draw(window)

    assert control.created == 2
    assert 0 not in third.data_buffer[POSITION.ypos]


def test_a_new_style_draws_again():
    control = _Versioned(["first"])
    window, app = _set_up(control, char=" ")
    with set_app(app):
        draw(window)
        draw(window)
        screen, _ = draw(window, style="class:other")

    assert control.created == 3
    assert "class:other" in screen.data_buffer[1][POSITION.xpos].style


def test_a_window_that_leaves_cells_unwritten_draws_every_frame():
    "What it leaves is what was under it this frame, which nothing kept."
    control = _Versioned(["first"])
    window, app = _set_up(control)
    with set_app(app):
        for _ in range(3):
            draw(window)

    assert control.created == 3


def test_a_window_told_where_to_scroll_draws_every_frame():
    "The callable can move the view while the content stays the same."
    control = _Versioned(["first"])
    window, app = _set_up(control, char=" ", get_vertical_scroll=lambda window: 0)
    with set_app(app):
        for _ in range(3):
            draw(window)

    assert control.created == 3


def test_new_scroll_offsets_draw_again():
    control = _Versioned(["first"])
    window, app = _set_up(control, char=" ", scroll_offsets=ScrollOffsets())
    with set_app(app):
        draw(window)
        draw(window)
        window.scroll_offsets = ScrollOffsets(top=1)
        draw(window)

    assert control.created == 3


def test_a_control_that_cannot_say_draws_every_frame():
    control = _Versioned(["first"])
    control.version = None
    window, app = _set_up(control, char=" ")
    with set_app(app):
        for _ in range(3):
            draw(window)

    assert control.created == 3
