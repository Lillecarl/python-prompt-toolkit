"""
A `Screen` makes each row through `screen._new_row`.

A column nothing wrote reads the screen's default and keeps it, which is
what the rest of a render counts on. The screen looks the factory up when
it makes a row, so a row of another type can stand in for it.
"""

from prompt_toolkit.layout import screen as screen_module
from prompt_toolkit.layout.screen import Char, Screen


def test_a_column_nothing_wrote_reads_the_default_and_keeps_it():
    default = Char("x", "class:default")
    row = Screen(default_char=default).data_buffer[3]

    assert row[7] is default
    assert 7 in row
    assert 8 not in row


def test_rows_come_from_the_factory_the_module_holds_now(monkeypatch):
    made = []

    def new_row(default):
        row = {}
        made.append((row, default))
        return row

    monkeypatch.setattr(screen_module, "_new_row", new_row)
    default = Char("x", "")
    row = Screen(default_char=default).data_buffer[0]

    assert made == [(row, default)]
