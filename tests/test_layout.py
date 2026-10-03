from __future__ import annotations

import pytest

from prompt_toolkit.layout import InvalidLayoutError, Layout
from prompt_toolkit.layout.containers import HSplit, VSplit, Window
from prompt_toolkit.layout.controls import BufferControl
from prompt_toolkit.layout.screen import WritePosition


def test_layout_class():
    c1 = BufferControl()
    c2 = BufferControl()
    c3 = BufferControl()
    win1 = Window(content=c1)
    win2 = Window(content=c2)
    win3 = Window(content=c3)

    layout = Layout(container=VSplit([HSplit([win1, win2]), win3]))

    # Listing of windows/controls.
    assert list(layout.find_all_windows()) == [win1, win2, win3]
    assert list(layout.find_all_controls()) == [c1, c2, c3]

    # Focusing something.
    layout.focus(c1)
    assert layout.has_focus(c1)
    assert layout.has_focus(win1)
    assert layout.current_control == c1
    assert layout.previous_control == c1

    layout.focus(c2)
    assert layout.has_focus(c2)
    assert layout.has_focus(win2)
    assert layout.current_control == c2
    assert layout.previous_control == c1

    layout.focus(win3)
    assert layout.has_focus(c3)
    assert layout.has_focus(win3)
    assert layout.current_control == c3
    assert layout.previous_control == c2

    # Pop focus. This should focus the previous control again.
    layout.focus_last()
    assert layout.has_focus(c2)
    assert layout.has_focus(win2)
    assert layout.current_control == c2
    assert layout.previous_control == c1


def test_create_invalid_layout():
    with pytest.raises(InvalidLayoutError):
        Layout(HSplit([]))


def test_a_second_divide_gets_the_cached_answer():
    """
    A split that did not change asks the same question on every render,
    so `_divide_widths` keeps the answer: the second call hands back the
    very list the first one built.
    """
    split = VSplit([Window(), Window(), Window()])

    assert split._divide_widths(80) is split._divide_widths(80)


def test_a_changed_layout_divides_again():
    "New dimensions are a new question, so they get a new answer."
    split = VSplit([Window(), Window()])

    before = split._divide_widths(80)
    split.children.append(Window())
    after = split._divide_widths(80)

    assert before is not None
    assert after is not None
    assert after is not before
    # The child and the padding window beside it.
    assert len(after) == len(before) + 2


def test_heights_are_kept_the_same_way():
    split = HSplit([Window(), Window()])
    area = WritePosition(xpos=0, ypos=0, width=80, height=24)

    assert split._divide_heights(area) is split._divide_heights(area)
