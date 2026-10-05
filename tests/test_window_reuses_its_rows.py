"""
One copy per line, however many frames show it.

Copying a window looks every cell up: the style of each fragment,
the character of each cell. A control that caches its lines hands
the same list back while the row stands still, and the same list
draws the same characters, so the next frame stores those back
instead. The frame after a program wrote one line then copies one
line.

The cache is cleared between the frames: without the reuse the
second frame would build the same characters again and the test
could not tell, because the character cache hands the same objects
back for the same key.
"""

from __future__ import annotations

from contextlib import contextmanager

from prompt_toolkit.application import Application
from prompt_toolkit.application.current import set_app
from prompt_toolkit.input import DummyInput
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import _CHAR_CACHE, Window
from prompt_toolkit.layout.controls import UIContent, UIControl
from prompt_toolkit.layout.mouse_handlers import MouseHandlers
from prompt_toolkit.layout.screen import Screen, WritePosition
from prompt_toolkit.output import DummyOutput

WIDTH, HEIGHT = 20, 4


class _Stable(UIControl):
    "A control whose lines are the same objects until replaced."

    def __init__(self, rows: list) -> None:
        self.rows = rows

    def create_content(self, width: int, height: int) -> UIContent:
        content = UIContent(
            get_line=lambda number: self.rows[number], line_count=len(self.rows)
        )
        content.stable_lines = True
        return content


def draw(window: Window, position: WritePosition) -> Screen:
    "One frame of the window on a screen of its own."
    screen = Screen()
    window.write_to_screen(
        screen,
        MouseHandlers(),
        position,
        "",
        False,
        None,
    )
    return screen


def cells(screen: Screen, y: int) -> dict:
    "The cells one screen row holds, by column."
    return dict(screen.data_buffer[y])


def zip_rows(second: Screen, first: Screen, y: int):
    "The cells of one row of two screens, paired by column."
    left = cells(second, y)
    right = cells(first, y)
    assert set(left) == set(right)
    return [(left[x], right[x]) for x in left]


@contextmanager
def cleared_cache():
    "Empty the character cache, putting it back afterwards."
    saved = dict(_CHAR_CACHE)
    saved_keys = list(_CHAR_CACHE._keys)
    _CHAR_CACHE.clear()
    _CHAR_CACHE._keys.clear()
    try:
        yield
    finally:
        _CHAR_CACHE.clear()
        _CHAR_CACHE._keys.clear()
        _CHAR_CACHE.update(saved)
        _CHAR_CACHE._keys.extend(saved_keys)


def test_an_unchanged_line_is_stored_back():
    control = _Stable(
        [
            [("", "first line")],
            [("bold", "second"), ("", " line")],
        ]
    )
    window = Window(content=control)
    app = Application(layout=Layout(window), input=DummyInput(), output=DummyOutput())
    app.layout.update_parents_relations()
    position = WritePosition(xpos=0, ypos=0, width=WIDTH, height=HEIGHT)

    with set_app(app):
        draw(window, position)
        before = draw(window, position)
        with cleared_cache():
            after = draw(window, position)

    # The second frame collects what the first one registered, and the
    # third stores it back: every cell is the object the frame before
    # wrote, which a fresh copy could never be with an empty cache.
    for y in range(2):
        assert all(
            second_cell is first_cell
            for second_cell, first_cell in zip_rows(after, before, y)
        )


def test_a_changed_line_is_copied_again():
    control = _Stable(
        [
            [("", "first line")],
            [("", "second line")],
        ]
    )
    window = Window(content=control)
    app = Application(layout=Layout(window), input=DummyInput(), output=DummyOutput())
    app.layout.update_parents_relations()
    position = WritePosition(xpos=0, ypos=0, width=WIDTH, height=HEIGHT)

    with set_app(app):
        draw(window, position)
        before = draw(window, position)
        control.rows[1] = [("", "changed line")]
        with cleared_cache():
            after = draw(window, position)

    assert (
        "".join(cell.char for _, cell in sorted(cells(after, 1).items()))
        == "changed line"
    )
    assert all(
        second_cell is first_cell
        for second_cell, first_cell in zip_rows(after, before, 0)
    )


def test_a_moved_window_is_copied_again():
    control = _Stable([[("", "first line")]])
    window = Window(content=control)
    app = Application(layout=Layout(window), input=DummyInput(), output=DummyOutput())
    app.layout.update_parents_relations()

    with set_app(app):
        draw(window, WritePosition(xpos=0, ypos=0, width=WIDTH, height=HEIGHT))
        second = draw(window, WritePosition(xpos=2, ypos=1, width=WIDTH, height=HEIGHT))

    assert (
        "".join(cell.char for _, cell in sorted(cells(second, 1).items())[:10])
        == "first line"
    )
    assert cells(second, 0) == {}


class _Unstable(UIControl):
    "The same lines, claimed by nobody: every frame copies them again."

    def __init__(self, rows: list) -> None:
        self.rows = rows

    def create_content(self, width: int, height: int) -> UIContent:
        return UIContent(
            get_line=lambda number: self.rows[number], line_count=len(self.rows)
        )


def test_a_line_no_control_claims_is_copied_again():
    control = _Unstable([[("", "first line")]])
    window = Window(content=control)
    app = Application(layout=Layout(window), input=DummyInput(), output=DummyOutput())
    app.layout.update_parents_relations()
    position = WritePosition(xpos=0, ypos=0, width=WIDTH, height=HEIGHT)

    with set_app(app):
        draw(window, position)
        before = draw(window, position)
        with cleared_cache():
            after = draw(window, position)

    # The same objects twice over, and still no reuse: nothing said
    # they would stay, so the window looks every cell up again.
    assert all(
        second_cell is not first_cell
        for second_cell, first_cell in zip_rows(after, before, 0)
    )
