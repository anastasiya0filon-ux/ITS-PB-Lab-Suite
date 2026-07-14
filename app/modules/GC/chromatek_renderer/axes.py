# -*- coding: utf-8 -*-
from __future__ import annotations

import math
from PIL import ImageDraw

from . import geometry
from .fonts import draw_bitmap_text, draw_vertical_text, load_font
from .spec import detector_spec


AXIS_FONT_PX = 7
X_MINOR_STEP = 0.5
X_MAJOR_STEP = 2.5

X_MAJOR_TICK = 4
X_MINOR_TICK = 2
Y_MAJOR_TICK = 4
Y_MINOR_TICK = 2

X_LABEL_OFFSET = 5
Y_LABEL_GAP = 5


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
    font = load_font(AXIS_FONT_PX)

    # Геометрия и толщина — 1 px, как в эталонном растре.
    draw.line(
        (geometry.PLOT_X0, geometry.PLOT_Y0, geometry.PLOT_X1, geometry.PLOT_Y0),
        fill=(170, 170, 170),
        width=1,
    )
    draw.line(
        (geometry.PLOT_X0, geometry.PLOT_Y0, geometry.PLOT_X0, geometry.PLOT_Y1),
        fill=color,
        width=1,
    )
    draw.line(
        (geometry.PLOT_X0, geometry.PLOT_Y1, geometry.PLOT_X1, geometry.PLOT_Y1),
        fill=color,
        width=1,
    )

    value = math.ceil(x_min / X_MINOR_STEP) * X_MINOR_STEP
    while value <= x_max + 1e-9:
        x = geometry.x_to_px(value, x_min, x_max)
        is_major = abs(value / X_MAJOR_STEP - round(value / X_MAJOR_STEP)) < 1e-8
        tick = X_MAJOR_TICK if is_major else X_MINOR_TICK
        draw.line((x, geometry.PLOT_Y1, x, geometry.PLOT_Y1 + tick), fill=color, width=1)

        if is_major and value > x_min + 0.01 and value < x_max - 0.15:
            label = _format_tick(value, X_MAJOR_STEP)
            draw_bitmap_text(
                image,
                label,
                x,
                geometry.PLOT_Y1 + X_LABEL_OFFSET,
                font,
                color,
                anchor="mm",
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
            fill=color,
            width=1,
        )
        if index > 0:
            draw_bitmap_text(
                image,
                _format_tick(tick_value, step),
                geometry.PLOT_X0 - Y_LABEL_GAP,
                y,
                font,
                color,
                anchor="rm",
            )

        if index < count:
            for minor_index in range(1, 5):
                minor_value = tick_value + minor_index * step / 5.0
                minor_y = geometry.y_to_px(minor_value, y_max)
                draw.line(
                    (geometry.PLOT_X0 - Y_MINOR_TICK, minor_y, geometry.PLOT_X0, minor_y),
                    fill=color,
                    width=1,
                )

    draw_vertical_text(
        image,
        "мВ",
        7,
        geometry.PLOT_Y0 + 18,
        font,
        color,
        min_y=1,
        min_x=0,
        max_x=geometry.PLOT_X0 - 1,
    )
    draw_bitmap_text(
        image,
        "мин",
        geometry.PLOT_X1,
        geometry.PLOT_Y1 + 10,
        font,
        color,
        anchor="rt",
    )
