"""
The DEC line attributes: how big one line of the terminal is drawn.

A VT100 draws a line at single size or at double size, and the line
holds the attribute, not the cells. `ESC # 5` gives the plain line back,
`ESC # 6` draws it twice as wide, and `ESC # 3` and `ESC # 4` draw the
top and the bottom half of a line that is twice as high as well.

An application that draws the screen of another program has to carry
these, because the program chose them: a banner written with `ESC # 6`
holds half as many characters as the line, and a terminal that never
hears about the attribute draws them all small.
"""

from __future__ import annotations

from enum import Enum

__all__ = [
    "LineAttribute",
]


class LineAttribute(Enum):
    """
    How the terminal draws one line.

    The value of each member is what a fragment carries as its text, so
    `LineAttribute(text)` reads one back.
    """

    #: The plain line: one cell wide and one cell high. A row that names
    #: no attribute is this one.
    SINGLE = "single"

    #: DECDWL: twice as wide, one line high.
    DOUBLE_WIDTH = "double-width"

    #: DECDHL, the top half of a line that is twice as high.
    DOUBLE_HEIGHT_TOP = "double-height-top"

    #: DECDHL, the bottom half of one.
    DOUBLE_HEIGHT_BOTTOM = "double-height-bottom"
