from __future__ import annotations

from prompt_toolkit.output.vt100 import _256_colors, _get_closest_ansi_color


def test_get_closest_ansi_color():
    # White
    assert _get_closest_ansi_color(255, 255, 255) == "ansiwhite"
    assert _get_closest_ansi_color(250, 250, 250) == "ansiwhite"

    # Black
    assert _get_closest_ansi_color(0, 0, 0) == "ansiblack"
    assert _get_closest_ansi_color(5, 5, 5) == "ansiblack"

    # Green
    assert _get_closest_ansi_color(0, 255, 0) == "ansibrightgreen"
    assert _get_closest_ansi_color(10, 255, 0) == "ansibrightgreen"
    assert _get_closest_ansi_color(0, 255, 10) == "ansibrightgreen"

    assert _get_closest_ansi_color(220, 220, 100) == "ansiyellow"


def test_the_256_color_table_holds_256_colors():
    "The table is 16 colors, then a 6x6x6 cube, then a ramp of 24 greys."
    assert len(_256_colors.colors) == 256


def test_the_color_cube_ends_at_231():
    "Color 16 is the first of the cube and color 231 is the last."
    assert _256_colors.colors[16] == (0x00, 0x00, 0x00)
    assert _256_colors.colors[231] == (0xFF, 0xFF, 0xFF)


def test_the_grey_ramp_runs_from_232_to_255():
    "Each step of the ramp is ten, and the first one is eight."
    assert _256_colors.colors[232] == (8, 8, 8)
    assert _256_colors.colors[233] == (18, 18, 18)
    assert _256_colors.colors[255] == (238, 238, 238)
