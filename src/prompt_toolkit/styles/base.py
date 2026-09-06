"""
The base classes for the styling.
"""

from __future__ import annotations

import re
from abc import ABCMeta, abstractmethod
from typing import Callable, Hashable, NamedTuple

__all__ = [
    "Attrs",
    "DEFAULT_ATTRS",
    "ANSI_COLOR_NAMES",
    "ANSI_COLOR_NAMES_ALIASES",
    "PALETTE_COLOR_NAMES",
    "PALETTE_SIZE",
    "palette_color_number",
    "BaseStyle",
    "DummyStyle",
    "DynamicStyle",
]


#: Style attributes.
class Attrs(NamedTuple):
    color: str | None
    bgcolor: str | None
    bold: bool | None
    underline: bool | None
    strike: bool | None
    italic: bool | None
    blink: bool | None
    reverse: bool | None
    hidden: bool | None
    dim: bool | None
    # A default, so that code that builds an `Attrs` without knowing
    # about hyperlinks keeps working.
    hyperlink: str | None = ""
    # The shape of the underline, and its colour. Defaults again, for
    # the same reason.
    underline_style: str | None = ""
    underline_color: str | None = ""
    # The id that joins the pieces of one hyperlink. A default again.
    hyperlink_id: str | None = ""


"""
:param color: Hexadecimal string. E.g. '000000' or Ansi color name: e.g. 'ansiblue'
:param bgcolor: Hexadecimal string. E.g. 'ffffff' or Ansi color name: e.g. 'ansired'
:param bold: Boolean
:param underline: Boolean
:param strike: Boolean
:param italic: Boolean
:param blink: Boolean
:param reverse: Boolean
:param hidden: Boolean
:param dim: Boolean
:param hyperlink: The target of a hyperlink (OSC 8), or an empty string
    for text that is not a link.
:param underline_style: The shape of the line: 'single', 'double',
    'curly', 'dotted' or 'dashed'. An empty string means a single line.
    It only shows when `underline` is true.
:param underline_color: Hexadecimal string or Ansi color name for the
    line itself. An empty string means the colour of the text.
:param hyperlink_id: The id of a hyperlink (OSC 8), or an empty string
    for a link that has none. Two runs of cells with the same id are one
    link, even when a line break separates them. It only means something
    together with `hyperlink`.
"""

#: The default `Attrs`.
DEFAULT_ATTRS = Attrs(
    color="",
    bgcolor="",
    bold=False,
    underline=False,
    strike=False,
    italic=False,
    blink=False,
    reverse=False,
    hidden=False,
    dim=False,
    hyperlink="",
    underline_style="",
    underline_color="",
    hyperlink_id="",
)


#: ``Attrs.bgcolor/fgcolor`` can be in either 'ffffff' format, or can be any of
#: the following in case we want to take colors from the 8/16 color palette.
#: Usually, in that case, the terminal application allows to configure the RGB
#: values for these names.
#: ISO 6429 colors
ANSI_COLOR_NAMES = [
    "ansidefault",
    # Low intensity, dark.  (One or two components 0x80, the other 0x00.)
    "ansiblack",
    "ansired",
    "ansigreen",
    "ansiyellow",
    "ansiblue",
    "ansimagenta",
    "ansicyan",
    "ansigray",
    # High intensity, bright. (One or two components 0xff, the other 0x00. Not supported everywhere.)
    "ansibrightblack",
    "ansibrightred",
    "ansibrightgreen",
    "ansibrightyellow",
    "ansibrightblue",
    "ansibrightmagenta",
    "ansibrightcyan",
    "ansiwhite",
]


# People don't use the same ANSI color names everywhere. In prompt_toolkit 1.0
# we used some unconventional names (which were contributed like that to
# Pygments). This is fixed now, but we still support the old names.

# The table below maps the old aliases to the current names.
ANSI_COLOR_NAMES_ALIASES: dict[str, str] = {
    "ansidarkgray": "ansibrightblack",
    "ansiteal": "ansicyan",
    "ansiturquoise": "ansibrightcyan",
    "ansibrown": "ansiyellow",
    "ansipurple": "ansimagenta",
    "ansifuchsia": "ansibrightmagenta",
    "ansilightgray": "ansigray",
    "ansidarkred": "ansired",
    "ansidarkgreen": "ansigreen",
    "ansidarkblue": "ansiblue",
}
assert set(ANSI_COLOR_NAMES_ALIASES.values()).issubset(set(ANSI_COLOR_NAMES))
assert not (set(ANSI_COLOR_NAMES_ALIASES.keys()) & set(ANSI_COLOR_NAMES))


#: The name of each of the first sixteen colours of the palette, in the
#: order that "CSI 38 ; 5 ; n m" numbers them. `ANSI_COLOR_NAMES` is
#: the same list with the default in front of it.
PALETTE_COLOR_NAMES = ANSI_COLOR_NAMES[1:]

assert len(PALETTE_COLOR_NAMES) == 16

#: How a colour of the palette that has no name is written: "ansi16"
#: up to "ansi255". The first sixteen have names, and `parse_color`
#: gives the name back, so one colour keeps one spelling.
_PALETTE_COLOR = re.compile(r"^ansi([0-9]{1,3})$")

#: How many colours the palette holds.
PALETTE_SIZE = 256


def palette_color_number(color: str) -> int | None:
    """
    The number of the palette that a colour string names, or None.

    A number of the palette is not a colour. It is a question that the
    terminal of the user answers from its own theme, so it travels as
    a number and nothing here turns it into red, green and blue.
    """
    match = _PALETTE_COLOR.match(color)
    if match is None:
        return None
    number = int(match.group(1))
    if number >= PALETTE_SIZE:
        return None
    return number


class BaseStyle(metaclass=ABCMeta):
    """
    Abstract base class for prompt_toolkit styles.
    """

    @abstractmethod
    def get_attrs_for_style_str(
        self, style_str: str, default: Attrs = DEFAULT_ATTRS
    ) -> Attrs:
        """
        Return :class:`.Attrs` for the given style string.

        :param style_str: The style string. This can contain inline styling as
            well as classnames (e.g. "class:title").
        :param default: `Attrs` to be used if no styling was defined.
        """

    @property
    @abstractmethod
    def style_rules(self) -> list[tuple[str, str]]:
        """
        The list of style rules, used to create this style.
        (Required for `DynamicStyle` and `_MergedStyle` to work.)
        """
        return []

    @abstractmethod
    def invalidation_hash(self) -> Hashable:
        """
        Invalidation hash for the style. When this changes over time, the
        renderer knows that something in the style changed, and that everything
        has to be redrawn.
        """


class DummyStyle(BaseStyle):
    """
    A style that doesn't style anything.
    """

    def get_attrs_for_style_str(
        self, style_str: str, default: Attrs = DEFAULT_ATTRS
    ) -> Attrs:
        return default

    def invalidation_hash(self) -> Hashable:
        return 1  # Always the same value.

    @property
    def style_rules(self) -> list[tuple[str, str]]:
        return []


class DynamicStyle(BaseStyle):
    """
    Style class that can dynamically returns an other Style.

    :param get_style: Callable that returns a :class:`.Style` instance.
    """

    def __init__(self, get_style: Callable[[], BaseStyle | None]):
        self.get_style = get_style
        self._dummy = DummyStyle()

    def get_attrs_for_style_str(
        self, style_str: str, default: Attrs = DEFAULT_ATTRS
    ) -> Attrs:
        style = self.get_style() or self._dummy

        return style.get_attrs_for_style_str(style_str, default)

    def invalidation_hash(self) -> Hashable:
        return (self.get_style() or self._dummy).invalidation_hash()

    @property
    def style_rules(self) -> list[tuple[str, str]]:
        return (self.get_style() or self._dummy).style_rules
