from __future__ import annotations

from collections import defaultdict
from typing import TypeVar

from prompt_toolkit.data_structures import Point
from prompt_toolkit.filters import FilterOrBool, to_filter
from prompt_toolkit.key_binding import KeyBindingsBase

from .containers import Container, ScrollOffsets
from .dimension import AnyDimension, Dimension, sum_layout_dimensions, to_dimension
from .mouse_handlers import MouseHandlers
from .screen import Char, Screen, WritePosition, _CHAR_CACHE

__all__ = ["ScrollablePane"]

# Never go beyond this height, because performance will degrade.
MAX_AVAILABLE_HEIGHT = 10_000

_Row = TypeVar("_Row")


def _clipped_rows(
    rows: defaultdict[int, _Row], top: int, bottom: int
) -> defaultdict[int, _Row]:
    """
    Stand in for one dictionary of rows, holding only one band of it.

    A `Screen` keeps its cells and its escape sequences as rows, and so
    does `MouseHandlers` with its callbacks. A `ScrollablePane` draws
    its content above and below the rows it owns, and those rows belong
    to other containers, so what lands there goes into a bin that
    nothing reads.

    The columns are not clipped. The content is given the width of the
    pane, so it stays inside it, and no other container in this library
    defends against a child that draws beyond the position it was given.
    """
    assert rows.default_factory is not None

    the_bin = rows.default_factory()
    clipped: defaultdict[int, _Row] = defaultdict(lambda: the_bin)
    for y in range(top, bottom):
        clipped[y] = rows[y]
    return clipped


def _clipped_mouse_handlers(
    mouse_handlers: MouseHandlers, write_position: WritePosition
) -> MouseHandlers:
    "The same handlers, minus every row outside the pane."
    clipped = MouseHandlers()
    clipped.mouse_handlers = _clipped_rows(
        mouse_handlers.mouse_handlers,
        write_position.ypos,
        write_position.ypos + write_position.height,
    )
    return clipped


class _ClippedScreen(Screen):
    """
    A screen that writes to one band of rows of another screen.

    Only the cells and the escape sequences are clipped. Everything else a
    render leaves on a screen -- where each window was drawn, the cursor, the
    menus -- is in the coordinates of the real screen already, because there
    is one coordinate space and not two.

    The write positions go straight into the real screen. The cursor and the
    menus do not: a pane keeps the terminal cursor inside itself, and that is
    a rule about the pane rather than a translation, so it is applied once
    after the content is drawn.

    The floats stay here as well, and `ScrollablePane` draws them itself, so
    that everything a frame of the pane holds is finished before its caller
    goes on.
    """

    def __init__(self, screen: Screen, write_position: WritePosition) -> None:
        super().__init__()

        top = write_position.ypos
        bottom = top + write_position.height

        self.data_buffer = _clipped_rows(screen.data_buffer, top, bottom)
        self.zero_width_escapes = _clipped_rows(screen.zero_width_escapes, top, bottom)
        self.visible_windows_to_write_positions = (
            screen.visible_windows_to_write_positions
        )
        self.show_cursor = screen.show_cursor


class ScrollablePane(Container):
    """
    Container widget that exposes a larger virtual screen to its content and
    displays it in a vertical scrollbale region.

    Typically this is wrapped in a large `HSplit` container. Make sure in that
    case to not specify a `height` dimension of the `HSplit`, so that it will
    scale according to the content.

    .. note::

        If you want to display a completion menu for widgets in this
        `ScrollablePane`, then it's still a good practice to use a
        `FloatContainer` with a `CompletionsMenu` in a `Float` at the top-level
        of the layout hierarchy, rather then nesting a `FloatContainer` in this
        `ScrollablePane`. (Otherwise, it's possible that the completion menu
        is clipped.)

    :param content: The content container.
    :param scrolloffset: Try to keep the cursor within this distance from the
        top/bottom (left/right offset is not used).
    :param keep_cursor_visible: When `True`, automatically scroll the pane so
        that the cursor (of the focused window) is always visible.
    :param keep_focused_window_visible: When `True`, automatically scroll the
        pane so that the focused window is visible, or as much visible as
        possible if it doesn't completely fit the screen.
    :param max_available_height: Always constraint the height to this amount
        for performance reasons.
    :param width: When given, use this width instead of looking at the children.
    :param height: When given, use this height instead of looking at the children.
    :param show_scrollbar: When `True` display a scrollbar on the right.
    """

    def __init__(
        self,
        content: Container,
        scroll_offsets: ScrollOffsets | None = None,
        keep_cursor_visible: FilterOrBool = True,
        keep_focused_window_visible: FilterOrBool = True,
        max_available_height: int = MAX_AVAILABLE_HEIGHT,
        width: AnyDimension = None,
        height: AnyDimension = None,
        show_scrollbar: FilterOrBool = True,
        display_arrows: FilterOrBool = True,
        up_arrow_symbol: str = "^",
        down_arrow_symbol: str = "v",
    ) -> None:
        self.content = content
        self.scroll_offsets = scroll_offsets or ScrollOffsets(top=1, bottom=1)
        self.keep_cursor_visible = to_filter(keep_cursor_visible)
        self.keep_focused_window_visible = to_filter(keep_focused_window_visible)
        self.max_available_height = max_available_height
        self.width = width
        self.height = height
        self.show_scrollbar = to_filter(show_scrollbar)
        self.display_arrows = to_filter(display_arrows)
        self.up_arrow_symbol = up_arrow_symbol
        self.down_arrow_symbol = down_arrow_symbol

        self.vertical_scroll = 0

    def __repr__(self) -> str:
        return f"ScrollablePane({self.content!r})"

    def reset(self) -> None:
        self.content.reset()

    def preferred_width(self, max_available_width: int) -> Dimension:
        if self.width is not None:
            return to_dimension(self.width)

        # We're only scrolling vertical. So the preferred width is equal to
        # that of the content.
        content_width = self.content.preferred_width(max_available_width)

        # If a scrollbar needs to be displayed, add +1 to the content width.
        if self.show_scrollbar():
            return sum_layout_dimensions([Dimension.exact(1), content_width])

        return content_width

    def preferred_height(self, width: int, max_available_height: int) -> Dimension:
        if self.height is not None:
            return to_dimension(self.height)

        # Prefer a height large enough so that it fits all the content. If not,
        # we'll make the pane scrollable.
        if self.show_scrollbar():
            # If `show_scrollbar` is set. Always reserve space for the scrollbar.
            width -= 1

        dimension = self.content.preferred_height(width, self.max_available_height)

        # Only take 'preferred' into account. Min/max can be anything.
        return Dimension(min=0, preferred=dimension.preferred)

    def write_to_screen(
        self,
        screen: Screen,
        mouse_handlers: MouseHandlers,
        write_position: WritePosition,
        parent_style: str,
        erase_bg: bool,
        z_index: int | None,
    ) -> None:
        """
        Render scrollable pane content.

        The content is drawn straight onto `screen`, at its full height,
        `vertical_scroll` rows above the pane. The rows that land outside the
        pane are dropped, and everything else is in the coordinates of
        `screen` already, so nothing has to be copied afterwards. A window
        that is only partly visible reports its whole size at its real place,
        which is the answer a caller asking "what is drawn here" needs.
        """
        show_scrollbar = self.show_scrollbar()

        if show_scrollbar:
            virtual_width = write_position.width - 1
        else:
            virtual_width = write_position.width

        # Compute preferred height again.
        virtual_height = self.content.preferred_height(
            virtual_width, self.max_available_height
        ).preferred

        # Ensure virtual height is at least the available height.
        virtual_height = max(virtual_height, write_position.height)
        virtual_height = min(virtual_height, self.max_available_height)

        self._scroll_to_focused_window(
            write_position,
            virtual_width,
            virtual_height,
            parent_style,
            erase_bg,
            z_index,
        )

        # Paint the pane, then draw the content over it. The screen this
        # replaced had a default character of its own and every cell of the
        # pane was copied off it, so the pane has always painted its whole
        # area, whether the content reached a cell or not.
        clipped = _ClippedScreen(screen, write_position)
        self._erase(clipped, write_position, virtual_width, parent_style)

        self.content.write_to_screen(
            clipped,
            _clipped_mouse_handlers(mouse_handlers, write_position),
            WritePosition(
                xpos=write_position.xpos,
                ypos=write_position.ypos - self.vertical_scroll,
                width=virtual_width,
                height=virtual_height,
            ),
            parent_style,
            erase_bg,
            z_index,
        )
        clipped.draw_all_floats()

        # Set screen.width/height. The pane is as tall as its own position,
        # whatever the content that was drawn past it says.
        ypos = write_position.ypos
        xpos = write_position.xpos

        screen.width = max(screen.width, xpos + virtual_width)
        screen.height = max(screen.height, ypos + write_position.height)

        if clipped.show_cursor:
            screen.show_cursor = True

        # Take over cursor positions, if they are visible.
        for window, point in clipped.cursor_positions.items():
            if (
                xpos <= point.x < xpos + write_position.width
                and ypos <= point.y < ypos + write_position.height
            ):
                screen.cursor_positions[window] = point

        # Take over menu positions, but clip them to the visible area.
        for window, point in clipped.menu_positions.items():
            screen.menu_positions[window] = self._clip_point_to_visible_area(
                point, write_position
            )

        # Draw scrollbar.
        if show_scrollbar:
            self._draw_scrollbar(
                write_position,
                virtual_height,
                screen,
            )

    def _scroll_to_focused_window(
        self,
        write_position: WritePosition,
        virtual_width: int,
        virtual_height: int,
        parent_style: str,
        erase_bg: bool,
        z_index: int | None,
    ) -> None:
        """
        Scroll so that the focused window is visible.

        Where a window sits in the content, and where its cursor is, are known
        only after that window has rendered. So the content is rendered once
        onto a screen that is thrown away. That screen is a ruler: nothing is
        copied off it, and the frame the user sees is drawn afterwards, at the
        scroll it decided.

        The alternative is to draw first and scroll after, which shows the
        previous view for one frame every time the pane scrolls.
        """
        from prompt_toolkit.application import get_app

        focused_window = get_app().layout.current_window

        ruler = Screen(default_char=Char(char=" ", style=parent_style))
        self.content.write_to_screen(
            ruler,
            MouseHandlers(),
            WritePosition(xpos=0, ypos=0, width=virtual_width, height=virtual_height),
            parent_style,
            erase_bg,
            z_index,
        )
        ruler.draw_all_floats()

        try:
            visible_win_write_pos = ruler.visible_windows_to_write_positions[
                focused_window
            ]
        except KeyError:
            return  # No window focused here. Don't scroll.

        self._make_window_visible(
            write_position.height,
            virtual_height,
            visible_win_write_pos,
            ruler.cursor_positions.get(focused_window),
        )

    def _erase(
        self,
        screen: Screen,
        write_position: WritePosition,
        virtual_width: int,
        parent_style: str,
    ) -> None:
        """
        Fill the area of the pane, before the content is drawn on it.

        The column of the scrollbar is left out, because the scrollbar is
        drawn there afterwards.
        """
        char = _CHAR_CACHE[" ", parent_style]
        data_buffer = screen.data_buffer

        for y in range(
            write_position.ypos, write_position.ypos + write_position.height
        ):
            row = data_buffer[y]
            for x in range(write_position.xpos, write_position.xpos + virtual_width):
                row[x] = char

    def _clip_point_to_visible_area(
        self, point: Point, write_position: WritePosition
    ) -> Point:
        """
        Ensure that the cursor and menu positions always are always reported
        """
        if point.x < write_position.xpos:
            point = point._replace(x=write_position.xpos)
        if point.y < write_position.ypos:
            point = point._replace(y=write_position.ypos)
        if point.x >= write_position.xpos + write_position.width:
            point = point._replace(x=write_position.xpos + write_position.width - 1)
        if point.y >= write_position.ypos + write_position.height:
            point = point._replace(y=write_position.ypos + write_position.height - 1)

        return point

    def is_modal(self) -> bool:
        return self.content.is_modal()

    def get_key_bindings(self) -> KeyBindingsBase | None:
        return self.content.get_key_bindings()

    def get_children(self) -> list[Container]:
        return [self.content]

    def _make_window_visible(
        self,
        visible_height: int,
        virtual_height: int,
        visible_win_write_pos: WritePosition,
        cursor_position: Point | None,
    ) -> None:
        """
        Scroll the scrollable pane, so that this window becomes visible.

        :param visible_height: Height of this `ScrollablePane` that is rendered.
        :param virtual_height: Height of the whole content.
        :param visible_win_write_pos: `WritePosition` of the nested window on
            the ruler screen.
        :param cursor_position: The location of the cursor position of this
            window on the ruler screen.
        """
        # Start with maximum allowed scroll range, and then reduce according to
        # the focused window and cursor position.
        min_scroll = 0
        max_scroll = virtual_height - visible_height

        if self.keep_cursor_visible():
            # Reduce min/max scroll according to the cursor in the focused window.
            if cursor_position is not None:
                offsets = self.scroll_offsets
                cpos_min_scroll = (
                    cursor_position.y - visible_height + 1 + offsets.bottom
                )
                cpos_max_scroll = cursor_position.y - offsets.top
                min_scroll = max(min_scroll, cpos_min_scroll)
                max_scroll = max(0, min(max_scroll, cpos_max_scroll))

        if self.keep_focused_window_visible():
            # Reduce min/max scroll according to focused window position.
            # If the window is small enough, bot the top and bottom of the window
            # should be visible.
            if visible_win_write_pos.height <= visible_height:
                window_min_scroll = (
                    visible_win_write_pos.ypos
                    + visible_win_write_pos.height
                    - visible_height
                )
                window_max_scroll = visible_win_write_pos.ypos
            else:
                # Window does not fit on the screen. Make sure at least the whole
                # screen is occupied with this window, and nothing else is shown.
                window_min_scroll = visible_win_write_pos.ypos
                window_max_scroll = (
                    visible_win_write_pos.ypos
                    + visible_win_write_pos.height
                    - visible_height
                )

            min_scroll = max(min_scroll, window_min_scroll)
            max_scroll = min(max_scroll, window_max_scroll)

        if min_scroll > max_scroll:
            min_scroll = max_scroll  # Should not happen.

        # Finally, properly clip the vertical scroll.
        if self.vertical_scroll > max_scroll:
            self.vertical_scroll = max_scroll
        if self.vertical_scroll < min_scroll:
            self.vertical_scroll = min_scroll

    def _draw_scrollbar(
        self, write_position: WritePosition, content_height: int, screen: Screen
    ) -> None:
        """
        Draw the scrollbar on the screen.

        Note: There is some code duplication with the `ScrollbarMargin`
              implementation.
        """

        window_height = write_position.height
        display_arrows = self.display_arrows()

        if display_arrows:
            window_height -= 2

        try:
            fraction_visible = write_position.height / float(content_height)
            fraction_above = self.vertical_scroll / float(content_height)

            scrollbar_height = int(
                min(window_height, max(1, window_height * fraction_visible))
            )
            scrollbar_top = int(window_height * fraction_above)
        except ZeroDivisionError:
            return
        else:

            def is_scroll_button(row: int) -> bool:
                "True if we should display a button on this row."
                return scrollbar_top <= row <= scrollbar_top + scrollbar_height

            xpos = write_position.xpos + write_position.width - 1
            ypos = write_position.ypos
            data_buffer = screen.data_buffer

            # Up arrow.
            if display_arrows:
                data_buffer[ypos][xpos] = Char(
                    self.up_arrow_symbol, "class:scrollbar.arrow"
                )
                ypos += 1

            # Scrollbar body.
            scrollbar_background = "class:scrollbar.background"
            scrollbar_background_start = "class:scrollbar.background,scrollbar.start"
            scrollbar_button = "class:scrollbar.button"
            scrollbar_button_end = "class:scrollbar.button,scrollbar.end"

            for i in range(window_height):
                style = ""
                if is_scroll_button(i):
                    if not is_scroll_button(i + 1):
                        # Give the last cell a different style, because we want
                        # to underline this.
                        style = scrollbar_button_end
                    else:
                        style = scrollbar_button
                else:
                    if is_scroll_button(i + 1):
                        style = scrollbar_background_start
                    else:
                        style = scrollbar_background

                data_buffer[ypos][xpos] = Char(" ", style)
                ypos += 1

            # Down arrow
            if display_arrows:
                data_buffer[ypos][xpos] = Char(
                    self.down_arrow_symbol, "class:scrollbar.arrow"
                )
