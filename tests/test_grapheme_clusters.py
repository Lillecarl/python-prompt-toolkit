"""
A grapheme cluster narrower whole than in pieces takes one cell.

A family emoji is three faces and two joiners, and a terminal that
draws it as one glyph moves two columns, not six. A flag and a skin
tone are two characters of two columns each, and one glyph of two.

A cluster as wide whole as in pieces stays as it was: a combining mark
or a variation selector merges into the cell before it, and a conjunct
of two narrow letters takes two cells.
"""

from __future__ import annotations

import pytest
from prompt_toolkit.data_structures import Point
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.controls import UIContent, UIControl
from prompt_toolkit.layout.mouse_handlers import MouseHandlers
from prompt_toolkit.layout.screen import Screen, WritePosition
from prompt_toolkit.utils import get_cwidth

FAMILY = "\U0001f468\u200d\U0001f469\u200d\U0001f467"
FLAG = "\U0001f1f8\U0001f1ea"
THUMB = "\U0001f44d\U0001f3fd"
RUNNER = "\U0001f3c3\u200d♀\ufe0f"
KEYCAP = "1\ufe0f\u20e3"
HEART = "❤\ufe0f"
CONJUNCT = "क\u094dष"


class _Line(UIControl):
    def __init__(self, text: str, cursor: int = 0) -> None:
        self.text = text
        self.cursor = cursor

    def create_content(self, width: int, height: int) -> UIContent:
        return UIContent(
            get_line=lambda number: [("", self.text)],
            line_count=1,
            cursor_position=Point(x=self.cursor, y=0),
        )


def _draw(control: _Line) -> tuple[Window, Screen]:
    window = Window(content=control)
    screen = Screen()
    window.write_to_screen(
        screen,
        MouseHandlers(),
        WritePosition(xpos=0, ypos=0, width=20, height=1),
        "",
        False,
        None,
    )
    return window, screen


def _cells(screen: Screen) -> list[tuple[str, int]]:
    row = screen.data_buffer[0]
    return [(row[x].char, row[x].width) for x in range(4)]


@pytest.mark.parametrize("cluster", [FAMILY, FLAG, THUMB, RUNNER])
def test_a_cluster_is_one_cell_two_columns_wide(cluster: str) -> None:
    assert get_cwidth(cluster) == 2
    _, screen = _draw(_Line(cluster + "xy"))
    assert _cells(screen) == [(cluster, 2), ("", 0), ("x", 1), ("y", 1)]


def test_the_cursor_after_a_cluster_stands_two_columns_on() -> None:
    window, _ = _draw(_Line(FAMILY + "x", cursor=len(FAMILY)))
    assert window.render_info is not None
    assert window.render_info.cursor_position == Point(x=2, y=0)


@pytest.mark.parametrize("cluster", [KEYCAP, HEART])
def test_a_selector_adds_no_width(cluster: str) -> None:
    assert get_cwidth(cluster) == 1
    _, screen = _draw(_Line(cluster + "x"))
    assert _cells(screen)[:2] == [(cluster, 1), ("x", 1)]


def test_a_narrow_conjunct_takes_its_two_cells() -> None:
    assert get_cwidth(CONJUNCT) == 2
    _, screen = _draw(_Line(CONJUNCT))
    assert [screen.data_buffer[0][x].char for x in range(2)] == [
        CONJUNCT[:2],
        CONJUNCT[2],
    ]


def test_two_flags_are_two_cells() -> None:
    _, screen = _draw(_Line(FLAG + FLAG))
    assert _cells(screen) == [(FLAG, 2), ("", 0), (FLAG, 2), ("", 0)]
