"""
Renders the command line on the console.
(Redraws parts of the input line that were changed.)
"""

from __future__ import annotations

from asyncio import FIRST_COMPLETED, Future, ensure_future, sleep, wait
from collections import deque
from collections.abc import Callable, Hashable
from enum import Enum
from typing import TYPE_CHECKING, Any

from prompt_toolkit.application.current import get_app
from prompt_toolkit.cursor_shapes import CursorShape
from prompt_toolkit.data_structures import Point, Size
from prompt_toolkit.filters import FilterOrBool, to_filter
from prompt_toolkit.formatted_text import AnyFormattedText, to_formatted_text
from prompt_toolkit.layout.mouse_handlers import MouseHandlers
from prompt_toolkit.layout.screen import Char, Screen, WritePosition
from prompt_toolkit.output import ColorDepth, Output
from prompt_toolkit.styles import (
    Attrs,
    BaseStyle,
    DummyStyleTransformation,
    StyleTransformation,
)
from prompt_toolkit.token import KeepWhitespace

if TYPE_CHECKING:
    from prompt_toolkit.application import Application
    from prompt_toolkit.layout.layout import Layout


__all__ = [
    "Renderer",
    "print_formatted_text",
]


def _output_screen_diff(
    app: Application[Any],
    output: Output,
    screen: Screen,
    current_pos: Point,
    color_depth: ColorDepth,
    previous_screen: Screen | None,
    last_style: str | None,
    is_done: bool,  # XXX: drop is_done
    full_screen: bool,
    attrs_for_style_string: _StyleStringToAttrsCache,
    style_string_keeps_a_blank: _KeepABlankCellCache,
    size: Size,
    previous_width: int,
) -> tuple[Point, str | None]:
    """
    Render the diff between this screen and the previous screen.

    This takes two `Screen` instances. The one that represents the output like
    it was during the last rendering and one that represents the current
    output raster. Looking at these two `Screen` instances, this function will
    render the difference by calling the appropriate methods of the `Output`
    object that only paint the changes to the terminal.

    This is some performance-critical code which is heavily optimized.
    Don't change things without profiling first.

    :param current_pos: Current cursor position.
    :param last_style: The style string, used for drawing the last drawn
        character.  (Color/attributes.)
    :param attrs_for_style_string: :class:`._StyleStringToAttrsCache` instance.
    :param width: The width of the terminal.
    :param previous_width: The width of the terminal during the last rendering.
    """
    width, height = size.columns, size.rows

    #: Variable for capturing the output.
    write = output.write
    write_raw = output.write_raw

    # Create locals for the most used output methods.
    # (Save expensive attribute lookups.)
    _output_set_attributes = output.set_attributes
    _output_reset_attributes = output.reset_attributes
    _output_cursor_forward = output.cursor_forward
    _output_cursor_up = output.cursor_up
    _output_cursor_backward = output.cursor_backward

    # Whether this frame has anything to say to the terminal yet.
    #
    # **A frame that changes nothing writes nothing.** An application
    #: renders whenever something may have changed, and most of the
    #: time nothing has: a clock that redraws itself every few seconds
    #: says the same word each time. The frame around the painting used
    #: to go out anyway, so such an application wrote "hide the cursor,
    #: reset the attributes, show the cursor" over and over.
    #:
    #: That is not nothing. It wakes the terminal, and a terminal does
    #: more on a read than draw what arrived: xterm advances the phase
    #: of its blinking text, so text a person is reading appears or
    #: disappears for no reason anybody can see.
    writing = False

    # Whether the terminal's cursor column is the one this frame counts.
    # Terminals have their own width tables: an emoji presentation
    # sequence is one column to wcwidth and two to kitty. After a cell
    # they may disagree on, the next write anchors at the line's start,
    # so a disagreement stays in its own cell instead of carrying the
    # rest of the row, and whatever stands beside it, along.
    column_known = True

    def start_writing() -> None:
        """
        The head of a frame, written before the first change of it.

        While the screen is painted the cursor is moved all over it, and
        a cursor that is visible while that happens flickers around the
        screen. There are two ways to stop that.

        A terminal that holds the frame back shows none of the painting,
        so the cursor can stay where it is. That is the better one, and
        not only for flicker: hiding the cursor and showing it again
        restarts the blink in most terminals, and an application that
        renders many times a second then has a cursor that never blinks
        at all.

        Hiding it is the fallback, for a terminal that cannot.
        """
        nonlocal writing

        if not writing:
            writing = True

            if output.synchronized_output:
                output.begin_synchronized_update()
            else:
                output.hide_cursor()

    def reset_attributes() -> None:
        "Wrapper around Output.reset_attributes."
        nonlocal last_style
        start_writing()
        # What the row queued stands before the reset: it was written
        # in the style the reset leaves.
        flush_pending()
        _output_reset_attributes()
        last_style = None  # Forget last char after resetting attributes.

    def move_cursor(new: Point) -> Point:
        "Move cursor to this `new` point. Returns the given Point."
        nonlocal column_known
        start_writing()
        # What the row queued stands before the move: it was written
        # where the cursor was, and the move leaves there.
        flush_pending()
        current_x, current_y = current_pos.x, current_pos.y

        if new.y > current_y:
            # Use newlines instead of CURSOR_DOWN, because this might add new lines.
            # CURSOR_DOWN will never create new lines at the bottom.
            # Also reset attributes, otherwise the newline could draw a
            # background color.
            reset_attributes()
            write("\r\n" * (new.y - current_y))
            current_x = 0
            _output_cursor_forward(new.x)
            column_known = True
            return new
        elif new.y < current_y:
            _output_cursor_up(current_y - new.y)

        if not column_known:
            write("\r")
            _output_cursor_forward(new.x)
            column_known = True
        elif current_x >= width - 1:
            write("\r")
            _output_cursor_forward(new.x)
        elif new.x < current_x or current_x >= width - 1:
            _output_cursor_backward(current_x - new.x)
        elif new.x > current_x:
            _output_cursor_forward(new.x - current_x)

        return new

    def in_row_move_cost(from_x: int, to_x: int) -> int:
        """
        The bytes a move across one row costs, without writing it.

        This counts what `move_cursor` writes for the same move: the
        shapes of `Vt100_Output` -- `\\x1b[C` for one step forward,
        `\\x1b[{n}C` past it, `\\b` for one step back, `\\x1b[{n}D`
        past it, and a carriage return first when the cursor may have
        wrapped. A gap the content crosses for fewer bytes than this
        is written through instead of moved across.
        """
        if from_x >= width - 1:
            forward = to_x
            return 1 + (
                0 if forward == 0 else 3 if forward == 1 else 3 + len(str(forward))
            )
        if to_x < from_x:
            back = from_x - to_x
            return 1 if back == 1 else 3 + len(str(back))
        ahead = to_x - from_x
        return 0 if ahead == 0 else 3 if ahead == 1 else 3 + len(str(ahead))

    def gap_writes_cheaper(
        row: dict[int, Char], escapes_row: dict[int, str], from_x: int, to_x: int
    ) -> bool:
        """
        Whether the unchanged columns from `from_x` to `to_x` go out
        as content instead of a cursor move.

        The cells are unchanged, so writing what the new row holds
        says what the terminal already shows -- but only when it
        costs less than the move across, and only when nothing in the
        gap asks for more than its characters:

        - every cell draws in the running style, so no switch goes
          out and none is owed after;
        - no injected escape stands in the gap, which would need its
          own write anyway;
        - every cell moves the terminal by its columns. A cell with
          no width writes nothing -- the second half of a wide
          character, a combining mark -- so counting it would move
          the books without moving the cursor;
        - the gap stops before the last column. Landing on it would
          call for a move that writes even standing still, so a gap
          that reaches it keeps the forward move it always had.
        """
        if to_x >= width - 1:
            return False
        if to_x - from_x > in_row_move_cost(from_x, to_x):
            return False
        running = attrs_for_style_string[last_style]
        c = from_x
        while c < to_x:
            cell = row[c]
            if c in escapes_row:
                return False
            if not cell.width:
                return False
            if attrs_for_style_string[cell.style] != running:
                return False
            c += cell.width or 1
        return True

    # The characters of one style run, queued for one write. A row
    # with scattered changes paid a cursor move per island and a
    # `write` per cell; the walk below collects the changed spans of
    # the row first and emits one move per span, and the characters
    # of one style go out in one `write`. Lillecarl/pymux#522.
    pending: list[str] = []

    def flush_pending() -> None:
        """
        Write what the row queued, as one write.

        Joining changes no byte: `write` replaces per character, so
        one call with the run writes what one call per character
        would. The run holds one style by construction -- a change of
        it flushes first -- and an injected escape never sits inside
        one: those flush too. Every move and every reset flushes as
        well, so what is queued always stands before them.
        """
        if pending:
            write("".join(pending))
            del pending[:]

    def output_char(char: Char) -> None:
        """
        Queue one cell the way the diff writes it, batched.

        The style switch, when the cell asks for one, goes out before
        what is queued: the queued characters were written in the
        style the switch leaves.
        """
        nonlocal last_style, column_known

        if not _moves_one_column_everywhere(char.char):
            column_known = False

        # If the last queued character has the same style, join it.
        if last_style == char.style:
            pending.append(char.char)
        else:
            # Look up `Attr` for this style string. Only set attributes if different.
            # (Two style strings can still have the same formatting.)
            # Note that an empty style string can have formatting that needs to
            # be applied, because of style transformations.
            new_attrs = attrs_for_style_string[char.style]
            if not last_style or new_attrs != attrs_for_style_string[last_style]:
                flush_pending()
                _output_set_attributes(new_attrs, color_depth)

            last_style = char.style
            pending.append(char.char)

    def get_max_column_index(row: dict[int, Char]) -> int:
        """
        Return max used column index, ignoring whitespace (without style) at
        the end of the line. This is important for people that copy/paste
        terminal output.

        There are two reasons we are sometimes seeing whitespace at the end:
        - `BufferControl` adds a trailing space to each line, because it's a
          possible cursor position, so that the line wrapping won't change if
          the cursor position moves around.
        - The `Window` adds a style class to the current line for highlighting
          (cursor-line).

        Only the columns of the screen count. A `Float` is allowed to be
        partially visible, so `FloatContainer` writes at a negative column
        and past the last one, and `Screen` keeps what it is given. A cell
        nobody can see must not make the row look full: that would draw
        every row to the edge on every frame, and no line would ever be
        short enough to erase.

        A row that holds nothing answers -1, which is the column before
        the first one. The loop below then writes nothing and the trim
        erases from column 0. With 0 the row costs one space instead,
        and a terminal that reads its own screen back sees a cell where
        the program left none.

        A cell can ask to stay with `KeepWhitespace`. A control that
        draws the screen of another program knows which blanks that
        program wrote, and the guess above is wrong for those.
        """
        numbers = (
            index
            for index, cell in row.items()
            if 0 <= index < width
            and (cell.char != " " or style_string_keeps_a_blank[cell.style])
        )
        return max(numbers, default=-1)

    # Render for the first time: reset styling.
    if not previous_screen:
        reset_attributes()

    # Disable autowrap. (When entering a the alternate screen, or anytime when
    # we have a prompt. - In the case of a REPL, like IPython, people can have
    # background threads, and it's hard for debugging if their output is not
    # wrapped.)
    if not previous_screen or not full_screen:
        start_writing()
        output.disable_autowrap()

    # When the previous screen has a different size, redraw everything anyway.
    # Also when we are done. (We might take up less rows, so clearing is important.)
    if (
        is_done or not previous_screen or previous_width != width
    ):  # XXX: also consider height??
        if full_screen:
            # Say where the cursor goes, rather than walking it there.
            #
            # `move_cursor` counts from `current_pos`, which is where
            # the last frame left the cursor. One thing moves the cursor
            # between two frames without saying so: a terminal that
            # changes size moves it itself. A terminal that reflows
            # joins the lines it had wrapped and carries the cursor with
            # them, and one that does not still clamps it to the new
            # width. A relative move then lands somewhere else, the
            # erase below keeps a piece of the old screen, and the
            # redraw is written beside it instead of over it.
            #
            # A full screen application owns the screen, so it can name
            # the position. The other branch cannot: the layout starts
            # wherever the cursor stood.
            start_writing()
            output.cursor_goto(0, 0)
            current_pos = Point(x=0, y=0)
        else:
            current_pos = move_cursor(Point(x=0, y=0))
        reset_attributes()
        output.erase_down()

        previous_screen = Screen()

    # Get height of the screen.
    # (height changes as we loop over data_buffer, so remember the current value.)
    # (Also make sure to clip the height to the size of the output.)
    current_height = min(screen.height, height)

    # Loop over the rows.
    row_count = min(max(screen.height, previous_screen.height), height)

    # The widths the previous frame measured, which travel on the
    # screen itself: it is the same object that was the new one then,
    # so a row nobody touched still ends where it did. The widths this
    # frame measures go onto the new screen for the next one.
    previous_max_index = previous_screen.max_column_index
    max_index = screen.max_column_index

    # Where the cursor stands, as plain integers. The loop below
    # walks cell by cell, and a `Point` for every changed one is a
    # tuple each. `current_pos` is synced where a move reads it and
    # after the rows, and nowhere else.
    cur_x = current_pos.x
    cur_y = current_pos.y

    # Scroll sequences for shifted rows: one region set-up and one
    # scroll per scrolled region instead of a repaint per row. The
    # copy recorded which screen rows each reported scroll covers;
    # each region is verified cell for cell, scrolled past, and the
    # committed rows are rotated to match, so the loop below finds
    # them unchanged and only the uncovered rows repaint. Anything a
    # region does not prove repaints as before. Only a terminal that
    # scrolls regions is asked: anywhere else the repaint it replaces
    # stays home.
    # Lillecarl/pymux#518.
    scroll_regions = getattr(screen, "scroll_regions", None) or []
    if not getattr(output, "scroll_regions_support", False):
        scroll_regions = []
    # Uncovered rows, painted by the loop below and adopted after it:
    # adopting first would tell the loop nothing differs while the
    # terminal still shows the scroll's blanks.
    adopt_rows: list[int] = []
    for stop, sbottom, sdistance in sorted(scroll_regions):
        if sdistance == 0 or not (0 <= stop <= sbottom < height):
            continue
        if sdistance > 0:
            first, last = stop, sbottom - sdistance
        else:
            first, last = stop - sdistance, sbottom
        if first > last:
            continue
        new_buffer = screen.data_buffer
        prev_buffer = previous_screen.data_buffer
        shifted = True
        for r in range(first, last + 1):
            # `.get` reads without writing: the rows are defaultdicts,
            # and a row the walk never reaches must not appear for it.
            prev_row = prev_buffer.get(r + sdistance)
            new_row = new_buffer.get(r)
            if prev_row is None or new_row is None or new_row != prev_row:
                shifted = False
                break
        if not shifted:
            continue
        # No injected escape may ride along: scrolling moves cells,
        # and an escape is terminal state, not a cell. The rows read
        # as present but empty: the loop below touches every row it
        # walks, so only a row with something in it counts.
        zero_new = screen.zero_width_escapes
        zero_prev = previous_screen.zero_width_escapes
        if any(zero_new.get(r) or zero_prev.get(r) for r in range(stop, sbottom + 1)):
            continue
        # The cursor opens the frame and stands at the top of the
        # region; the scroll goes out whole, whatever it moves. No
        # margins are set coming in: the region before gave its own
        # back, because a move below walks through them and every
        # linefeed at the bottom margin would scroll them again.
        current_pos = Point(x=cur_x, y=cur_y)
        current_pos = move_cursor(Point(x=0, y=stop))
        cur_x, cur_y = 0, stop
        if stop > 0 or sbottom < height - 1:
            write_raw(f"\x1b[{stop + 1};{sbottom + 1}r")
        if sdistance == 1:
            write_raw("\x1b[S")
        elif sdistance == -1:
            write_raw("\x1b[T")
        elif sdistance > 0:
            write_raw(f"\x1b[{sdistance}S")
        else:
            write_raw(f"\x1b[{-sdistance}T")
        if stop > 0 or sbottom < height - 1:
            write_raw("\x1b[r")
            # Setting the margins homes the cursor, and so does
            # giving them back, so the books stand at home with it.
            # Origin mode would move home to the top of the region
            # instead, but no screen this draws ever sets it. A scroll
            # on the whole screen sets nothing and moves nothing.
            current_pos = Point(x=0, y=0)
            cur_x, cur_y = 0, 0
            column_known = True
        # The committed rows follow the terminal: shifted rows move
        # now. Uncovered rows go back to blank: the scroll emptied
        # them on the terminal, so the loop below repaints them whole
        # and adopts them after it.
        moved_rows: dict[int, Any] = {}
        for r in range(first, last + 1):
            moved_rows[r] = prev_buffer[r + sdistance]
        for r in range(stop, sbottom + 1):
            if r in moved_rows:
                prev_buffer[r] = moved_rows[r]
            else:
                prev_buffer.pop(r, None)
                adopt_rows.append(r)
        moved_measures: dict[int, int] = {}
        for r in range(first, last + 1):
            if r + sdistance in previous_max_index:
                moved_measures[r] = previous_max_index[r + sdistance]
        for r in range(stop, sbottom + 1):
            if r in moved_measures:
                previous_max_index[r] = moved_measures[r]
            else:
                previous_max_index.pop(r, None)

    for y in range(row_count):
        new_row = screen.data_buffer[y]
        previous_row = previous_screen.data_buffer[y]
        zero_width_escapes_row = screen.zero_width_escapes[y]

        # A row that did not change needs no work at all. The
        # comparison runs in C and stops at the first cell that
        # differs, and two equal cells are usually the same object, so
        # it costs far less than the loop below. Between two renders
        # most rows of a screen stay as they were.
        if not zero_width_escapes_row and new_row == previous_row:
            # Unchanged, so it ends where it did. Carried forward for
            # the frame after this one, which may be the one that
            # changes it.
            if y in previous_max_index:
                max_index[y] = previous_max_index[y]
            continue

        new_max: int
        try:
            # A row the copy reached carries how far it wrote, and so
            # do the fills. That is an upper bound, not the measure: a
            # copy cannot tell a blank the walk would skip, because
            # that depends on what the style draws, which only this
            # side knows. So step back over the trailing blanks, which
            # costs the blanks and not the row. A row nobody speaks of
            # -- erased fills, single cells, or nothing at all -- is
            # measured as before.
            new_max = min(max_index[y], width - 1)
            while new_max >= 0:
                cell = new_row.get(new_max)
                if cell is not None and (
                    cell.char != " " or style_string_keeps_a_blank[cell.style]
                ):
                    break
                new_max -= 1
        except KeyError:
            new_max = get_max_column_index(new_row)
        max_index[y] = new_max
        new_max_line_len = min(width - 1, new_max)

        # The changed spans of the row: maximal runs of adjacent
        # changed columns, collected before anything is written. The
        # walk already visits every column; buffering the decisions
        # per row is what lets one span go out in one move and one
        # write instead of one of each per cell. One tuple per span,
        # not per cell: a full redraw makes every cell changed, and
        # a tuple each would be thirty million of them.
        spans: list[tuple[int, int]] = []
        span_start = -1
        c = 0  # Column counter.
        while c <= new_max_line_len:
            new_char = new_row[c]
            old_char = previous_row[c]
            char_width = new_char.width or 1

            # When the old and new character at this position are different,
            # draw the output. (Because of the performance, we don't call
            # `Char.__ne__`, but inline the same expression.) The same
            # object draws the same cell, and the cache hands out one
            # object per way of drawing, so an unchanged cell answers
            # with one pointer comparison and reads nothing at all.
            if new_char is not old_char and (
                new_char.char != old_char.char or new_char.style != old_char.style
            ):
                if span_start < 0:
                    span_start = c
            elif span_start >= 0:
                spans.append((span_start, c))
                span_start = -1

            c += char_width

        if span_start >= 0:
            spans.append((span_start, c))

        for start, end in spans:
            # The gap since the cursor stands on this row: when its
            # cells cost less written than moved across, they go out
            # as content and the span joins them in one write. The
            # cells are unchanged, so writing what the row holds says
            # what the terminal shows. Anything else keeps its move:
            # a gap on another row, one past an unknown style, or one
            # the move crosses for fewer bytes.
            if (
                y == cur_y
                and start > cur_x
                and last_style is not None
                and column_known
                and gap_writes_cheaper(new_row, zero_width_escapes_row, cur_x, start)
            ):
                while cur_x < start:
                    gap_char = new_row[cur_x]
                    output_char(gap_char)
                    cur_x += gap_char.width or 1
            # The cursor is usually already here: the cell before
            # this one was just drawn. Moving it again would write
            # the same, so only a gap -- or the last column, where
            # a move writes even standing still -- calls for one.
            # A frame that has written nothing yet always moves:
            # the move opens the frame.
            elif not (
                writing
                and column_known
                and start == cur_x
                and y == cur_y
                and start < width - 1
            ):
                current_pos = Point(x=cur_x, y=cur_y)
                current_pos = move_cursor(Point(x=start, y=y))
                cur_x, cur_y = start, y

            # The span itself, cell by cell into one style run at a
            # time. The cursor marches with what is written, so no
            # span pays a move inside -- except on the last column,
            # where standing still still writes, as above. The first
            # cell is positioned above and never checked again: it
            # would call for a second move, standing where the first
            # one left it.
            c = start
            while c < end:
                span_char = new_row[c]
                span_width = span_char.width or 1
                if c > start and not (
                    writing
                    and column_known
                    and c == cur_x
                    and y == cur_y
                    and c < width - 1
                ):
                    current_pos = Point(x=cur_x, y=cur_y)
                    current_pos = move_cursor(Point(x=c, y=y))
                    cur_x, cur_y = c, y

                # Send injected escape sequences to output.
                if c in zero_width_escapes_row:
                    flush_pending()
                    write_raw(zero_width_escapes_row[c])

                output_char(span_char)
                cur_x += span_width

                c += span_width

        # What the spans queued goes out before the tail: the erase
        # moves first, and what is queued stands before the move.
        flush_pending()

        # Finish the row to the end of the line. The cells past what
        # this row wrote are not this row: the erase of the first
        # frame left them the terminal's default, and so did the tail
        # of an earlier, longer row. A row that is shorter than the one
        # before is the visible case, but a row the first frame never
        # reached and one that grew past a trim are the same, so every
        # row this frame touched erases its own tail.
        #
        # The erase carries the tail's own background. A fill painted
        # those cells with the window behind them, and a reset would
        # blot them out with the terminal's default instead, on every
        # row the program left empty. A tail nobody painted erases as
        # before.
        #
        # `.get` reads the row without writing to it: the rows are
        # defaultdicts, and an access that stores the default would
        # make the next frame read this one back as changed.
        if new_max_line_len < width - 1:
            current_pos = Point(x=cur_x, y=cur_y)
            current_pos = move_cursor(Point(x=new_max_line_len + 1, y=y))
            cur_x, cur_y = new_max_line_len + 1, y
            tail_style: str | None = None
            for tail in range(new_max_line_len + 1, width):
                tail_char = new_row.get(tail)
                if tail_char is None:
                    continue
                if attrs_for_style_string[tail_char.style].bgcolor is not None:
                    tail_style = tail_char.style
                break
            if tail_style is None:
                reset_attributes()
            else:
                tail_attrs = attrs_for_style_string[tail_style]
                if not last_style or tail_attrs != attrs_for_style_string[last_style]:
                    _output_set_attributes(tail_attrs, color_depth)
                last_style = tail_style
            output.erase_end_of_line()

    current_pos = Point(x=cur_x, y=cur_y)

    # Uncovered rows painted above are adopted now: the loop paints
    # what differs, so what it painted is what the terminal shows,
    # and the next frame finds it instead of painting it again.
    if adopt_rows:
        adopt_new = screen.data_buffer
        adopt_prev = previous_screen.data_buffer
        for r in adopt_rows:
            adopted = adopt_new.get(r)
            if adopted is None:
                adopt_prev.pop(r, None)
                previous_max_index.pop(r, None)
            else:
                adopt_prev[r] = adopted
                if max_index.get(r) is not None:
                    previous_max_index[r] = max_index[r]
                else:
                    previous_max_index.pop(r, None)

    # Correctly reserve vertical space as required by the layout.
    # When this is a new screen (drawn for the first time), or for some reason
    # higher than the previous one. Move the cursor once to the bottom of the
    # output. That way, we're sure that the terminal scrolls up, even when the
    # lower lines of the canvas just contain whitespace.

    # The most obvious reason that we actually want this behavior is the avoid
    # the artifact of the input scrolling when the completion menu is shown.
    # (If the scrolling is actually wanted, the layout can still be build in a
    # way to behave that way by setting a dynamic height.)
    if current_height > previous_screen.height:
        current_pos = move_cursor(Point(x=0, y=current_height - 1))

    # Move cursor:
    if is_done:
        current_pos = move_cursor(Point(x=0, y=current_height))
        output.erase_down()
    else:
        # A cursor that is already where the screen wants it stays
        # where it is. `move_cursor` writes for a position it holds
        # already when that position is the last column, and a frame
        # that changes nothing must write nothing.
        wanted = screen.get_cursor_position(app.layout.current_window)
        if wanted != current_pos or not column_known:
            current_pos = move_cursor(wanted)

    if writing:
        if is_done or not full_screen:
            output.enable_autowrap()

        # Always reset the color attributes. This is important because a
        # background thread could print data to stdout and we want that to be
        # displayed in the default colors. (Also, if a background color has
        # been set, many terminals give weird artifacts on resize events.)
        reset_attributes()

    # What the screen asks for. Without synchronised output the cursor
    # was hidden above, so this is what puts it back; with it, `hide` and
    # `show` write only when the answer has changed, so a screen that
    # keeps the cursor visible says nothing about it frame after frame.
    # A frame that painted nothing hid nothing either, so this asks for
    # what the screen holds and writes only when that has changed.
    if screen.show_cursor:
        output.show_cursor()
    else:
        output.hide_cursor()

    if writing:
        output.end_synchronized_update()

    return current_pos, last_style


def _moves_one_column_everywhere(text: str) -> bool:
    """
    Whether every terminal moves its cursor one column for this cell.

    One code point below U+2300 does: Latin, Greek, Cyrillic, the
    general punctuation. So do box drawing and the block elements, which
    every terminal draws in one cell outside a CJK locale. Anything else
    may be drawn wider by a terminal whose width table disagrees with
    this one's: an emoji, a symbol with an emoji form such as U+2733,
    and any cell of more than one code point -- a variation selector, a
    joiner, a combining mark.
    """
    if len(text) != 1:
        return False
    if " " <= text <= "~":
        return True
    point = ord(text)
    return 0xA0 <= point < 0x2300 or 0x2500 <= point < 0x25A0


class HeightIsUnknownError(Exception):
    "Information unavailable. Did not yet receive the CPR response."


class _StyleStringToAttrsCache(dict[str, Attrs]):
    """
    A cache structure that maps style strings to :class:`.Attr`.
    (This is an important speed up.)
    """

    def __init__(
        self,
        get_attrs_for_style_str: Callable[[str], Attrs],
        style_transformation: StyleTransformation,
    ) -> None:
        self.get_attrs_for_style_str = get_attrs_for_style_str
        self.style_transformation = style_transformation

    def __missing__(self, style_str: str) -> Attrs:
        attrs = self.get_attrs_for_style_str(style_str)
        attrs = self.style_transformation.transform_attrs(attrs)

        self[style_str] = attrs
        return attrs


class _KeepABlankCellCache(dict[str, bool]):
    """
    Cache for remember which style strings keep a cell that holds a space.

    Two things keep such a cell. The style renders something other than
    the default output style (default fg/bg, no underline and no reverse
    and no blink), so the terminal has to draw it. Or the cell carries
    `KeepWhitespace`, which says that a program wrote the space and the
    screen has to hold it.

    Note: we don't consider bold/italic/hidden because they don't change the
    output if there's no text in the cell.
    """

    def __init__(self, style_string_to_attrs: dict[str, Attrs]) -> None:
        self.style_string_to_attrs = style_string_to_attrs

    def __missing__(self, style_str: str) -> bool:
        attrs = self.style_string_to_attrs[style_str]
        keep = bool(
            attrs.color
            or attrs.bgcolor
            or attrs.underline
            or attrs.strike
            or attrs.blink
            or attrs.reverse
        ) or (KeepWhitespace in style_str)

        self[style_str] = keep
        return keep


class CPR_Support(Enum):
    "Enum: whether or not CPR is supported."

    SUPPORTED = "SUPPORTED"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    UNKNOWN = "UNKNOWN"


class Renderer:
    """
    Typical usage:

    ::

        output = Vt100_Output.from_pty(sys.stdout)
        r = Renderer(style, output)
        r.render(app, layout=...)
    """

    CPR_TIMEOUT = 2  # Time to wait until we consider CPR to be not supported.

    def __init__(
        self,
        style: BaseStyle,
        output: Output,
        full_screen: bool = False,
        mouse_support: FilterOrBool = False,
        cpr_not_supported_callback: Callable[[], None] | None = None,
    ) -> None:
        self.style = style
        self.output = output
        self.full_screen = full_screen
        self.mouse_support = to_filter(mouse_support)
        self.cpr_not_supported_callback = cpr_not_supported_callback

        # TODO: Move following state flags into `Vt100_Output`, similar to
        #       `_cursor_shape_changed` and `_cursor_visible`. But then also
        #       adjust the `Win32Output` to not call win32 APIs if nothing has
        #       to be changed.

        self._in_alternate_screen = False
        self._mouse_support_enabled = False
        self._bracketed_paste_enabled = False
        self._cursor_key_mode_reset = False

        # Future set when we are waiting for a CPR flag.
        self._waiting_for_cpr_futures: deque[Future[None]] = deque()
        self.cpr_support = CPR_Support.UNKNOWN

        if not output.responds_to_cpr:
            self.cpr_support = CPR_Support.NOT_SUPPORTED

        # Cache for the style.
        self._attrs_for_style: _StyleStringToAttrsCache | None = None
        self._style_string_keeps_a_blank: _KeepABlankCellCache | None = None
        self._last_style_hash: Hashable | None = None
        self._last_transformation_hash: Hashable | None = None
        self._last_color_depth: ColorDepth | None = None

        self.reset(_scroll=True)

    def reset(self, _scroll: bool = False, leave_alternate_screen: bool = True) -> None:
        # Reset position
        self._cursor_pos = Point(x=0, y=0)

        # Remember the last screen instance between renderers. This way,
        # we can create a `diff` between two screens and only output the
        # difference. It's also to remember the last height. (To show for
        # instance a toolbar at the bottom position.)
        self._last_screen: Screen | None = None
        self._last_size: Size | None = None
        self._last_style: str | None = None
        self._last_cursor_shape: CursorShape | None = None

        # Default MouseHandlers. (Just empty.)
        self.mouse_handlers = MouseHandlers()

        #: Space from the top of the layout, until the bottom of the terminal.
        #: We don't know this until a `report_absolute_cursor_row` call.
        self._min_available_height = 0

        # In case of Windows, also make sure to scroll to the current cursor
        # position. (Only when rendering the first time.)
        # It does nothing for vt100 terminals.
        if _scroll:
            self.output.scroll_buffer_to_prompt()

        # Quit alternate screen.
        if self._in_alternate_screen and leave_alternate_screen:
            self.output.quit_alternate_screen()
            self._in_alternate_screen = False

        # Disable mouse support.
        if self._mouse_support_enabled:
            self.output.disable_mouse_support()
            self._mouse_support_enabled = False

        # Disable bracketed paste.
        if self._bracketed_paste_enabled:
            self.output.disable_bracketed_paste()
            self._bracketed_paste_enabled = False

        self.output.reset_cursor_shape()
        self.output.show_cursor()

        # NOTE: No need to set/reset cursor key mode here.

        # Flush output. `disable_mouse_support` needs to write to stdout.
        self.output.flush()

    @property
    def last_rendered_screen(self) -> Screen | None:
        """
        The `Screen` class that was generated during the last rendering.
        This can be `None`.
        """
        return self._last_screen

    @property
    def height_is_known(self) -> bool:
        """
        True when the height from the cursor until the bottom of the terminal
        is known. (It's often nicer to draw bottom toolbars only if the height
        is known, in order to avoid flickering when the CPR response arrives.)
        """
        if self.full_screen or self._min_available_height > 0:
            return True
        try:
            self._min_available_height = self.output.get_rows_below_cursor_position()
            return True
        except NotImplementedError:
            return False

    @property
    def rows_above_layout(self) -> int:
        """
        Return the number of rows visible in the terminal above the layout.
        """
        if self._in_alternate_screen:
            return 0
        elif self._min_available_height > 0:
            total_rows = self.output.get_size().rows
            last_screen_height = self._last_screen.height if self._last_screen else 0
            return total_rows - max(self._min_available_height, last_screen_height)
        else:
            raise HeightIsUnknownError("Rows above layout is unknown.")

    def request_absolute_cursor_position(self) -> None:
        """
        Get current cursor position.

        We do this to calculate the minimum available height that we can
        consume for rendering the prompt. This is the available space below te
        cursor.

        For vt100: Do CPR request. (answer will arrive later.)
        For win32: Do API call. (Answer comes immediately.)
        """
        # Only do this request when the cursor is at the top row. (after a
        # clear or reset). We will rely on that in `report_absolute_cursor_row`.
        assert self._cursor_pos.y == 0

        # In full-screen mode, always use the total height as min-available-height.
        if self.full_screen:
            self._min_available_height = self.output.get_size().rows
            return

        # For Win32, we have an API call to get the number of rows below the
        # cursor.
        try:
            self._min_available_height = self.output.get_rows_below_cursor_position()
            return
        except NotImplementedError:
            pass

        # Use CPR.
        if self.cpr_support == CPR_Support.NOT_SUPPORTED:
            return

        def do_cpr() -> None:
            # Asks for a cursor position report (CPR).
            self._waiting_for_cpr_futures.append(Future())
            self.output.ask_for_cpr()

        if self.cpr_support == CPR_Support.SUPPORTED:
            do_cpr()
            return

        # If we don't know whether CPR is supported, only do a request if
        # none is pending, and test it, using a timer.
        if self.waiting_for_cpr:
            return

        do_cpr()

        async def timer() -> None:
            await sleep(self.CPR_TIMEOUT)

            # Not set in the meantime -> not supported.
            if self.cpr_support == CPR_Support.UNKNOWN:
                self.cpr_support = CPR_Support.NOT_SUPPORTED

                if self.cpr_not_supported_callback:
                    # Make sure to call this callback in the main thread.
                    self.cpr_not_supported_callback()

        get_app().create_background_task(timer())

    def report_absolute_cursor_row(self, row: int) -> None:
        """
        To be called when we know the absolute cursor position.
        (As an answer of a "Cursor Position Request" response.)
        """
        self.cpr_support = CPR_Support.SUPPORTED

        # Calculate the amount of rows from the cursor position until the
        # bottom of the terminal.
        total_rows = self.output.get_size().rows
        rows_below_cursor = total_rows - row + 1

        # Set the minimum available height.
        self._min_available_height = rows_below_cursor

        # Pop and set waiting for CPR future.
        try:
            f = self._waiting_for_cpr_futures.popleft()
        except IndexError:
            pass  # Received CPR response without having a CPR.
        else:
            f.set_result(None)

    @property
    def waiting_for_cpr(self) -> bool:
        """
        Waiting for CPR flag. True when we send the request, but didn't got a
        response.
        """
        return bool(self._waiting_for_cpr_futures)

    async def wait_for_cpr_responses(self, timeout: int = 1) -> None:
        """
        Wait for a CPR response.
        """
        cpr_futures = list(self._waiting_for_cpr_futures)  # Make copy.

        # When there are no CPRs in the queue. Don't do anything.
        if not cpr_futures or self.cpr_support == CPR_Support.NOT_SUPPORTED:
            return None

        async def wait_for_responses() -> None:
            for response_f in cpr_futures:
                await response_f

        async def wait_for_timeout() -> None:
            await sleep(timeout)

            # Got timeout, erase queue.
            for response_f in cpr_futures:
                response_f.cancel()
            self._waiting_for_cpr_futures = deque()

        tasks = {
            ensure_future(wait_for_responses()),
            ensure_future(wait_for_timeout()),
        }
        _, pending = await wait(tasks, return_when=FIRST_COMPLETED)
        for task in pending:
            task.cancel()

    def render(
        self, app: Application[Any], layout: Layout, is_done: bool = False
    ) -> None:
        """
        Render the current interface to the output.

        :param is_done: When True, put the cursor at the end of the interface. We
                won't print any changes to this part.
        """
        output = self.output

        # A frame asked for before input arrived is already stale: drawing
        # it first would only delay what the input changes, so this asks
        # for another frame instead, which the input's own handling
        # brings. An application that never sets the hook draws as
        # always. A first frame and a teardown always draw: nothing
        # committed could be stale.
        should_skip = app.should_skip_render
        if not is_done and self._last_screen is not None and should_skip is not None and should_skip():
            app.invalidate()
            return

        # Enter alternate screen.
        if self.full_screen and not self._in_alternate_screen:
            self._in_alternate_screen = True
            output.enter_alternate_screen()

        # Enable bracketed paste.
        if not self._bracketed_paste_enabled:
            self.output.enable_bracketed_paste()
            self._bracketed_paste_enabled = True

        # Reset cursor key mode.
        if not self._cursor_key_mode_reset:
            self.output.reset_cursor_key_mode()
            self._cursor_key_mode_reset = True

        # Enable/disable mouse support.
        needs_mouse_support = self.mouse_support()

        if needs_mouse_support and not self._mouse_support_enabled:
            output.enable_mouse_support()
            self._mouse_support_enabled = True

        elif not needs_mouse_support and self._mouse_support_enabled:
            output.disable_mouse_support()
            self._mouse_support_enabled = False

        # Create screen and write layout to it.
        size = output.get_size()
        screen = Screen()
        screen.visible_width = size.columns
        screen.show_cursor = False  # Hide cursor by default, unless one of the
        # containers decides to display it.
        mouse_handlers = MouseHandlers()

        # Calculate height.
        if self.full_screen:
            height = size.rows
        elif is_done:
            # When we are done, we don't necessary want to fill up until the bottom.
            height = layout.container.preferred_height(
                size.columns, size.rows
            ).preferred
        else:
            last_height = self._last_screen.height if self._last_screen else 0
            height = max(
                self._min_available_height,
                last_height,
                layout.container.preferred_height(size.columns, size.rows).preferred,
            )

        height = min(height, size.rows)

        # When the size changes, don't consider the previous screen.
        if self._last_size != size:
            self._last_screen = None

        # When we render using another style or another color depth, do a full
        # repaint. (Forget about the previous rendered screen.)
        # (But note that we still use _last_screen to calculate the height.)
        if (
            self.style.invalidation_hash() != self._last_style_hash
            or app.style_transformation.invalidation_hash()
            != self._last_transformation_hash
            or app.color_depth != self._last_color_depth
        ):
            self._last_screen = None
            self._attrs_for_style = None
            self._style_string_keeps_a_blank = None

        if self._attrs_for_style is None:
            self._attrs_for_style = _StyleStringToAttrsCache(
                self.style.get_attrs_for_style_str, app.style_transformation
            )
        if self._style_string_keeps_a_blank is None:
            self._style_string_keeps_a_blank = _KeepABlankCellCache(
                self._attrs_for_style
            )

        self._last_style_hash = self.style.invalidation_hash()
        self._last_transformation_hash = app.style_transformation.invalidation_hash()
        self._last_color_depth = app.color_depth

        layout.container.write_to_screen(
            screen,
            mouse_handlers,
            WritePosition(xpos=0, ypos=0, width=size.columns, height=height),
            parent_style="",
            erase_bg=False,
            z_index=None,
        )
        screen.draw_all_floats()

        # When grayed. Replace all styles in the new screen.
        if app.exit_style:
            screen.append_style_to_content(app.exit_style)

        # Process diff and write to output.
        self._cursor_pos, self._last_style = _output_screen_diff(
            app,
            output,
            screen,
            self._cursor_pos,
            app.color_depth,
            self._last_screen,
            self._last_style,
            is_done,
            full_screen=self.full_screen,
            attrs_for_style_string=self._attrs_for_style,
            style_string_keeps_a_blank=self._style_string_keeps_a_blank,
            size=size,
            previous_width=(self._last_size.columns if self._last_size else 0),
        )
        self._last_screen = screen
        self._last_size = size
        self.mouse_handlers = mouse_handlers

        # Handle cursor shapes.
        new_cursor_shape = app.cursor.get_cursor_shape(app)
        if (
            self._last_cursor_shape is None
            or self._last_cursor_shape != new_cursor_shape
        ):
            output.set_cursor_shape(new_cursor_shape)
            self._last_cursor_shape = new_cursor_shape

        # Flush buffered output.
        output.flush()

        # Set visible windows in layout.
        app.layout.visible_windows = screen.visible_windows

        if is_done:
            self.reset()

    def erase(self, leave_alternate_screen: bool = True) -> None:
        """
        Hide all output and put the cursor back at the first line. This is for
        instance used for running a system command (while hiding the CLI) and
        later resuming the same CLI.)

        :param leave_alternate_screen: When True, and when inside an alternate
            screen buffer, quit the alternate screen.
        """
        output = self.output

        output.cursor_backward(self._cursor_pos.x)
        output.cursor_up(self._cursor_pos.y)
        output.erase_down()
        output.reset_attributes()
        output.enable_autowrap()

        output.flush()

        self.reset(leave_alternate_screen=leave_alternate_screen)

    def clear(self) -> None:
        """
        Clear screen and go to 0,0
        """
        # Erase current output first.
        self.erase()

        # Send "Erase Screen" command and go to (0, 0).
        output = self.output

        output.erase_screen()
        output.cursor_goto(0, 0)
        output.flush()

        self.request_absolute_cursor_position()


def print_formatted_text(
    output: Output,
    formatted_text: AnyFormattedText,
    style: BaseStyle,
    style_transformation: StyleTransformation | None = None,
    color_depth: ColorDepth | None = None,
) -> None:
    """
    Print a list of (style_str, text) tuples in the given style to the output.
    """
    fragments = to_formatted_text(formatted_text)
    style_transformation = style_transformation or DummyStyleTransformation()
    color_depth = color_depth or output.get_default_color_depth()

    # Reset first.
    output.reset_attributes()
    output.enable_autowrap()
    last_attrs: Attrs | None = None

    # Print all (style_str, text) tuples.
    attrs_for_style_string = _StyleStringToAttrsCache(
        style.get_attrs_for_style_str, style_transformation
    )

    for style_str, text, *_ in fragments:
        attrs = attrs_for_style_string[style_str]

        # Set style attributes if something changed.
        if attrs != last_attrs:
            if attrs:
                output.set_attributes(attrs, color_depth)
            else:
                output.reset_attributes()
        last_attrs = attrs

        # Print escape sequences as raw output
        if "[ZeroWidthEscape]" in style_str:
            output.write_raw(text)
        else:
            # Eliminate carriage returns
            text = text.replace("\r", "")
            # Insert a carriage return before every newline (important when the
            # front-end is a telnet client).
            text = text.replace("\n", "\r\n")
            output.write(text)

    # Reset again.
    output.reset_attributes()
    output.flush()
