"""
The colours of a vt100 terminal, and the arithmetic that reaches them.

A terminal takes a colour in one of three ways: by name, as one of the
256 numbers of its palette, or as red, green and blue. A style names a
colour in a fourth way, "ffffff", and something has to map one onto the
other. This module is that map, and nothing in it writes an escape
sequence: `vt100.py` does that.

A lot of thanks, regarding outputting of colors, goes to the Pygments
project. (We don't rely on Pygments anymore, because many things are
very custom, and everything has been highly optimized.)
http://pygments.org/
"""

from __future__ import annotations

from typing import Dict, Hashable, Sequence, Tuple

from prompt_toolkit.styles import ANSI_COLOR_NAMES, PALETTE_COLOR_NAMES

__all__ = [
    "ANSI_COLORS_TO_RGB",
    "ANSI_COLOR_INDEXES",
    "BG_ANSI_COLORS",
    "FG_ANSI_COLORS",
]


FG_ANSI_COLORS = {
    "ansidefault": 39,
    # Low intensity.
    "ansiblack": 30,
    "ansired": 31,
    "ansigreen": 32,
    "ansiyellow": 33,
    "ansiblue": 34,
    "ansimagenta": 35,
    "ansicyan": 36,
    "ansigray": 37,
    # High intensity.
    "ansibrightblack": 90,
    "ansibrightred": 91,
    "ansibrightgreen": 92,
    "ansibrightyellow": 93,
    "ansibrightblue": 94,
    "ansibrightmagenta": 95,
    "ansibrightcyan": 96,
    "ansiwhite": 97,
}

BG_ANSI_COLORS = {
    "ansidefault": 49,
    # Low intensity.
    "ansiblack": 40,
    "ansired": 41,
    "ansigreen": 42,
    "ansiyellow": 43,
    "ansiblue": 44,
    "ansimagenta": 45,
    "ansicyan": 46,
    "ansigray": 47,
    # High intensity.
    "ansibrightblack": 100,
    "ansibrightred": 101,
    "ansibrightgreen": 102,
    "ansibrightyellow": 103,
    "ansibrightblue": 104,
    "ansibrightmagenta": 105,
    "ansibrightcyan": 106,
    "ansiwhite": 107,
}


ANSI_COLORS_TO_RGB = {
    "ansidefault": (
        0x00,
        0x00,
        0x00,
    ),  # Don't use, 'default' doesn't really have a value.
    "ansiblack": (0x00, 0x00, 0x00),
    "ansigray": (0xE5, 0xE5, 0xE5),
    "ansibrightblack": (0x7F, 0x7F, 0x7F),
    "ansiwhite": (0xFF, 0xFF, 0xFF),
    # Low intensity.
    "ansired": (0xCD, 0x00, 0x00),
    "ansigreen": (0x00, 0xCD, 0x00),
    "ansiyellow": (0xCD, 0xCD, 0x00),
    "ansiblue": (0x00, 0x00, 0xCD),
    "ansimagenta": (0xCD, 0x00, 0xCD),
    "ansicyan": (0x00, 0xCD, 0xCD),
    # High intensity.
    "ansibrightred": (0xFF, 0x00, 0x00),
    "ansibrightgreen": (0x00, 0xFF, 0x00),
    "ansibrightyellow": (0xFF, 0xFF, 0x00),
    "ansibrightblue": (0x00, 0x00, 0xFF),
    "ansibrightmagenta": (0xFF, 0x00, 0xFF),
    "ansibrightcyan": (0x00, 0xFF, 0xFF),
}


assert set(FG_ANSI_COLORS) == set(ANSI_COLOR_NAMES)
assert set(BG_ANSI_COLORS) == set(ANSI_COLOR_NAMES)
assert set(ANSI_COLORS_TO_RGB) == set(ANSI_COLOR_NAMES)


#: The number of the palette that an Ansi name stands for. "SGR 58"
#: takes a number and no name, so the name has to become one.
ANSI_COLOR_INDEXES = {
    name: (code - 30 if code < 40 else code - 90 + 8)
    for name, code in FG_ANSI_COLORS.items()
    if name != "ansidefault"
}

#: `PALETTE_COLOR_NAMES` names the first sixteen in the order that the
#: palette numbers them. `parse_color` reads a number back to a name
#: out of it, so the order has to be this one.
assert [ANSI_COLOR_INDEXES[name] for name in PALETTE_COLOR_NAMES] == list(range(16))


def _get_closest_ansi_color(r: int, g: int, b: int, exclude: Sequence[str] = ()) -> str:
    """
    Find closest ANSI color. Return it by name.

    :param r: Red (Between 0 and 255.)
    :param g: Green (Between 0 and 255.)
    :param b: Blue (Between 0 and 255.)
    :param exclude: A tuple of color names to exclude. (E.g. ``('ansired', )``.)
    """
    exclude = list(exclude)

    # When we have a bit of saturation, avoid the gray-like colors, otherwise,
    # too often the distance to the gray color is less.
    saturation = abs(r - g) + abs(g - b) + abs(b - r)  # Between 0..510

    if saturation > 30:
        exclude.extend(["ansilightgray", "ansidarkgray", "ansiwhite", "ansiblack"])

    # Take the closest color.
    # (Thanks to Pygments for this part.)
    distance = 257 * 257 * 3  # "infinity" (>distance from #000000 to #ffffff)
    match = "ansidefault"

    for name, (r2, g2, b2) in ANSI_COLORS_TO_RGB.items():
        if name != "ansidefault" and name not in exclude:
            d = (r - r2) ** 2 + (g - g2) ** 2 + (b - b2) ** 2

            if d < distance:
                match = name
                distance = d

    return match


_ColorCodeAndName = Tuple[int, str]


class _16ColorCache:
    """
    Cache which maps (r, g, b) tuples to 16 ansi colors.

    :param bg: Cache for background colors, instead of foreground.
    """

    def __init__(self, bg: bool = False) -> None:
        self.bg = bg
        self._cache: dict[Hashable, _ColorCodeAndName] = {}

    def get_code(
        self, value: tuple[int, int, int], exclude: Sequence[str] = ()
    ) -> _ColorCodeAndName:
        """
        Return a (ansi_code, ansi_name) tuple. (E.g. ``(44, 'ansiblue')``.) for
        a given (r,g,b) value.
        """
        key: Hashable = (value, tuple(exclude))
        cache = self._cache

        if key not in cache:
            cache[key] = self._get(value, exclude)

        return cache[key]

    def _get(
        self, value: tuple[int, int, int], exclude: Sequence[str] = ()
    ) -> _ColorCodeAndName:
        r, g, b = value
        match = _get_closest_ansi_color(r, g, b, exclude=exclude)

        # Turn color name into code.
        if self.bg:
            code = BG_ANSI_COLORS[match]
        else:
            code = FG_ANSI_COLORS[match]

        return code, match


class _256ColorCache(Dict[Tuple[int, int, int], int]):
    """
    Cache which maps (r, g, b) tuples to 256 colors.
    """

    def __init__(self) -> None:
        # Build color table.
        colors: list[tuple[int, int, int]] = []

        # colors 0..15: 16 basic colors
        colors.append((0x00, 0x00, 0x00))  # 0
        colors.append((0xCD, 0x00, 0x00))  # 1
        colors.append((0x00, 0xCD, 0x00))  # 2
        colors.append((0xCD, 0xCD, 0x00))  # 3
        colors.append((0x00, 0x00, 0xEE))  # 4
        colors.append((0xCD, 0x00, 0xCD))  # 5
        colors.append((0x00, 0xCD, 0xCD))  # 6
        colors.append((0xE5, 0xE5, 0xE5))  # 7
        colors.append((0x7F, 0x7F, 0x7F))  # 8
        colors.append((0xFF, 0x00, 0x00))  # 9
        colors.append((0x00, 0xFF, 0x00))  # 10
        colors.append((0xFF, 0xFF, 0x00))  # 11
        colors.append((0x5C, 0x5C, 0xFF))  # 12
        colors.append((0xFF, 0x00, 0xFF))  # 13
        colors.append((0x00, 0xFF, 0xFF))  # 14
        colors.append((0xFF, 0xFF, 0xFF))  # 15

        # colors 16..231: the 6x6x6 color cube
        valuerange = (0x00, 0x5F, 0x87, 0xAF, 0xD7, 0xFF)

        for i in range(216):
            r = valuerange[(i // 36) % 6]
            g = valuerange[(i // 6) % 6]
            b = valuerange[i % 6]
            colors.append((r, g, b))

        # colors 232..255: the grayscale ramp. It has 24 steps. It
        # starts near black and stops near white, because the cube
        # holds both ends already.
        for i in range(24):
            v = 8 + i * 10
            colors.append((v, v, v))

        self.colors = colors

    def __missing__(self, value: tuple[int, int, int]) -> int:
        r, g, b = value

        # Find closest color.
        # (Thanks to Pygments for this!)
        distance = 257 * 257 * 3  # "infinity" (>distance from #000000 to #ffffff)
        match = 0

        for i, (r2, g2, b2) in enumerate(self.colors):
            if i >= 16:  # XXX: We ignore the 16 ANSI colors when mapping RGB
                # to the 256 colors, because these highly depend on
                # the color scheme of the terminal.
                d = (r - r2) ** 2 + (g - g2) ** 2 + (b - b2) ** 2

                if d < distance:
                    match = i
                    distance = d

        # Turn color name into code.
        self[value] = match
        return match


_16_fg_colors = _16ColorCache(bg=False)
_16_bg_colors = _16ColorCache(bg=True)
_256_colors = _256ColorCache()
