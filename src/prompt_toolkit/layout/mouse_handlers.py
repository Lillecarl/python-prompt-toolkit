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
        # The regions, in the order they were set, until something reads
        # the table. A render sets one per window and a mouse event reads
        # one cell, so the table is built for the event that needs it and
        # not on every frame.
        self._ranges: list[tuple[int, int, int, int, MouseHandler]] = []
        self._table: defaultdict[int, defaultdict[int, MouseHandler]] | None = None

    @property
    def mouse_handlers(self) -> defaultdict[int, defaultdict[int, MouseHandler]]:
        """
        Map y (row) to x (column) to handlers.

        A dictionary per row, so that the scrollable pane can copy over
        the handlers of the rows it shows. Built from the regions the
        first time it is read; regions set after that go straight in.
        """
        if self._table is None:

            def dummy_callback(mouse_event: MouseEvent) -> NotImplementedOrNone:
                """
                :param mouse_event: `MouseEvent` instance.
                """
                return NotImplemented

            self._table = defaultdict(lambda: defaultdict(lambda: dummy_callback))
            for region in self._ranges:
                self._fill(*region)
            self._ranges.clear()
        return self._table

    @mouse_handlers.setter
    def mouse_handlers(
        self, table: defaultdict[int, defaultdict[int, MouseHandler]]
    ) -> None:
        self._table = table
        self._ranges.clear()

    def _fill(
        self, x_min: int, x_max: int, y_min: int, y_max: int, handler: MouseHandler
    ) -> None:
        assert self._table is not None
        # Every cell of the region gets the same handler, so the row is
        # built once with `fromkeys` and copied into each line with
        # `update`. Both run in C.
        row_handlers = dict.fromkeys(range(x_min, x_max), handler)
        for y in range(y_min, y_max):
            self._table[y].update(row_handlers)

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
        if self._table is None:
            self._ranges.append((x_min, x_max, y_min, y_max, handler))
        else:
            self._fill(x_min, x_max, y_min, y_max, handler)
