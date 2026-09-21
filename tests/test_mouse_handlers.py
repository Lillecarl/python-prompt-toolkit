"""
`MouseHandlers.set_mouse_handler_for_range` covers a rectangle.

Every cell of the region takes the same handler, so the row is built
once and copied into each line of the region. These say the copy
reaches the same cells the loop reached, and no others.
"""

from prompt_toolkit.layout.mouse_handlers import MouseHandlers


def handler_at(handlers, x, y):
    return handlers.mouse_handlers[y][x]


def a_handler(name):
    def handle(mouse_event):
        return name

    return handle


def test_every_cell_of_the_region_gets_the_handler():
    handlers = MouseHandlers()
    one = a_handler("one")

    handlers.set_mouse_handler_for_range(
        x_min=1, x_max=4, y_min=2, y_max=4, handler=one
    )

    for y in (2, 3):
        for x in (1, 2, 3):
            assert handler_at(handlers, x, y) is one


def test_cells_outside_the_region_are_left_alone():
    handlers = MouseHandlers()
    one = a_handler("one")

    handlers.set_mouse_handler_for_range(
        x_min=1, x_max=3, y_min=1, y_max=3, handler=one
    )

    for x, y in ((0, 1), (3, 1), (1, 0), (1, 3)):
        assert handler_at(handlers, x, y) is not one


def test_a_region_of_no_width_or_no_height_sets_nothing():
    handlers = MouseHandlers()
    one = a_handler("one")

    handlers.set_mouse_handler_for_range(
        x_min=2, x_max=2, y_min=0, y_max=4, handler=one
    )
    handlers.set_mouse_handler_for_range(
        x_min=0, x_max=4, y_min=2, y_max=2, handler=one
    )

    for y in range(4):
        for x in range(4):
            assert handler_at(handlers, x, y) is not one


def test_a_later_region_takes_the_cells_it_overlaps():
    """
    A float draws over what is under it, and the handler of the cells
    it covers has to be the float's. The rows are updated and not
    replaced, so the cells beside the overlap keep what they had.
    """
    handlers = MouseHandlers()
    under, over = a_handler("under"), a_handler("over")

    handlers.set_mouse_handler_for_range(
        x_min=0, x_max=4, y_min=0, y_max=2, handler=under
    )
    handlers.set_mouse_handler_for_range(
        x_min=2, x_max=6, y_min=1, y_max=3, handler=over
    )

    assert handler_at(handlers, 0, 0) is under
    assert handler_at(handlers, 3, 0) is under
    assert handler_at(handlers, 1, 1) is under
    assert handler_at(handlers, 2, 1) is over
    assert handler_at(handlers, 5, 2) is over


def test_a_cell_nobody_claimed_answers_without_being_asked_to_handle():
    "The default is a callback that says it did nothing, not a missing key."
    handlers = MouseHandlers()

    assert handler_at(handlers, 7, 9)(None) is NotImplemented
