""" """

from __future__ import annotations

__all__ = [
    "KeepWhitespace",
    "ZeroWidthEscape",
]

ZeroWidthEscape = "[ZeroWidthEscape]"

#: Keep a blank cell that carries no style.
#:
#: The renderer drops whitespace without style at the end of a row, so
#: that a person who copies the output does not get trailing spaces. A
#: control that draws the screen of another program cannot accept that
#: guess: a space the program wrote is content, and the terminal has to
#: hold it. Such a control puts this in the style string of the cell,
#: and the renderer keeps the cell.
KeepWhitespace = "[KeepWhitespace]"
