from __future__ import annotations

from prompt_toolkit.application import Application
from prompt_toolkit.application.current import set_app
from prompt_toolkit.layout import Float, FloatContainer, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.mouse_handlers import MouseHandlers
from prompt_toolkit.layout.screen import Screen, WritePosition


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


def test_a_float_not_at_the_cursor_draws_at_its_own_z_index():
    """
    Only a float placed at the cursor waits for the cursor. `xcursor`
    and `ycursor` are booleans, so a float with neither is drawn at the
    z-index it asks for, under a window of the content above it.
    """
    content = Window(FormattedTextControl("under"), z_index=5)
    container = FloatContainer(
        content,
        floats=[Float(Window(FormattedTextControl("float"), width=5, height=1), top=0, left=0, z_index=1)],
    )
    screen = Screen()
    with set_app(Application(layout=Layout(container))):
        container.write_to_screen(
            screen,
            MouseHandlers(),
            WritePosition(xpos=0, ypos=0, width=10, height=1),
            parent_style="",
            erase_bg=False,
            z_index=None,
        )
        screen.draw_all_floats()

    assert "".join(screen.data_buffer[0][x].char for x in range(5)) == "under"
