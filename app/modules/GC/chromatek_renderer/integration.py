# -*- coding: utf-8 -*-
from __future__ import annotations

import random

from . import geometry
from .fonts import draw_vertical_text, load_font
from .profiles import zone_for
from .spec import detector_spec


ANALYTIC_FONT_PX = 7
BACKGROUND_FONT_PX = 6

# Один пиксель между вершиной и текстом: читаемо и близко к эталону.
ANALYTIC_APEX_GAP = 1
BACKGROUND_APEX_GAP = 0

ANALYTIC_MIN_GAP_PX = 5
ANALYTIC_SHIFT_STEP_PX = 2
ANALYTIC_MAX_SHIFT_PX = 6

BACKGROUND_EXCLUSION_PX = 8
BACKGROUND_MIN_GAP_PX = 5


def _nearest_time(samples, target):
    return min(samples, key=lambda row: abs(row[0] - target)) if samples else None


def _nearest_apex(samples, left, right):
    rows = [row for row in samples if left <= row[0] <= right]
    return max(rows, key=lambda row: row[1]) if rows else None


def analytic_label_text(retention_time, component, area, detector):
    return f"{retention_time:.3f} {component} {float(area):.3f}"


def _resolve_x(base_x, used_x):
    if all(abs(base_x - previous) >= ANALYTIC_MIN_GAP_PX for previous in used_x):
        return base_x

    for distance in range(
        ANALYTIC_SHIFT_STEP_PX,
        ANALYTIC_MAX_SHIFT_PX + 1,
        ANALYTIC_SHIFT_STEP_PX,
    ):
        for candidate in (base_x - distance, base_x + distance):
            if candidate <= geometry.PLOT_X0 + 1:
                continue
            if candidate >= geometry.PLOT_X1 - 1:
                continue
            if all(
                abs(candidate - previous) >= ANALYTIC_MIN_GAP_PX
                for previous in used_x
            ):
                return candidate

    return base_x


def draw_labels(
    image, *, peaks, samples, events, detector, y_max, seed, x_min, x_max,
):
    color = tuple(detector_spec(detector)["rgb"])
    analytic_font = load_font(ANALYTIC_FONT_PX)
    background_font = load_font(BACKGROUND_FONT_PX)

    ordered = sorted(peaks, key=lambda peak: float(peak.retention_time_generated))
    analytic_x_positions = []

    for peak in ordered:
        tr = float(peak.retention_time_generated)
        row = _nearest_time(samples, tr)
        if row is None:
            continue

        _, amplitude = row
        label = analytic_label_text(
            tr,
            str(peak.component),
            peak.calculated_area,
            detector,
        )

        base_x = geometry.x_to_px(tr, x_min, x_max)
        x = _resolve_x(base_x, analytic_x_positions)
        analytic_x_positions.append(x)

        bottom_y = int(round(
            geometry.y_to_px(amplitude, y_max) - ANALYTIC_APEX_GAP
        ))

        draw_vertical_text(
            image,
            label,
            x,
            bottom_y,
            analytic_font,
            color,
            min_y=geometry.PLOT_Y0 + 1,
            min_x=geometry.PLOT_X0 + 1,
            max_x=geometry.PLOT_X1 - 1,
        )

    rnd = random.Random(seed ^ 0x91F3)
    background_x_positions = []

    for center, amplitude, width, kind in events:
        zone = zone_for(center)
        probability = float(zone["label_probability"]) * (
            0.26 if center < 20.0 else 0.48
        )
        if kind > probability:
            continue

        apex = _nearest_apex(samples, center - 2.7 * width, center + 2.7 * width)
        if apex is None:
            continue

        at, apex_value = apex
        x = geometry.x_to_px(at, x_min, x_max)

        if any(abs(x - used_x) < BACKGROUND_EXCLUSION_PX for used_x in analytic_x_positions):
            continue
        if any(abs(x - used_x) < BACKGROUND_MIN_GAP_PX for used_x in background_x_positions):
            continue

        background_x_positions.append(x)
        text = f"{at:.3f}" if kind < 0.35 else f"{at:.3f} {amplitude * 9:.3f}"

        draw_vertical_text(
            image,
            text,
            x,
            int(round(geometry.y_to_px(apex_value, y_max))),
            background_font,
            color,
            min_y=geometry.PLOT_Y0 + 1,
            min_x=geometry.PLOT_X0 + 1,
            max_x=geometry.PLOT_X1 - 1,
        )
