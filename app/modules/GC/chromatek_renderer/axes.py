# -*- coding: utf-8 -*-
from __future__ import annotations

import math
from PIL import ImageDraw

from . import geometry
from .fonts import load_font, draw_vertical_text, draw_bitmap_text
from .spec import SPEC, detector_spec


def nice_y_max(value: float) -> float:
    value = max(float(value), 1e-9)
    exponent = math.floor(math.log10(value))
    fraction = value / (10 ** exponent)

    for candidate in (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if fraction <= candidate:
            return candidate * (10 ** exponent)
    return 10 ** (exponent + 1)


def _format_y_tick(value: float, step: float) -> str:
    """
    Keep the scale in real mV, but format it like Chromatek:
    no scientific notation and no meaningless long decimal tails.
    """
    absolute_step = abs(step)

    if absolute_step >= 10:
        decimals = 0
    elif absolute_step >= 1:
        decimals = 0 if abs(round(step) - step) < 1e-9 else 1
    elif absolute_step >= 0.1:
        decimals = 1
    elif absolute_step >= 0.01:
        decimals = 2
    elif absolute_step >= 0.001:
        decimals = 3
    else:
        decimals = 4

    text = f"{value:.{decimals}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def draw_axes(image, *, detector: str, y_max: float, x_min: float, x_max: float):
    draw = ImageDraw.Draw(image)
    detector_style = detector_spec(detector)
    color = tuple(detector_style["axis_rgb"])
    font = load_font(int(SPEC["fonts"]["axis_size"]))

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

    minor_step = float(SPEC["axis"]["minor_x_step"])
    major_step = float(SPEC["axis"]["major_x_step"])
    value = 0.0
    label_y = geometry.PLOT_Y1 + 3

    while value <= x_max + 1e-9:
        x = geometry.x_to_px(value, x_min, x_max)
        is_major = abs(value / major_step - round(value / major_step)) < 1e-8

        draw.line(
            (
                x,
                geometry.PLOT_Y1,
                x,
                geometry.PLOT_Y1 + (4 if is_major else 2),
            ),
            fill=color,
            width=1,
        )

        if is_major and value > 0 and value < x_max - 0.2:
            label = (
                f"{value:.1f}"
                if abs(value - round(value)) > 1e-8
                else str(int(value))
            )
            draw_bitmap_text(
                image,
                label,
                x,
                label_y,
                font,
                color,
                anchor="mm",
            )

        value += minor_step

    intervals = int(SPEC["axis"]["y_major_intervals"])
    minor_count = int(SPEC["axis"]["y_minor_per_major"])
    step = y_max / intervals

    for index in range(intervals + 1):
        tick_value = index * step
        y = geometry.y_to_px(tick_value, y_max)

        draw.line(
            (geometry.PLOT_X0 - 4, y, geometry.PLOT_X0, y),
            fill=color,
            width=1,
        )

        if index > 0:
            label = _format_y_tick(tick_value, step)
            draw_bitmap_text(
                image,
                label,
                geometry.PLOT_X0 - 6,
                y,
                font,
                color,
                anchor="rm",
            )

        if index < intervals:
            for minor_index in range(1, minor_count):
                minor_y = geometry.y_to_px(
                    tick_value + minor_index * step / minor_count,
                    y_max,
                )
                draw.line(
                    (
                        geometry.PLOT_X0 - 2,
                        minor_y,
                        geometry.PLOT_X0,
                        minor_y,
                    ),
                    fill=color,
                    width=1,
                )

    draw_vertical_text(
        image,
        "мВ",
        x=7,
        bottom_y=geometry.PLOT_Y0 + 18,
        font=font,
        color=color,
        min_y=1,
        min_x=0,
        max_x=geometry.PLOT_X0 - 1,
    )

    draw_bitmap_text(
        image,
        "мин",
        geometry.PLOT_X1,
        geometry.PLOT_Y1 + 11,
        font,
        color,
        anchor="rt",
    )
