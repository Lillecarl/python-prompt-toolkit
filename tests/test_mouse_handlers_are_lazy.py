"""
The mouse handlers keep regions until the table is read.

A render sets a region per window and nothing reads a cell until a
mouse event arrives, so the table is built for the event and not on
every frame. Once built, it is the table: a region set later lands in
it, and a table set from outside replaces it.
"""

from __future__ import annotations

from collections import defaultdict

from prompt_toolkit.layout.mouse_handlers import MouseHandlers


def first(event):
    return "first"


def second(event):
    return "second"


def test_a_region_set_after_the_table_was_read_lands_in_it():
    handlers = MouseHandlers()
    handlers.set_mouse_handler_for_range(0, 10, 0, 5, first)
    table = handlers.mouse_handlers
    handlers.set_mouse_handler_for_range(0, 3, 0, 1, second)
    assert table[0][1] is second
    assert handlers.mouse_handlers is table


def test_a_table_set_from_outside_is_the_one_read():
    handlers = MouseHandlers()
    handlers.set_mouse_handler_for_range(0, 10, 0, 5, first)
    replaced = defaultdict(lambda: defaultdict(lambda: second))
    handlers.mouse_handlers = replaced
    assert handlers.mouse_handlers is replaced
    assert handlers.mouse_handlers[0][0] is second
    handlers.set_mouse_handler_for_range(0, 1, 0, 1, first)
    assert replaced[0][0] is first
