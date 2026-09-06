"""
Output for vt100 terminals.

This module writes the escape sequences. `vt100_colors.py` holds the
tables and the arithmetic that turn a colour into a number, and this
module is the only reader of them.
"""

from __future__ import annotations

import io
import os
import sys
from typing import Callable, Dict, Iterable, TextIO

from prompt_toolkit.cursor_shapes import CursorShape
from prompt_toolkit.data_structures import Size
from prompt_toolkit.output import Output
from prompt_toolkit.styles import ANSI_COLOR_NAMES, Attrs, palette_color_number
from prompt_toolkit.utils import is_dumb_terminal

from .color_depth import ColorDepth
from .flush_stdout import flush_stdout
from .vt100_colors import (
    ANSI_COLOR_INDEXES,
    BG_ANSI_COLORS,
    FG_ANSI_COLORS,
    _16_bg_colors,
    _16_fg_colors,
    _256_colors,
)

__all__ = [
    "Vt100_Output",
]


#: The parameter of "SGR 4" that each shape of an underline takes. A
#: shape that a terminal does not know draws a plain line.
UNDERLINE_STYLE_PARAMETERS = {
    "": "4",
    "single": "4",
    "double": "4:2",
    "curly": "4:3",
    "dotted": "4:4",
    "dashed": "4:5",
}


class _EscapeCodeCache(Dict[Attrs, str]):
    """
    Cache for VT100 escape codes. It maps
    (fgcolor, bgcolor, bold, underline, strike, italic, blink, reverse, hidden, dim) tuples to VT100
    escape sequences.

    :param true_color: When True, use 24bit colors instead of 256 colors.
    """

    def __init__(self, color_depth: ColorDepth) -> None:
        self.color_depth = color_depth

    def __missing__(self, attrs: Attrs) -> str:
        (
            fgcolor,
            bgcolor,
            bold,
            underline,
            strike,
            italic,
            blink,
            reverse,
            hidden,
            dim,
            # A hyperlink is not a rendition: it opens with a sequence
            # of its own and closes with another, so `set_attributes`
            # writes it and this cache leaves it alone. The id of the
            # link goes out in the same sequence.
            _hyperlink,
            underline_style,
            underline_color,
            _hyperlink_id,
        ) = attrs
        parts: list[str] = []

        parts.extend(self._colors_to_code(fgcolor or "", bgcolor or ""))

        if bold:
            parts.append("1")
        if dim:
            parts.append("2")
        if italic:
            parts.append("3")
        if blink:
            parts.append("5")
        if underline:
            parts.append(UNDERLINE_STYLE_PARAMETERS.get(underline_style or "", "4"))
            parts.extend(self._underline_color_to_code(underline_color or ""))
        if reverse:
            parts.append("7")
        if hidden:
            parts.append("8")
        if strike:
            parts.append("9")

        if parts:
            result = "\x1b[0;" + ";".join(parts) + "m"
        else:
            result = "\x1b[0m"

        self[attrs] = result
        return result

    def _underline_color_to_code(self, color: str) -> Iterable[str]:
        """
        The parameters that paint the line itself ("SGR 58").

        The line takes the colour of the text when nothing comes back.
        There is no form of "SGR 58" that names one of the first
        sixteen colours directly, so a name becomes a number of the
        palette. A terminal of four bits paints no coloured line at
        all, so it gets nothing.
        """
        if not color or self.color_depth in (
            ColorDepth.DEPTH_1_BIT,
            ColorDepth.DEPTH_4_BIT,
        ):
            return []

        if color in ANSI_COLOR_INDEXES:
            return ["58:5:%d" % ANSI_COLOR_INDEXES[color]]
        if color in ANSI_COLOR_NAMES:  # 'ansidefault'.
            return []

        number = palette_color_number(color)
        if number is not None:
            return ["58:5:%d" % number]

        try:
            red, green, blue = self._color_name_to_rgb(color)
        except ValueError:
            return []

        if self.color_depth == ColorDepth.DEPTH_24_BIT:
            return ["58:2::%d:%d:%d" % (red, green, blue)]
        return ["58:5:%d" % _256_colors[(red, green, blue)]]

    def _color_name_to_rgb(self, color: str) -> tuple[int, int, int]:
        "Turn 'ffffff', into (0xff, 0xff, 0xff)."
        try:
            rgb = int(color, 16)
        except ValueError:
            raise
        else:
            r = (rgb >> 16) & 0xFF
            g = (rgb >> 8) & 0xFF
            b = rgb & 0xFF
            return r, g, b

    def _colors_to_code(self, fg_color: str, bg_color: str) -> Iterable[str]:
        """
        Return a tuple with the vt100 values  that represent this color.
        """
        # When requesting ANSI colors only, and both fg/bg color were converted
        # to ANSI, ensure that the foreground and background color are not the
        # same. (Unless they were explicitly defined to be the same color.)
        fg_ansi = ""

        def get(color: str, bg: bool) -> list[int]:
            nonlocal fg_ansi

            table = BG_ANSI_COLORS if bg else FG_ANSI_COLORS

            if not color or self.color_depth == ColorDepth.DEPTH_1_BIT:
                return []

            # 16 ANSI colors. (Given by name.)
            elif color in table:
                return [table[color]]

            # A color of the palette ('ansi234'), or an RGB color
            # (defined as 'ffffff').
            else:
                number = palette_color_number(color)

                if number is None:
                    try:
                        rgb = self._color_name_to_rgb(color)
                    except ValueError:
                        return []
                else:
                    rgb = _256_colors.colors[number]

                # When only 16 colors are supported, use that.
                if self.color_depth == ColorDepth.DEPTH_4_BIT:
                    if bg:  # Background.
                        if fg_color != bg_color:
                            exclude = [fg_ansi]
                        else:
                            exclude = []
                        code, name = _16_bg_colors.get_code(rgb, exclude=exclude)
                        return [code]
                    else:  # Foreground.
                        code, name = _16_fg_colors.get_code(rgb)
                        fg_ansi = name
                        return [code]

                # A number of the palette stays a number, at every
                # depth that can carry one. The terminal of the user
                # paints it from its own theme, and this one has no
                # theme to paint it from.
                elif number is not None:
                    return [(48 if bg else 38), 5, number]

                # True colors. (Only when this feature is enabled.)
                elif self.color_depth == ColorDepth.DEPTH_24_BIT:
                    r, g, b = rgb
                    return [(48 if bg else 38), 2, r, g, b]

                # 256 RGB colors.
                else:
                    return [(48 if bg else 38), 5, _256_colors[rgb]]

        result: list[int] = []
        result.extend(get(fg_color, False))
        result.extend(get(bg_color, True))

        return map(str, result)


def _get_size(fileno: int) -> tuple[int, int]:
    """
    Get the size of this pseudo terminal.

    :param fileno: stdout.fileno()
    :returns: A (rows, cols) tuple.
    """
    size = os.get_terminal_size(fileno)
    return size.lines, size.columns


#: The longest id that an "OSC 8" may carry. The specification of the
#: sequence gives this number.
MAX_HYPERLINK_ID_LENGTH = 250

#: The characters that an id may not hold. Three of them separate the
#: parts of the sequence, and a control character ends it early. An id
#: with one of these in it would change what the sequence means, so it
#: does not go out at all.
_UNSAFE_IN_HYPERLINK_ID = frozenset(";:=\x1b\x07")


def _safe_hyperlink_id(hyperlink_id: str) -> str:
    """
    The id to write for a hyperlink, or an empty string for none.

    An id joins the pieces of one link, so a link that a line break cuts
    in two stays one link. It travels in the parameter field of the
    sequence, which is why it may not hold the characters that end that
    field.
    """
    if not hyperlink_id or len(hyperlink_id) > MAX_HYPERLINK_ID_LENGTH:
        return ""
    if any(
        character < " " or character == "\x7f" or character in _UNSAFE_IN_HYPERLINK_ID
        for character in hyperlink_id
    ):
        return ""
    return hyperlink_id


class Vt100_Output(Output):
    """
    :param get_size: A callable which returns the `Size` of the output terminal.
    :param stdout: Any object with has a `write` and `flush` method + an 'encoding' property.
    :param term: The terminal environment variable. (xterm, xterm-256color, linux, ...)
    :param enable_cpr: When `True` (the default), send "cursor position
        request" escape sequences to the output in order to detect the cursor
        position. That way, we can properly determine how much space there is
        available for the UI (especially for drop down menus) to render. The
        `Renderer` will still try to figure out whether the current terminal
        does respond to CPR escapes. When `False`, never attempt to send CPR
        requests.
    """

    # For the error messages. Only display "Output is not a terminal" once per
    # file descriptor.
    _fds_not_a_terminal: set[int] = set()

    def __init__(
        self,
        stdout: TextIO,
        get_size: Callable[[], Size],
        term: str | None = None,
        default_color_depth: ColorDepth | None = None,
        enable_bell: bool = True,
        enable_cpr: bool = True,
    ) -> None:
        assert all(hasattr(stdout, a) for a in ("write", "flush"))

        self._buffer: list[str] = []
        self.stdout: TextIO = stdout
        self.default_color_depth = default_color_depth
        self._get_size = get_size
        self.term = term
        self.enable_bell = enable_bell
        self.enable_cpr = enable_cpr

        # Cache for escape codes.
        self._escape_code_caches: dict[ColorDepth, _EscapeCodeCache] = {
            ColorDepth.DEPTH_1_BIT: _EscapeCodeCache(ColorDepth.DEPTH_1_BIT),
            ColorDepth.DEPTH_4_BIT: _EscapeCodeCache(ColorDepth.DEPTH_4_BIT),
            ColorDepth.DEPTH_8_BIT: _EscapeCodeCache(ColorDepth.DEPTH_8_BIT),
            ColorDepth.DEPTH_24_BIT: _EscapeCodeCache(ColorDepth.DEPTH_24_BIT),
        }

        # Keep track of whether the cursor shape was ever changed.
        # (We don't restore the cursor shape if it was never changed - by
        # default, we don't change them.)
        self._cursor_shape_changed = False

        # The hyperlink (OSC 8) that is open, and the id that joins its
        # pieces. Two empty strings mean that what follows is not a link.
        self._hyperlink = ""
        self._hyperlink_id = ""

        # Don't hide/show the cursor when this was already done.
        # (`None` means that we don't know whether the cursor is visible or
        # not.)
        self._cursor_visible: bool | None = None

    @classmethod
    def from_pty(
        cls,
        stdout: TextIO,
        term: str | None = None,
        default_color_depth: ColorDepth | None = None,
        enable_bell: bool = True,
    ) -> Vt100_Output:
        """
        Create an Output class from a pseudo terminal.
        (This will take the dimensions by reading the pseudo
        terminal attributes.)
        """
        fd: int | None
        # Normally, this requires a real TTY device, but people instantiate
        # this class often during unit tests as well. For convenience, we print
        # an error message, use standard dimensions, and go on.
        try:
            fd = stdout.fileno()
        except io.UnsupportedOperation:
            fd = None

        if not stdout.isatty() and (fd is None or fd not in cls._fds_not_a_terminal):
            msg = "Warning: Output is not a terminal (fd=%r).\n"
            sys.stderr.write(msg % fd)
            sys.stderr.flush()
            if fd is not None:
                cls._fds_not_a_terminal.add(fd)

        def get_size() -> Size:
            # If terminal (incorrectly) reports its size as 0, pick a
            # reasonable default.  See
            # https://github.com/ipython/ipython/issues/10071
            rows, columns = (None, None)

            # It is possible that `stdout` is no longer a TTY device at this
            # point. In that case we get an `OSError` in the ioctl call in
            # `get_size`. See:
            # https://github.com/prompt-toolkit/python-prompt-toolkit/pull/1021
            try:
                rows, columns = _get_size(stdout.fileno())
            except OSError:
                pass
            return Size(rows=rows or 24, columns=columns or 80)

        return cls(
            stdout,
            get_size,
            term=term,
            default_color_depth=default_color_depth,
            enable_bell=enable_bell,
        )

    def get_size(self) -> Size:
        return self._get_size()

    def fileno(self) -> int:
        "Return file descriptor."
        return self.stdout.fileno()

    def encoding(self) -> str:
        "Return encoding used for stdout."
        return self.stdout.encoding

    def write_raw(self, data: str) -> None:
        """
        Write raw data to output.
        """
        self._buffer.append(data)

    def write(self, data: str) -> None:
        """
        Write text to output.
        (Removes vt100 escape codes. -- used for safely writing text.)
        """
        self._buffer.append(data.replace("\x1b", "?"))

    def set_title(self, title: str) -> None:
        """
        Set terminal title.
        """
        if self.term not in (
            "linux",
            "eterm-color",
        ):  # Not supported by the Linux console.
            self.write_raw(
                "\x1b]2;{}\x07".format(title.replace("\x1b", "").replace("\x07", ""))
            )

    def clear_title(self) -> None:
        self.set_title("")

    def erase_screen(self) -> None:
        """
        Erases the screen with the background color and moves the cursor to
        home.
        """
        self.write_raw("\x1b[2J")

    def enter_alternate_screen(self) -> None:
        self.write_raw("\x1b[?1049h\x1b[H")

    def quit_alternate_screen(self) -> None:
        self.write_raw("\x1b[?1049l")

    def enable_mouse_support(self) -> None:
        self.write_raw("\x1b[?1000h")

        # Enable mouse-drag support.
        self.write_raw("\x1b[?1003h")

        # Enable urxvt Mouse mode. (For terminals that understand this.)
        self.write_raw("\x1b[?1015h")

        # Also enable Xterm SGR mouse mode. (For terminals that understand this.)
        self.write_raw("\x1b[?1006h")

        # Note: E.g. lxterminal understands 1000h, but not the urxvt or sgr
        #       extensions.

    def disable_mouse_support(self) -> None:
        self.write_raw("\x1b[?1000l")
        self.write_raw("\x1b[?1015l")
        self.write_raw("\x1b[?1006l")
        self.write_raw("\x1b[?1003l")

    def erase_end_of_line(self) -> None:
        """
        Erases from the current cursor position to the end of the current line.
        """
        self.write_raw("\x1b[K")

    def erase_down(self) -> None:
        """
        Erases the screen from the current line down to the bottom of the
        screen.
        """
        self.write_raw("\x1b[J")

    def reset_attributes(self) -> None:
        self.write_raw("\x1b[0m")

        # "CSI 0 m" says nothing about a hyperlink, so an open one has
        # to be closed by hand.
        if self._hyperlink:
            self._hyperlink = ""
            self._hyperlink_id = ""
            self.write_raw("\x1b]8;;\x1b\\")

    def set_attributes(self, attrs: Attrs, color_depth: ColorDepth) -> None:
        """
        Create new style and output.

        :param attrs: `Attrs` instance.
        """
        # Get current depth.
        escape_code_cache = self._escape_code_caches[color_depth]

        # Write escape character.
        self.write_raw(escape_code_cache[attrs])

        # A hyperlink (OSC 8) opens with one sequence and closes with
        # another, so it only goes out when it changes. An empty target
        # closes the link that is open.
        #
        # The id changes the link as much as the target does. Two runs
        # with one target and two ids are two links, and a terminal that
        # reads only the target joins what the program kept apart.
        hyperlink = attrs.hyperlink or ""
        # A link that closes carries no id, because there is nothing
        # left to join.
        hyperlink_id = _safe_hyperlink_id(attrs.hyperlink_id or "") if hyperlink else ""

        if (hyperlink, hyperlink_id) != (self._hyperlink, self._hyperlink_id):
            self._hyperlink = hyperlink
            self._hyperlink_id = hyperlink_id
            parameters = "id=%s" % hyperlink_id if hyperlink_id else ""
            self.write_raw("\x1b]8;%s;%s\x1b\\" % (parameters, hyperlink))

    def disable_autowrap(self) -> None:
        self.write_raw("\x1b[?7l")

    def enable_autowrap(self) -> None:
        self.write_raw("\x1b[?7h")

    def enable_bracketed_paste(self) -> None:
        self.write_raw("\x1b[?2004h")

    def disable_bracketed_paste(self) -> None:
        self.write_raw("\x1b[?2004l")

    def reset_cursor_key_mode(self) -> None:
        """
        For vt100 only.
        Put the terminal in cursor mode (instead of application mode).
        """
        # Put the terminal in cursor mode. (Instead of application mode.)
        self.write_raw("\x1b[?1l")

    def cursor_goto(self, row: int = 0, column: int = 0) -> None:
        """
        Move cursor position.
        """
        self.write_raw("\x1b[%i;%iH" % (row, column))

    def cursor_up(self, amount: int) -> None:
        if amount == 0:
            pass
        elif amount == 1:
            self.write_raw("\x1b[A")
        else:
            self.write_raw("\x1b[%iA" % amount)

    def cursor_down(self, amount: int) -> None:
        if amount == 0:
            pass
        elif amount == 1:
            # Note: Not the same as '\n', '\n' can cause the window content to
            #       scroll.
            self.write_raw("\x1b[B")
        else:
            self.write_raw("\x1b[%iB" % amount)

    def cursor_forward(self, amount: int) -> None:
        if amount == 0:
            pass
        elif amount == 1:
            self.write_raw("\x1b[C")
        else:
            self.write_raw("\x1b[%iC" % amount)

    def cursor_backward(self, amount: int) -> None:
        if amount == 0:
            pass
        elif amount == 1:
            self.write_raw("\b")  # '\x1b[D'
        else:
            self.write_raw("\x1b[%iD" % amount)

    def hide_cursor(self) -> None:
        if self._cursor_visible in (True, None):
            self._cursor_visible = False
            self.write_raw("\x1b[?25l")

    def show_cursor(self) -> None:
        if self._cursor_visible in (False, None):
            self._cursor_visible = True
            # Only show it. This used to send "CSI ? 12 l" as well, which
            # stops the cursor blinking. That is a setting of the
            # terminal, and the user chose it: an application that takes
            # it away never gives it back, because nothing here sends
            # "CSI ? 12 h" again. DECSCUSR says what shape the cursor
            # has, blinking included, and `set_cursor_shape` writes it.
            self.write_raw("\x1b[?25h")

    def begin_synchronized_update(self) -> None:
        if self.synchronized_output:
            self.write_raw("\x1b[?2026h")

    def end_synchronized_update(self) -> None:
        if self.synchronized_output:
            self.write_raw("\x1b[?2026l")

    def set_cursor_shape(self, cursor_shape: CursorShape) -> None:
        if cursor_shape == CursorShape._NEVER_CHANGE:
            return

        # "Give it back", which is only something to do when we took it.
        if cursor_shape == CursorShape.DEFAULT:
            self.reset_cursor_shape()
            return

        self._cursor_shape_changed = True
        self.write_raw(
            {
                CursorShape.BLOCK: "\x1b[2 q",
                CursorShape.BEAM: "\x1b[6 q",
                CursorShape.UNDERLINE: "\x1b[4 q",
                CursorShape.BLINKING_BLOCK: "\x1b[1 q",
                CursorShape.BLINKING_BEAM: "\x1b[5 q",
                CursorShape.BLINKING_UNDERLINE: "\x1b[3 q",
            }.get(cursor_shape, "")
        )

    def reset_cursor_shape(self) -> None:
        "Reset cursor shape."
        # (Only reset cursor shape, if we ever changed it.)
        if self._cursor_shape_changed:
            self._cursor_shape_changed = False

            # Reset cursor shape.
            self.write_raw("\x1b[0 q")

    def flush(self) -> None:
        """
        Write to output stream and flush.
        """
        if not self._buffer:
            return

        data = "".join(self._buffer)
        self._buffer = []

        flush_stdout(self.stdout, data)

    def ask_for_cpr(self) -> None:
        """
        Asks for a cursor position report (CPR).
        """
        self.write_raw("\x1b[6n")
        self.flush()

    @property
    def responds_to_cpr(self) -> bool:
        if not self.enable_cpr:
            return False

        # When the input is a tty, we assume that CPR is supported.
        # It's not when the input is piped from Pexpect.
        if os.environ.get("PROMPT_TOOLKIT_NO_CPR", "") == "1":
            return False

        if is_dumb_terminal(self.term):
            return False
        try:
            return self.stdout.isatty()
        except ValueError:
            return False  # ValueError: I/O operation on closed file

    def bell(self) -> None:
        "Sound bell."
        if self.enable_bell:
            self.write_raw("\a")
            self.flush()

    def get_default_color_depth(self) -> ColorDepth:
        """
        Return the default color depth for a vt100 terminal, according to the
        our term value.

        We prefer 256 colors almost always, because this is what most terminals
        support these days, and is a good default.
        """
        if self.default_color_depth is not None:
            return self.default_color_depth

        term = self.term

        if term is None:
            return ColorDepth.DEFAULT

        if is_dumb_terminal(term):
            return ColorDepth.DEPTH_1_BIT

        if term in ("linux", "eterm-color"):
            return ColorDepth.DEPTH_4_BIT

        return ColorDepth.DEFAULT
