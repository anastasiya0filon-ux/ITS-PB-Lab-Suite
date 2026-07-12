# -*- coding: utf-8 -*-
from __future__ import annotations

import random

from . import geometry
from .fonts import draw_vertical_text, load_font
from .profiles import zone_for
from .spec import SPEC, detector_spec


def _nearest(samples, left, right):
    rows = [row for row in samples if left <= row[0] <= right]
    return max(rows, key=lambda row: row[1]) if rows else None


def _analytic_label(at, component, area, detector):
    name = str(component)
    if detector == "ПИД-2" and 20.2 <= at <= 21.4 and name in {"п-Ксилол", "м-Ксилол"}:
        name = "м-Ксилол, п-Ксилол"
    if detector == "ПИД-2" and 21.5 <= at <= 22.9 and name in {"Стирол", "о-Ксилол"}:
        name = "Стирол, о-Ксилол"
    return f"{at:.3f} {name} {float(area):.3f}"


def draw_labels(image, *, peaks, samples, events, detector, y_max, seed, x_min, x_max):
    color = tuple(detector_spec(detector)["rgb"])
    analytic_font = load_font(int(SPEC["fonts"]["analytic_size"]))
    background_font = load_font(int(SPEC["fonts"]["background_size"]))

    ordered = sorted(peaks, key=lambda peak: float(peak.retention_time_generated))
    merged: set[str] = set()

    for index, peak in enumerate(ordered):
        tr = float(peak.retention_time_generated)
        sigma = max(float(getattr(peak, "sigma", 0.02)), 0.020)

        left = tr - max(0.055, sigma * 4.2)
        right = tr + max(0.075, sigma * 5.2)
        if index:
            previous = float(ordered[index - 1].retention_time_generated)
            left = max(left, (previous + tr) / 2.0)
        if index + 1 < len(ordered):
            following = float(ordered[index + 1].retention_time_generated)
            right = min(right, (tr + following) / 2.0)

        apex = _nearest(samples, left, right)
        if not apex:
            continue

        at, av = apex
        label = _analytic_label(at, peak.component, peak.calculated_area, detector)

        if detector == "ПИД-2" and (
            "м-Ксилол, п-Ксилол" in label or "Стирол, о-Ксилол" in label
        ):
            key = label.split(" ", 1)[1].rsplit(" ", 1)[0]
            if key in merged:
                peak.retention_time_generated = round(at, 6)
                continue
            merged.add(key)

        x = geometry.x_to_px(at, x_min, x_max)
        apex_y = geometry.y_to_px(av, y_max)

        # Final rule: lower edge of the vertical label is just above the
        # true maximum of the already constructed signal.
        draw_vertical_text(
            image,
            label,
            x,
            int(round(apex_y - 2)),
            analytic_font,
            color,
            min_y=geometry.PLOT_Y0 + 1,
            min_x=geometry.PLOT_X0 + 1,
            max_x=geometry.PLOT_X1 - 1,
        )
        peak.retention_time_generated = round(at, 6)

    rnd = random.Random(seed ^ 0x91F3)
    for center, amplitude, width, kind in events:
        zone = zone_for(center)
        probability = float(zone["label_probability"])
        probability *= 0.54 if center < 20.0 else 0.92
        if kind > probability:
            continue

        apex = _nearest(
            samples,
            center - 2.7 * width,
            center + 2.7 * width,
        )
        if not apex:
            continue

        at, av = apex
        label = f"{at:.3f}" if kind < 0.35 else f"{at:.3f} {amplitude * 9.0:.3f}"
        x = geometry.x_to_px(at, x_min, x_max) + rnd.uniform(-0.45, 0.45)
        apex_y = geometry.y_to_px(av, y_max)

        draw_vertical_text(
            image,
            label,
            x,
            int(round(apex_y - 1)),
            background_font,
            color,
            min_y=geometry.PLOT_Y0 + 1,
            min_x=geometry.PLOT_X0 + 1,
            max_x=geometry.PLOT_X1 - 1,
        )
