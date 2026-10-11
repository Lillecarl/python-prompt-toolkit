from __future__ import annotations

from prompt_toolkit.layout.screen import Screen


def test_floats_draw_by_z_index_and_then_in_the_order_they_came():
    "A float that a float adds joins the queue behind the ones of its z-index."
    screen = Screen()
    drawn = []

    def draw(name, adds=()):
        def run():
            drawn.append(name)
            for z_index, added in adds:
                screen.draw_with_z_index(z_index, draw(added))

        return run

    screen.draw_with_z_index(1, draw("a"))
    screen.draw_with_z_index(0, draw("b", adds=[(0, "d"), (1, "e")]))
    screen.draw_with_z_index(1, draw("c"))
    screen.draw_all_floats()

    assert drawn == ["b", "d", "a", "c", "e"]
