"""
Where each character of a window's content landed on the screen.

`Window._copy_body` holds this as runs rather than as one entry per
character. A run is exact only while each character is one cell wide
and lands beside the one before it, so what these tests push at is
everything that breaks a run: a wrap, a double width character, a
combining mark, and the edges a horizontal scroll cuts off.

**The reader that believes the runs is judged against one that
believes nothing.** A test that checked the runs one case at a time
would pass while missing the case nobody thought of, which is how a
cursor ends up one cell out on a line somebody happened to wrap.
"""

from __future__ import annotations

import pytest

from prompt_toolkit.layout.containers import Window, _RowColToYX
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.mouse_handlers import MouseHandlers
from prompt_toolkit.layout.screen import Screen, WritePosition
from prompt_toolkit.utils import get_cwidth


def _drawn(
    text: str, width: int, height: int, wrap_lines: bool = False
) -> tuple[Screen, "object"]:
    "Draw the text into a window, and hand back the screen and the mapping."
    window = Window(
        content=FormattedTextControl(text=text),
        wrap_lines=wrap_lines,
    )
    screen = Screen()
    window.write_to_screen(
        screen,
        MouseHandlers(),
        WritePosition(xpos=0, ypos=0, width=width, height=height),
        "",
        False,
        None,
    )
    return screen, window.render_info._rowcol_to_yx


def _walked(mapping) -> dict:
    "Everything the mapping holds, read through the interface it offers."
    return {rowcol: mapping[rowcol] for rowcol in mapping}


# ----------------------------------------------------------------------
# The runs on their own.


def test_a_run_answers_every_column_it_covers():
    runs = _RowColToYX()
    runs.record(lineno=3, col=5, length=4, y=7, x=10)

    assert runs[3, 5] == (7, 10)
    assert runs[3, 6] == (7, 11)
    assert runs[3, 8] == (7, 13)


def test_a_column_outside_every_run_is_missing():
    """
    **A gap has to raise, not answer.** `cursor_pos_to_screen_pos`
    reads a `KeyError` as "nothing drew there" and falls back; an
    answer invented by arithmetic would put the cursor somewhere no
    character is.
    """
    runs = _RowColToYX()
    runs.record(lineno=0, col=0, length=2, y=0, x=0)
    runs.record(lineno=0, col=5, length=2, y=0, x=5)

    for missing in [(0, 4), (0, 7), (0, 99), (1, 0)]:
        with pytest.raises(KeyError):
            runs[missing]


def test_the_runs_of_a_line_are_searched_in_order():
    "Several runs on one line, which is what a wrap or a wide character makes."
    runs = _RowColToYX()
    runs.record(lineno=0, col=0, length=3, y=0, x=0)
    runs.record(lineno=0, col=3, length=1, y=0, x=3)  # A wide character.
    runs.record(lineno=0, col=4, length=3, y=1, x=0)  # After a wrap.

    assert runs[0, 2] == (0, 2)
    assert runs[0, 3] == (0, 3)
    assert runs[0, 5] == (1, 1)
    assert len(runs) == 7


def test_walking_it_gives_back_every_column():
    "The mouse handler inverts the whole mapping, so it has to be walkable."
    runs = _RowColToYX()
    runs.record(lineno=0, col=0, length=2, y=0, x=0)
    runs.record(lineno=1, col=0, length=1, y=1, x=0)

    assert _walked(runs) == {(0, 0): (0, 0), (0, 1): (0, 1), (1, 0): (1, 0)}


# ----------------------------------------------------------------------
# Against a real render, judged by the screen itself.


@pytest.mark.parametrize(
    "text, width, height, wrap_lines",
    [
        ("hello world", 20, 3, False),
        # A wrap: the run ends where the row does.
        ("abcdefghij", 4, 4, True),
        ("the quick brown fox jumps", 7, 6, True),
        # Double width characters, which advance x by two and col by
        # one, so every one of them ends a run.
        ("ab中文cd", 20, 3, False),
        ("中文中文", 5, 4, True),
        # A combining mark advances col and not x, and merges into the
        # cell before it.
        ("ééx", 20, 3, False),
        # Several lines, and a line that is empty.
        ("one\n\nthree", 20, 5, False),
        # Wider than the window with no wrapping: the tail is cut off
        # and nothing may be asked about it.
        ("abcdefghij", 4, 3, False),
    ],
)
def test_the_mapping_agrees_with_the_screen(text, width, height, wrap_lines):
    """
    **The screen is the independent answer.** The mapping says where a
    character of the input went; the screen says what is really at that
    cell. Checking one against the other needs no second copy of the
    layout arithmetic, which is the only other way to know, and is the
    way that would repeat whatever mistake the first copy made.
    """
    screen, mapping = _drawn(text, width, height, wrap_lines)
    lines = text.split("\n")

    seen = 0
    for (row, col), (y, x) in _walked(mapping).items():
        assert 0 <= row < len(lines), (row, col)
        assert col < len(lines[row]), (row, col)

        character = lines[row][col]

        if get_cwidth(character) == 0:
            # A combining mark draws no cell of its own: it joins the
            # one before it, and its position is the column after that
            # cell. There is nothing at that column to check it
            # against, so what matters is only that it did not take
            # the position of a character that does draw -- which the
            # neighbours of this entry cover.
            seen += 1
            continue

        # **Begins with, not equals.** A combining mark that follows is
        # merged into this same cell, so the cell holds the pair while
        # the input holds the base character on its own.
        drawn = screen.data_buffer[y][x]
        assert drawn.char.startswith(character), (
            "input (%d, %d) is %r, but the screen has %r at (%d, %d)"
            % (row, col, character, drawn.char, y, x)
        )
        seen += 1

    assert seen, "The render recorded nothing at all."


def test_every_drawn_character_can_be_found():
    """
    The cursor asks for a position by row and column, so every
    character that really reached the screen has to have one.
    """
    text = "hello\nworld"
    _screen, mapping = _drawn(text, 20, 4)

    for row, line in enumerate(text.split("\n")):
        for col in range(len(line)):
            assert mapping[row, col], (row, col)
