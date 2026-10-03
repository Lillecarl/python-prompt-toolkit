"""
`walk` yields every container pre-order, and `find_all_controls`
collects every window's content in that order.

Both used to hand each node up through a generator frame per level of
the layout; they walk an explicit stack now. These pin the order, so
the saving cannot quietly reorder a layout.
"""

from prompt_toolkit.layout import Layout, walk
from prompt_toolkit.layout.containers import (
    ConditionalContainer,
    HSplit,
    VSplit,
    Window,
)
from prompt_toolkit.layout.controls import BufferControl


def test_walk_yields_every_container_pre_order():
    inner = VSplit([Window(), Window()])
    outer = HSplit([inner, Window()])

    assert list(walk(outer)) == [outer, inner, *inner.children, outer.children[1]]


def test_walk_skips_a_disabled_conditional_container_only_when_asked():
    shown, hidden = Window(), Window()
    cond = ConditionalContainer(content=hidden, filter=False)
    outer = HSplit([shown, cond])

    assert list(walk(outer, skip_hidden=True)) == [outer, shown]
    assert list(walk(outer)) == [outer, shown, cond, hidden]


def test_find_all_controls_follows_walk_order_and_survives_reuse():
    controls = [BufferControl(), BufferControl(), BufferControl()]
    windows = [Window(content=c) for c in controls]
    layout = Layout(HSplit([VSplit(windows[:2]), windows[2]]))

    found = layout.find_all_controls()

    # A list now, not a generator: every caller consumes all of it, and
    # a second pass over the answer has to work as well as the first.
    assert isinstance(found, list)
    assert found == controls
    assert list(found) == controls
