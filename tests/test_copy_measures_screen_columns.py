"""
The copy measures screen columns, not window columns.

A window usually starts at the left edge, where the two are the
same. Any other window -- the right pane beside the left one, a bar
beside its text -- writes past its origin, and the renderer reads
what the copy measured as screen columns: a measure in window
columns ends the row early, and the trim erases what it just drew,
or never paints it at all.

The wire test holds the whole chain -- the copy measures, the diff
walks what it measured -- against measuring every row itself, frame
after frame of scrolling text. The wire is identical either way, at
the origin and past it. The lines end in content on purpose: a row
of trailing blanks measures one past what the walk finds, which
paints the same cells with one more space and move.
"""

from __future__ import annotations

import random
from io import StringIO

import pytest
from prompt_toolkit.application.dummy import DummyApplication
from prompt_toolkit.data_structures import Point, Size
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.controls import UIContent, UIControl
from prompt_toolkit.layout.mouse_handlers import MouseHandlers
from prompt_toolkit.layout.screen import Screen, WritePosition
from prompt_toolkit.output import ColorDepth
from prompt_toolkit.output.vt100 import Vt100_Output
from prompt_toolkit.renderer import (
    _KeepABlankCellCache,
    _StyleStringToAttrsCache,
    _output_screen_diff,
)
from prompt_toolkit.styles import DummyStyleTransformation, Style

WIDTH, HEIGHT = 60, 6
XPOS = 21


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

    def is_focusable(self) -> bool:
        return False


def _draw(window: Window, position: WritePosition) -> Screen:
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


def test_a_copy_past_the_origin_measures_screen_columns() -> None:
    window = Window(content=_Stable([[("", "hi")]]))
    screen = _draw(
        window, WritePosition(xpos=XPOS, ypos=0, width=WIDTH, height=HEIGHT)
    )
    # The last cell written, in screen columns: the copy counts
    # window columns moved past the origin.
    assert screen.max_column_index[0] == XPOS + 1


class _NoStash(dict[int, int]):
    "A measure that holds nothing: the renderer walks every row itself."

    def get(self, key: int, default: int | None = None) -> int | None:
        return None

    def __setitem__(self, key: int, value: int) -> None:
        pass

    def __contains__(self, key: object) -> bool:
        return False


def _wire(xpos: int) -> list[str]:
    "Eleven frames of scrolling text, as wire bytes."
    rnd = random.Random(42)
    app = DummyApplication()
    control = _Stable(
        [[("", "line %d padding" % number)] for number in range(HEIGHT + 20)]
    )
    window = Window(content=control, wrap_lines=False)
    position = WritePosition(xpos=xpos, ypos=0, width=WIDTH, height=HEIGHT)
    style = Style([])
    attrs = _StyleStringToAttrsCache(
        style.get_attrs_for_style_str, DummyStyleTransformation()
    )
    blanks = _KeepABlankCellCache(attrs)
    size = Size(rows=HEIGHT, columns=WIDTH + xpos)
    buf = StringIO()
    out = Vt100_Output(buf, lambda: size)
    current = Point(x=0, y=0)
    last_style: str | None = None
    previous: Screen | None = None
    previous_width = 0
    frames = []
    for step in range(11):
        screen = Screen()
        window.write_to_screen(
            screen, MouseHandlers(), position, "", False, None
        )
        if xpos and step == 0:
            # The window really stands past the origin: its cells sit
            # past it on the screen, or this test proves nothing.
            assert any(
                column >= xpos
                for row in screen.data_buffer.values()
                for column in row
                if row[column].char != " "
            )
        current, last_style = _output_screen_diff(
            app,
            out,
            screen,
            current,
            ColorDepth.DEPTH_8_BIT,
            previous,
            last_style,
            False,
            True,
            attrs,
            blanks,
            size,
            previous_width,
        )
        out.flush()
        frames.append(buf.getvalue())
        buf.truncate(0)
        buf.seek(0)
        control.rows = control.rows[1:] + [
            [("", "new %d %s" % (step, rnd.choice(["x", "yy", "zzz"])))]
        ]
        previous = screen
        previous_width = size.columns
    return frames


@pytest.mark.parametrize("xpos", [0, XPOS])
def test_the_wire_matches_the_measured_walk(xpos: int) -> None:
    real_copy = Window._copy_body

    def without_stash(
        self: Window,
        ui_content: UIContent,
        new_screen: Screen,
        *args: object,
        **kwargs: object,
    ) -> object:
        real = new_screen.__dict__.get("max_column_index")
        new_screen.__dict__["max_column_index"] = _NoStash()
        try:
            return real_copy(self, ui_content, new_screen, *args, **kwargs)  # type: ignore[arg-type]
        finally:
            if real is not None:
                new_screen.__dict__["max_column_index"] = real

    stashed = _wire(xpos)
    Window._copy_body = without_stash  # type: ignore[method-assign]
    try:
        measured = _wire(xpos)
    finally:
        Window._copy_body = real_copy
    assert stashed == measured
    assert Window._copy_body is real_copy
