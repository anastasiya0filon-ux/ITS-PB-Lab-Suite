# GC_PEAK_LABEL_SOFTNESS_FIX_25A
# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass

from . import geometry
from .fonts import draw_vertical_text, load_font
from .peak_label_readability_fix_08 import draw_vertical_text_readable
from .spec import detector_spec
from .typography_passport import TYPOGRAPHY


@dataclass
class _LabelPlacement:
    peak: object
    apex_t: float
    apex_value: float
    x: float
    bottom_y: int


def _physical_apex(samples, target, left_limit, right_limit):
    """Находит физический максимум только внутри области собственного пика."""
    half_window = TYPOGRAPHY.search_half_window_min
    left = max(target - half_window, left_limit)
    right = min(target + half_window, right_limit)
    candidates = [row for row in samples if left <= row[0] <= right]
    return max(candidates, key=lambda row: row[1]) if candidates else None


def draw_labels(
    image,
    *,
    peaks,
    samples,
    events,
    detector,
    y_max,
    seed,
    x_min,
    x_max,
):
    """Рисует подписи согласно Chromatek Typography Passport 1.0.

    Важные инварианты:
    - X подписи равен X физического максимума собственного пика;
    - координата пика, RT, площадь и сигнал не пересчитываются;
    - искусственные раздвижки по X и Y отсутствуют;
    - в плотных группах разрешено эталонное наложение текста.
    """
    del events, seed

    color = tuple(detector_spec(detector)["rgb"])
    font = load_font(
        TYPOGRAPHY.peak_font_px,
        bold=TYPOGRAPHY.peak_font_bold,
        face=TYPOGRAPHY.peak_font_family,
        render_scale=TYPOGRAPHY.text_render_scale, softness=TYPOGRAPHY.peak_softness)
    ordered = sorted(peaks, key=lambda p: float(p.retention_time_generated))
    placements: list[_LabelPlacement] = []

    for index, peak in enumerate(ordered):
        target = float(peak.retention_time_generated)
        left_limit = float(x_min)
        right_limit = float(x_max)

        # Границы по серединам между соседними RT не позволяют подписи
        # привязаться к более высокому соседнему пику.
        if index > 0:
            previous = float(ordered[index - 1].retention_time_generated)
            left_limit = (previous + target) / 2.0
        if index + 1 < len(ordered):
            following = float(ordered[index + 1].retention_time_generated)
            right_limit = (target + following) / 2.0

        apex = _physical_apex(samples, target, left_limit, right_limit)
        if apex is None:
            continue

        apex_t, apex_value = apex
        x = geometry.x_to_px(apex_t, x_min, x_max)
        bottom_y = int(round(
            geometry.y_to_px(apex_value, y_max) - TYPOGRAPHY.apex_gap_px
        ))

        placements.append(
            _LabelPlacement(
                peak=peak,
                apex_t=float(apex_t),
                apex_value=float(apex_value),
                x=float(x),
                bottom_y=bottom_y,
            )
        )

    for placement in placements:
        peak = placement.peak
        label = TYPOGRAPHY.format_peak_label(
            retention_time=float(peak.retention_time_generated),
            component=peak.component,
            area=float(peak.calculated_area),
        )

        # ROLLBACK_CHROMATEK_TYPOGRAPHY_ENGINE_TO_WORKING_FONT
        # GC_PEAK_LABEL_READABILITY_FIX_08
        draw_vertical_text_readable(
            image,
            label,
            placement.x,
            placement.bottom_y,
            font,
            color,
            min_y=geometry.PLOT_Y0 + 1,
            min_x=geometry.PLOT_X0 + 1,
            max_x=geometry.PLOT_X1 - 1,
        )
