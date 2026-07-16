# -*- coding: utf-8 -*-
from __future__ import annotations
import math
from functools import lru_cache
from .real_profiles import interpolated_peak_profile


def _chromatek_soft_signal_line(draw, xy, fill, width=1):
    draw.line(xy, fill=fill, width=max(1, int(width)))
    try:
        if isinstance(fill, tuple) and len(fill) >= 3:
            soft_fill = tuple(
                min(255, int(round(channel * 0.78 + 255 * 0.22)))
                for channel in fill[:3]
            )
        else:
            soft_fill = fill

        shifted = []
        for point in xy:
            if not isinstance(point, (tuple, list)) or len(point) < 2:
                return
            shifted.append((point[0] + 1, point[1]))

        draw.line(shifted, fill=soft_fill, width=1)
    except Exception:
        pass


def _gauss(dt: float, sigma: float) -> float:
    if sigma <= 0:
        return 0.0
    z = dt / sigma
    return math.exp(-0.5 * z * z)

def _shape(dt: float, p: dict) -> float:
    sigma = p["sigma_min"]
    local = sigma * (p["left_factor"] if dt < 0 else p["right_factor"])
    core = _gauss(dt, local)
    base = 0.040 * _gauss(dt, sigma * 2.15)
    tail = 0.0
    if dt > 0:
        tail = p["tail_fraction"] * math.exp(
            -dt / max(sigma * p["tail_tau_sigma"], 1e-9)
        )
    return max(0.0, core + base + tail)

@lru_cache(maxsize=2048)
def _apex(detector: str, component: str, height_key: float):
    p = interpolated_peak_profile(detector, component, height_key)
    sigma = p["sigma_min"]
    span = max(0.08, 5.0 * sigma)
    best_dt, best_value = 0.0, -1.0
    for i in range(1401):
        dt = -span + 2.0 * span * i / 1400.0
        value = _shape(dt, p)
        if value > best_value:
            best_dt, best_value = dt, value
    return best_dt, best_value, p

def peak_value(t: float, peak) -> float:
    height = float(getattr(peak, "calculated_height", 0.0))
    if height <= 0:
        return 0.0
    detector = str(peak.detector)
    component = str(peak.component)
    tr = float(peak.retention_time_generated)
    key = round(height, 6)
    offset, apex_value, p = _apex(detector, component, key)
    return height * _shape((t - tr) + offset, p) / max(apex_value, 1e-12)
