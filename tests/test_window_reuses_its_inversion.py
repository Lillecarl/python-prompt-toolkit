"""
One inversion per render, however many wheel events one fling sends.

A trackpad fling sends dozens of scroll events between two frames, and
the window built its screen-to-input inversion again for each of them:
every cell of the window walked and bisected per tick, which held a
core and starved the frames the ticks asked for. The first event of a
render builds it now, and the rest of the render shares it. The next
render builds its own, because the mapping it inverts came out of the
last one.

Both scroll directions go through the same inversion, so the test sends
one event each way.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest import mock

from prompt_toolkit.application import Application
from prompt_toolkit.application.current import set_app
from prompt_toolkit.data_structures import Point
from prompt_toolkit.input import DummyInput
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import Window, _RowColToYX
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.mouse_handlers import MouseHandlers
from prompt_toolkit.layout.screen import Screen, WritePosition
from prompt_toolkit.mouse_events import (
    MouseButton,
    MouseEvent,
    MouseEventType,
)
from prompt_toolkit.output import DummyOutput

WIDTH, HEIGHT = 20, 4


class _Recording(FormattedTextControl):
    "A control that writes down the mouse events it gets."

    def __init__(self) -> None:
        super().__init__("first line\nsecond line", focusable=True)
        self.events: list[MouseEvent] = []

    def mouse_handler(self, mouse_event: MouseEvent) -> None:
        self.events.append(mouse_event)


@contextmanager
def an_application(container):
    """
    The container in an application, so that `get_app()` answers.

    A window turns down every mouse event that does not reach it
    through the layout it is in.
    """
    app = Application(
        layout=Layout(container),
        input=DummyInput(),
        output=DummyOutput(),
    )
    app.layout.update_parents_relations()

    with set_app(app):
        yield app


def draw(container) -> MouseHandlers:
    "One frame of the container, and where its clicks land."
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
    return mouse_handlers


def a_wheel(handlers: MouseHandlers, x: int, y: int, direction: MouseEventType) -> None:
    "One wheel tick over this cell of the drawn frame."
    handlers.mouse_handlers[y][x](
        MouseEvent(
            position=Point(x=x, y=y),
            event_type=direction,
            button=MouseButton.NONE,
            modifiers=frozenset(),
        )
    )


def test_two_wheel_ticks_share_one_inversion():
    """
    Down then up over one frame, and the mapping inverts once.

    The directions and the translated positions still arrive: sharing
    the inversion must not eat or move the events.
    """
    control = _Recording()
    root = Window(control)
    real_inverted = _RowColToYX.inverted
    builds: list[None] = []

    def counting(self: _RowColToYX):
        builds.append(None)
        return real_inverted(self)

    with an_application(root), mock.patch.object(_RowColToYX, "inverted", counting):
        handlers = draw(root)
        a_wheel(handlers, 3, 0, MouseEventType.SCROLL_DOWN)
        a_wheel(handlers, 5, 1, MouseEventType.SCROLL_UP)

    assert len(builds) == 1

    down, up = control.events
    assert down.event_type == MouseEventType.SCROLL_DOWN
    assert (down.position.x, down.position.y) == (3, 0)
    assert up.event_type == MouseEventType.SCROLL_UP
    assert (up.position.x, up.position.y) == (5, 1)


def test_a_new_render_builds_its_inversion_again():
    """
    The inversion belongs to the render it came out of.

    A second frame gets its own mapping, so its first event builds
    again rather than reading the frame before.
    """
    control = _Recording()
    root = Window(control)
    real_inverted = _RowColToYX.inverted
    builds: list[None] = []

    def counting(self: _RowColToYX):
        builds.append(None)
        return real_inverted(self)

    with an_application(root), mock.patch.object(_RowColToYX, "inverted", counting):
        a_wheel(draw(root), 3, 0, MouseEventType.SCROLL_DOWN)
        assert len(builds) == 1
        a_wheel(draw(root), 3, 0, MouseEventType.SCROLL_DOWN)
        assert len(builds) == 2

    assert len(control.events) == 2
