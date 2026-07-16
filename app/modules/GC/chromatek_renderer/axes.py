# GC_AXIS_LINES_INTENSITY_75_FIX_26
# GC_AXIS_LABEL_WEIGHT_SOFTNESS_FIX_24
# GC_AXIS_LABEL_WEIGHT_INTENSITY_FIX_23A
# GC_AXIS_LABEL_FINE_TUNE_FIX_22
# GC_AXIS_LABEL_POSITION_AND_SIZE_FIX_21A
# GC_AXIS_GDI_WIDTH_AND_OFFSET_FIX_20
# GC_AXES_LABELS_ORIGINAL_MATCH_FIX_19A
# -*- coding: utf-8 -*-
from __future__ import annotations

import math
from PIL import ImageDraw

from . import geometry
from .fonts import draw_bitmap_text, draw_vertical_text, load_font
from .spec import detector_spec
from .typography_passport import TYPOGRAPHY


X_MINOR_STEP = 0.5
X_MAJOR_STEP = 2.5

X_MAJOR_TICK = 7
X_MINOR_TICK = 4
Y_MAJOR_TICK = 7
Y_MINOR_TICK = 4


def _axis_line_color(rgb, intensity: float = 0.75):
    factor = max(0.0, min(1.0, float(intensity)))
    return tuple(
        int(round(255 - (255 - int(channel)) * factor))
        for channel in rgb
    )
def nice_y_max(value: float) -> float:
    value = max(float(value), 1e-9)
    exponent = math.floor(math.log10(value))
    fraction = value / (10 ** exponent)
    for candidate in (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if fraction <= candidate:
            return candidate * (10 ** exponent)
    return 10 ** (exponent + 1)


def _format_tick(value: float, step: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    decimals = 1 if abs(step) >= 0.1 else 2
    return f"{value:.{decimals}f}".rstrip("0").rstrip(".")


def draw_axes(
    image,
    *,
    detector: str,
    y_max: float,
    x_min: float,
    x_max: float,
    y_tick_step: float | None = None,
):
    draw = ImageDraw.Draw(image)
    color = tuple(detector_spec(detector)["axis_rgb"])
    scale_color = _axis_line_color(color, 0.75)
    scale_gray = _axis_line_color((170, 170, 170), 0.75)
    x_font = load_font(TYPOGRAPHY.x_axis_font_px, bold=TYPOGRAPHY.x_axis_font_bold, face=TYPOGRAPHY.x_axis_font_family, render_scale=TYPOGRAPHY.text_render_scale, width_scale=TYPOGRAPHY.x_axis_width_scale, size_scale=TYPOGRAPHY.axis_size_scale, weight_scale=TYPOGRAPHY.axis_weight_scale, intensity=TYPOGRAPHY.axis_intensity, softness=TYPOGRAPHY.axis_softness)
    y_font = load_font(TYPOGRAPHY.y_axis_font_px, bold=TYPOGRAPHY.y_axis_font_bold, face=TYPOGRAPHY.y_axis_font_family, render_scale=TYPOGRAPHY.text_render_scale, width_scale=TYPOGRAPHY.y_axis_width_scale, size_scale=TYPOGRAPHY.axis_size_scale, weight_scale=TYPOGRAPHY.axis_weight_scale, intensity=TYPOGRAPHY.axis_intensity, softness=TYPOGRAPHY.axis_softness)
    unit_font = load_font(TYPOGRAPHY.unit_font_px, bold=TYPOGRAPHY.unit_font_bold, face=TYPOGRAPHY.unit_font_family, render_scale=TYPOGRAPHY.text_render_scale, width_scale=TYPOGRAPHY.unit_width_scale, size_scale=TYPOGRAPHY.axis_size_scale, weight_scale=TYPOGRAPHY.axis_weight_scale, intensity=TYPOGRAPHY.axis_intensity, softness=TYPOGRAPHY.axis_softness)

    draw.line(
        (geometry.PLOT_X0, geometry.PLOT_Y0, geometry.PLOT_X1, geometry.PLOT_Y0),
        fill=scale_gray, width=1,
    )
    draw.line(
        (geometry.PLOT_X0, geometry.PLOT_Y0, geometry.PLOT_X0, geometry.PLOT_Y1),
        fill=scale_color, width=1,
    )
    draw.line(
        (geometry.PLOT_X0, geometry.PLOT_Y1, geometry.PLOT_X1, geometry.PLOT_Y1),
        fill=scale_color, width=1,
    )

    value = math.ceil(x_min / X_MINOR_STEP) * X_MINOR_STEP
    while value <= x_max + 1e-9:
        x = geometry.x_to_px(value, x_min, x_max)
        is_major = abs(value / X_MAJOR_STEP - round(value / X_MAJOR_STEP)) < 1e-8
        tick = X_MAJOR_TICK if is_major else X_MINOR_TICK
        draw.line((x, geometry.PLOT_Y1, x, geometry.PLOT_Y1 + tick), fill=scale_color, width=1)

        if is_major and value > x_min + 0.01 and value < x_max - 0.15:
            draw_bitmap_text(
                image, _format_tick(value, X_MAJOR_STEP), x,
                geometry.PLOT_Y1 + TYPOGRAPHY.x_axis_label_offset_px, x_font, color, anchor="mm",
            )
        value += X_MINOR_STEP

    step = (
        float(y_tick_step)
        if y_tick_step is not None and float(y_tick_step) > 0
        else float(y_max) / 5.0
    )
    count = max(1, int(round(float(y_max) / step)))

    for index in range(count + 1):
        tick_value = min(float(y_max), index * step)
        y = geometry.y_to_px(tick_value, y_max)
        draw.line(
            (geometry.PLOT_X0 - Y_MAJOR_TICK, y, geometry.PLOT_X0, y),
            fill=scale_color, width=1,
        )
        if index > 0:
            # GC_Y_AXIS_LABEL_ROTATION_FIX_16
            draw_vertical_text(
                image,
                _format_tick(tick_value, step),
                geometry.PLOT_X0 - TYPOGRAPHY.y_axis_label_gap_px,
                y,
                y_font,
                color,
                bottom_gap=0,
                min_y=geometry.PLOT_Y0,
                min_x=0,
                max_x=geometry.PLOT_X0 - 1,
                center_on_y=True,
            )

        if index < count:
            for minor_index in range(1, 5):
                minor_value = tick_value + minor_index * step / 5.0
                minor_y = geometry.y_to_px(minor_value, y_max)
                draw.line(
                    (geometry.PLOT_X0 - Y_MINOR_TICK, minor_y, geometry.PLOT_X0, minor_y),
                    fill=scale_color, width=1,
                )

    draw_vertical_text(
        image, "мВ", 7, geometry.PLOT_Y0 + 18, unit_font, color,
        min_y=1, min_x=0, max_x=geometry.PLOT_X0 - 1,
    )
    draw_bitmap_text(
        image, "мин", geometry.PLOT_X1, geometry.PLOT_Y1 + 10,
        unit_font, color, anchor="rt",
    )
