# GC_PEAK_LABEL_SOFTNESS_FIX_25A
# GC_AXIS_LABEL_WEIGHT_SOFTNESS_FIX_24
# GC_AXIS_LABEL_WEIGHT_INTENSITY_FIX_23A
# GC_AXIS_LABEL_FINE_TUNE_FIX_22
# GC_AXIS_LABEL_POSITION_AND_SIZE_FIX_21A
# GC_AXIS_WIDTH_ISOLATION_FIX_20A
# GC_AXIS_GDI_WIDTH_AND_OFFSET_FIX_20
# GC_AXES_LABELS_ORIGINAL_MATCH_FIX_19A
# GC_AXIS_TYPOGRAPHY_ORIGINAL_MATCH_FIX_18
# GC_AXIS_TYPOGRAPHY_FROM_ORIGINAL_FIX_17
# GC_AXIS_LABEL_SIZE_8_FIX_15
# GC_X_AXIS_LABEL_OFFSET_4_FIX_14
# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class TypographyPassport:
    peak_font_family: str = "Arial Narrow"
    peak_font_px: int = 11
    peak_font_bold: bool = False
    peak_softness: float = 0.08
    x_axis_font_family: str = "Arial Narrow"
    x_axis_font_px: int = 11
    x_axis_font_bold: bool = False
    x_axis_width_scale: float = 1.124864
    y_axis_font_family: str = "Arial Narrow"
    y_axis_font_px: int = 11
    y_axis_font_bold: bool = False
    y_axis_width_scale: float = 1.124864
    unit_font_family: str = "Arial Narrow"
    unit_font_px: int = 11
    unit_font_bold: bool = False
    unit_width_scale: float = 1.124864
    axis_size_scale: float = 1.02
    axis_weight_scale: float = 1.03
    axis_softness: float = 0.08
    axis_intensity: float = 0.6
    text_render_scale: int = 1
    x_axis_label_offset_px: int = 14
    y_axis_label_gap_px: int = 14
    apex_gap_px: int = 12
    search_half_window_min: float = 0.16
    label_template: str = "{retention_time:.3f} {component} {area:.3f}"
    allow_x_shift: bool = False
    allow_artificial_y_staircase: bool = False
    clip_at_plot_top: bool = True

    @property
    def font_family(self) -> str:
        return self.peak_font_family

    @property
    def axis_font_px(self) -> int:
        return self.x_axis_font_px

    @property
    def analytic_font_px(self) -> int:
        return self.peak_font_px

    @property
    def font_bold(self) -> bool:
        return self.peak_font_bold

    def format_peak_label(self, *, retention_time: float, component: str, area: float) -> str:
        return self.label_template.format(
            retention_time=float(retention_time),
            component=str(component),
            area=float(area),
        )


def load_typography_passport() -> TypographyPassport:
    path = Path(__file__).with_name("typography_passport.json")
    if not path.exists():
        return TypographyPassport()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return TypographyPassport()

    defaults = TypographyPassport()
    legacy_family = str(raw.get("font_family", defaults.peak_font_family))
    legacy_axis_px = int(raw.get("axis_font_px", defaults.x_axis_font_px))
    legacy_peak_px = int(raw.get("analytic_font_px", defaults.peak_font_px))
    legacy_bold = bool(raw.get("font_bold", defaults.peak_font_bold))

    return TypographyPassport(
        peak_font_family=str(raw.get("peak_font_family", legacy_family)),
        peak_font_px=max(1, int(raw.get("peak_font_px", legacy_peak_px))),
        peak_font_bold=bool(raw.get("peak_font_bold", legacy_bold)),
        peak_softness=max(0.0, min(1.0, float(raw.get("peak_softness", 0.08)))),
        x_axis_font_family=str(raw.get("x_axis_font_family", "Arial Narrow")),
        x_axis_font_px=max(1, int(raw.get("x_axis_font_px", 11))),
        x_axis_font_bold=bool(raw.get("x_axis_font_bold", False)),
        x_axis_width_scale=max(0.5, float(raw.get("x_axis_width_scale", 1.124864))),
        y_axis_font_family=str(raw.get("y_axis_font_family", "Arial Narrow")),
        y_axis_font_px=max(1, int(raw.get("y_axis_font_px", 11))),
        y_axis_font_bold=bool(raw.get("y_axis_font_bold", False)),
        y_axis_width_scale=max(0.5, float(raw.get("y_axis_width_scale", 1.124864))),
        unit_font_family=str(raw.get("unit_font_family", "Arial Narrow")),
        unit_font_px=max(1, int(raw.get("unit_font_px", 11))),
        unit_font_bold=bool(raw.get("unit_font_bold", False)),
        unit_width_scale=max(0.5, float(raw.get("unit_width_scale", 1.124864))),
        axis_size_scale=max(0.5, float(raw.get("axis_size_scale", 1.02))),
        axis_weight_scale=max(1.0, float(raw.get("axis_weight_scale", 1.03))),
        axis_softness=max(0.0, min(1.0, float(raw.get("axis_softness", 0.08)))),
        axis_intensity=max(0.0, min(1.0, float(raw.get("axis_intensity", 0.6)))),
        text_render_scale=max(1, int(raw.get("text_render_scale", 4))),
        x_axis_label_offset_px=max(0, int(raw.get("x_axis_label_offset_px", 14))),
        y_axis_label_gap_px=max(0, int(raw.get("y_axis_label_gap_px", 14))),
        apex_gap_px=max(0, int(raw.get("apex_gap_px", defaults.apex_gap_px))),
        search_half_window_min=max(0.001, float(raw.get("search_half_window_min", defaults.search_half_window_min))),
        label_template=str(raw.get("label_template", defaults.label_template)),
        allow_x_shift=bool(raw.get("allow_x_shift", defaults.allow_x_shift)),
        allow_artificial_y_staircase=bool(raw.get("allow_artificial_y_staircase", defaults.allow_artificial_y_staircase)),
        clip_at_plot_top=bool(raw.get("clip_at_plot_top", defaults.clip_at_plot_top)),
    )


TYPOGRAPHY = load_typography_passport()
