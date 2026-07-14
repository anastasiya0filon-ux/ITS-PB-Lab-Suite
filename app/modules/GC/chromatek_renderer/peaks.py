# -*- coding: utf-8 -*-
from __future__ import annotations

import math
import random
from functools import lru_cache

from .profiles import component_profile, zone_for
from .spec import SPEC


def _gauss(dt: float, sigma: float) -> float:
    if sigma <= 0.0:
        return 0.0
    z = dt / sigma
    return math.exp(-0.5 * z * z)


def _instrument_profile(
    dt: float,
    sigma: float,
    height: float,
    family: str,
    seed: int,
    tail_fraction: float,
) -> float:
    rnd = random.Random(seed ^ 0x6B39)
    asym = rnd.uniform(-0.030, 0.030)

    families = {
        "sharp":   (1.02, 1.12, 0.010, 0.0),
        "fronted": (1.20, 1.03, 0.018, -1.0),
        "wide":    (1.27, 1.33, 0.016, 1.0),
        "cluster": (1.08, 1.37, 0.036, 1.0),
        "tail":    (1.07, 1.44, 0.018, 1.0),
        "normal":  (1.11, 1.21, 0.012, 1.0),
    }
    left, right, shoulder_share, shoulder_side = families.get(
        family, families["normal"]
    )
    left *= 1.0 - asym
    right *= 1.0 + asym

    local_sigma = sigma * (left if dt < 0.0 else right)

    core_narrow = 0.68 * _gauss(dt, local_sigma)
    core_wide = 0.27 * _gauss(dt, local_sigma * 1.48)
    base = 0.040 * _gauss(dt, sigma * 2.50)

    shoulder = 0.0
    if shoulder_side:
        center = shoulder_side * 0.65 * sigma
        shoulder = shoulder_share * _gauss(
            dt - center,
            sigma * (0.66 if family != "cluster" else 0.82),
        )

    tail = 0.0
    if dt > 0.0 and tail_fraction > 0.0:
        tau = max(0.035, sigma * (4.8 if family in {"tail", "cluster"} else 3.6))
        tail = tail_fraction * math.exp(-dt / tau)

    apex_window = math.exp(-0.5 * (dt / max(sigma * 0.70, 1e-9)) ** 2)
    ripple = 1.0 + apex_window * (
        0.0025 * math.sin(dt / max(sigma, 1e-9) * 15.0 + seed % 17)
        + 0.0012 * math.sin(dt / max(sigma, 1e-9) * 33.0 + seed % 11)
    )

    result = height * (
        core_narrow + core_wide + base + shoulder + tail
    ) / (0.99 + shoulder_share)
    return max(0.0, result * ripple)


@lru_cache(maxsize=4096)
def _profile_apex_offset(
    sigma_rounded: float,
    family: str,
    seed: int,
    tail_rounded: float,
) -> float:
    sigma = float(sigma_rounded)
    tail_fraction = float(tail_rounded)
    span = max(0.20, sigma * 3.4)
    steps = 1501
    best_dt = 0.0
    best_value = -1.0

    for index in range(steps):
        dt = -span + (2.0 * span * index / (steps - 1))
        value = _instrument_profile(
            dt, sigma, 1.0, family, seed, tail_fraction
        )
        if value > best_value:
            best_value = value
            best_dt = dt
    return best_dt


def peak_value(t: float, peak) -> float:
    height = float(getattr(peak, "calculated_height", 0.0))
    sigma_source = float(getattr(peak, "sigma", 0.0))
    tr = float(getattr(peak, "retention_time_generated", 0.0))
    if height <= 0.0:
        return 0.0

    cfg = SPEC["peaks"]
    zone = zone_for(tr)
    component = component_profile(str(getattr(peak, "component", "")))

    minimum = float(cfg["min_sigma_early"]) + float(cfg["min_sigma_slope"]) * tr
    sigma = max(
        sigma_source
        * (1.0 + float(cfg["late_broadening_per_min"]) * max(0.0, tr - 2.0)),
        minimum,
    )

    # Только визуальная доводка: чуть шире основание крупных пиков.
    sigma *= 1.14
    sigma *= float(zone["sigma_scale"]) * float(component.get("sigma_scale", 1.0))

    family = str(component.get("family", "normal"))
    seed = int(getattr(peak, "internal_seed", 1))
    rnd = random.Random(seed ^ 0x51A7)

    tail_fraction = min(
        float(cfg["tail_max_fraction"]),
        float(zone["tail"]) + rnd.uniform(0.0, 0.0020),
    )

    own_apex = _profile_apex_offset(
        round(sigma, 8),
        family,
        seed,
        round(tail_fraction, 8),
    )
    corrected_dt = (t - tr) + own_apex

    return _instrument_profile(
        corrected_dt, sigma, height, family, seed, tail_fraction
    )
