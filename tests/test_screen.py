"""
`Screen.fill_area` puts a style on every cell of a rectangle.

It is the innermost loop of a render, so it holds the last cell it
restyled and reuses the answer when the next cell is the same object.
That is sound because `_CHAR_CACHE` hands out one `Char` for each
(character, style), and every cell nothing drew is the screen's own
default, which is one shared object. These say the shortcut gives the
same answer the long way gives.
"""

from prompt_toolkit.layout.screen import Char, Screen, WritePosition


def area(xpos=0, ypos=0, width=4, height=2):
    return WritePosition(xpos=xpos, ypos=ypos, width=width, height=height)


def styles_of(screen, width, height, xpos=0, ypos=0):
    "The style of every cell of a rectangle, row by row."
    return [
        [screen.data_buffer[y][x].style for x in range(xpos, xpos + width)]
        for y in range(ypos, ypos + height)
    ]


def characters_of(screen, width, height):
    return [
        "".join(screen.data_buffer[y][x].char for x in range(width))
        for y in range(height)
    ]


def test_every_cell_of_the_area_takes_the_style():
    screen = Screen()
    screen.fill_area(area(), style="class:red")

    assert styles_of(screen, 4, 2) == [
        ["class:red [transparent]"] * 4,
        ["class:red [transparent]"] * 4,
    ]


def test_cells_outside_the_area_are_untouched():
    screen = Screen()
    screen.fill_area(area(xpos=1, ypos=1, width=2, height=1), style="class:red")

    assert screen.data_buffer[0][0].style == "[transparent]"
    assert screen.data_buffer[1][0].style == "[transparent]"
    assert screen.data_buffer[1][1].style == "class:red [transparent]"
    assert screen.data_buffer[1][2].style == "class:red [transparent]"
    assert screen.data_buffer[1][3].style == "[transparent]"


def test_a_cell_keeps_its_own_style_under_the_new_one():
    screen = Screen()
    screen.data_buffer[0][1] = Char("x", "class:blue")
    screen.fill_area(area(width=3, height=1), style="class:red")

    assert styles_of(screen, 3, 1) == [
        [
            "class:red [transparent]",
            "class:red class:blue",
            "class:red [transparent]",
        ]
    ]


def test_cells_that_differ_each_get_their_own_answer():
    """
    The loop reuses the answer it has while the cell stays the same
    object. A run that ends has to end the reuse with it, so this puts
    a different cell between two identical ones: a shortcut that never
    looked again would give the middle cell the style of the first.
    """
    screen = Screen()
    screen.data_buffer[0][0] = Char("a", "class:one")
    screen.data_buffer[0][1] = Char("b", "class:two")
    screen.data_buffer[0][2] = Char("a", "class:one")

    screen.fill_area(area(width=3, height=1), style="class:red")

    assert styles_of(screen, 3, 1) == [
        ["class:red class:one", "class:red class:two", "class:red class:one"]
    ]
    assert characters_of(screen, 3, 1) == ["aba"]


def test_a_run_that_crosses_rows_is_still_one_answer():
    "The reuse is not reset per row, and the answer is the same either way."
    screen = Screen()
    screen.fill_area(area(width=3, height=3), style="class:red")

    assert styles_of(screen, 3, 3) == [["class:red [transparent]"] * 3] * 3


def test_after_puts_the_style_behind_the_one_that_is_there():
    screen = Screen()
    screen.data_buffer[0][0] = Char("x", "class:blue")
    screen.fill_area(area(width=1, height=1), style="class:red", after=True)

    assert screen.data_buffer[0][0].style == "class:blue class:red"


def test_a_style_of_nothing_fills_nothing():
    """
    A window with no style of its own asks for this on every frame, so
    the whole call has to cost nothing rather than rewrite every cell
    with the same style it had.
    """
    screen = Screen()
    before = screen.data_buffer[0][0]

    screen.fill_area(area(), style="   ")

    assert screen.data_buffer[0][0] is before
