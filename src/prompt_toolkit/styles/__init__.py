"""
Styling for prompt_toolkit applications.
"""

from __future__ import annotations

from .base import (
    ANSI_COLOR_NAMES,
    DEFAULT_ATTRS,
    PALETTE_COLOR_NAMES,
    PALETTE_SIZE,
    Attrs,
    BaseStyle,
    DummyStyle,
    DynamicStyle,
    palette_color_number,
)
from .defaults import default_pygments_style, default_ui_style
from .named_colors import NAMED_COLORS
from .pygments import (
    pygments_token_to_classname,
    style_from_pygments_cls,
    style_from_pygments_dict,
)
from .style import Priority, Style, merge_styles, parse_color
from .style_transformation import (
    AdjustBrightnessStyleTransformation,
    ConditionalStyleTransformation,
    DummyStyleTransformation,
    DynamicStyleTransformation,
    ReverseStyleTransformation,
    SetDefaultColorStyleTransformation,
    StyleTransformation,
    SwapLightAndDarkStyleTransformation,
    merge_style_transformations,
)

__all__ = [
    # Base.
    "Attrs",
    "DEFAULT_ATTRS",
    "ANSI_COLOR_NAMES",
    "PALETTE_COLOR_NAMES",
    "PALETTE_SIZE",
    "palette_color_number",
    "BaseStyle",
    "DummyStyle",
    "DynamicStyle",
    # Defaults.
    "default_ui_style",
    "default_pygments_style",
    # Style.
    "Style",
    "Priority",
    "merge_styles",
    "parse_color",
    # Style transformation.
    "StyleTransformation",
    "SwapLightAndDarkStyleTransformation",
    "ReverseStyleTransformation",
    "SetDefaultColorStyleTransformation",
    "AdjustBrightnessStyleTransformation",
    "DummyStyleTransformation",
    "ConditionalStyleTransformation",
    "DynamicStyleTransformation",
    "merge_style_transformations",
    # Pygments.
    "style_from_pygments_cls",
    "style_from_pygments_dict",
    "pygments_token_to_classname",
    # Named colors.
    "NAMED_COLORS",
]
