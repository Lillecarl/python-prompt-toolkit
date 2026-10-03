"""
`Window._fill_bg` erases the whole area one row at a time.

Every cell of the area takes the same character, so the row is built
once and copied into each line. These say the copy reaches every cell
of the area, and nothing outside it.
"""

from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.mouse_handlers import MouseHandlers
from prompt_toolkit.layout.screen import Screen, WritePosition


def _drawn(window, erase_bg=False):
    "Draw the window offset from the origin, so the outside is visible."
    screen = Screen()
    window.write_to_screen(
        screen,
        MouseHandlers(),
        WritePosition(xpos=1, ypos=1, width=4, height=3),
        "",
        erase_bg,
        None,
    )
    return screen


def test_a_window_with_a_char_fills_its_whole_area():
    window = Window(content=FormattedTextControl(text=""), char="x")

    screen = _drawn(window)

    for y in (1, 2, 3):
        for x in (1, 2, 3, 4):
            assert screen.data_buffer[y][x].char == "x"


def test_an_erased_window_fills_with_blank():
    window = Window(content=FormattedTextControl(text=""))

    screen = _drawn(window, erase_bg=True)

    for y in (1, 2, 3):
        for x in (1, 2, 3, 4):
            assert screen.data_buffer[y][x].char == " "


def test_cells_outside_the_area_keep_what_they_had():
    window = Window(content=FormattedTextControl(text=""), char="x")

    screen = _drawn(window)

    assert screen.data_buffer[0][0].char == " "
    assert screen.data_buffer[0][3].char == " "
    assert screen.data_buffer[4][4].char == " "
