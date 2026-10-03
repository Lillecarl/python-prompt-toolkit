from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import TYPE_CHECKING

from prompt_toolkit.mouse_events import MouseEvent

if TYPE_CHECKING:
    from prompt_toolkit.key_binding.key_bindings import NotImplementedOrNone

__all__ = [
    "MouseHandler",
    "MouseHandlers",
]


MouseHandler = Callable[[MouseEvent], "NotImplementedOrNone"]


class MouseHandlers:
    """
    Two dimensional raster of callbacks for mouse events.
    """

    def __init__(self) -> None:
        def dummy_callback(mouse_event: MouseEvent) -> NotImplementedOrNone:
            """
            :param mouse_event: `MouseEvent` instance.
            """
            return NotImplemented

        # NOTE: Previously, the data structure was a dictionary mapping (x,y)
        # to the handlers. This however would be more inefficient when copying
        # over the mouse handlers of the visible region in the scrollable pane.

        # Map y (row) to x (column) to handlers.
        self.mouse_handlers: defaultdict[int, defaultdict[int, MouseHandler]] = (
            defaultdict(lambda: defaultdict(lambda: dummy_callback))
        )

    def set_mouse_handler_for_range(
        self,
        x_min: int,
        x_max: int,
        y_min: int,
        y_max: int,
        handler: Callable[[MouseEvent], NotImplementedOrNone],
    ) -> None:
        """
        Set mouse handler for a region.
        """
        # Every cell of the region gets the same handler, so the row is
        # built once with `fromkeys` and copied into each line with
        # `update`. Both run in C, where the loop this replaces stored
        # each cell in Python.
        row_handlers = dict.fromkeys(range(x_min, x_max), handler)
        for y in range(y_min, y_max):
            self.mouse_handlers[y].update(row_handlers)
