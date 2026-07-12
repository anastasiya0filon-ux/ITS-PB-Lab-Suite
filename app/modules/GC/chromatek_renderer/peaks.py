# -*- coding: utf-8 -*-
from __future__ import annotations

import math
import random

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
    asym = rnd.uniform(-0.045, 0.045)
    shoulder_shift = rnd.uniform(0.42, 0.78)

    families = {
        "sharp":   (0.82, 1.04, 0.014, 0.0),
        "fronted": (1.16, 0.92, 0.028, -1.0),
        "wide":    (1.18, 1.24, 0.022, 1.0),
        "cluster": (0.94, 1.28, 0.052, 1.0),
        "tail":    (0.96, 1.38, 0.028, 1.0),
        "normal":  (1.00, 1.16, 0.020, 1.0),
    }
    left, right, shoulder_share, shoulder_side = families.get(
        family, families["normal"]
    )
    left *= 1.0 - asym
    right *= 1.0 + asym

    local_sigma = sigma * (left if dt < 0.0 else right)
    core = 0.935 * _gauss(dt, local_sigma)
    base = 0.050 * _gauss(dt, sigma * 2.25)

    shoulder = 0.0
    if shoulder_side:
        center = shoulder_side * shoulder_shift * sigma
        shoulder = shoulder_share * _gauss(
            dt - center,
            sigma * (0.50 if family != "cluster" else 0.68),
        )

    tail = 0.0
    if dt > 0.0 and tail_fraction > 0.0:
        tau = max(0.035, sigma * (4.4 if family in {"tail", "cluster"} else 3.2))
        tail = tail_fraction * math.exp(-dt / tau)

    # Small deterministic apex irregularity, strongest close to the apex.
    apex_window = math.exp(-0.5 * (dt / max(sigma * 0.52, 1e-9)) ** 2)
    ripple = 1.0 + apex_window * (
        0.008 * math.sin(dt / max(sigma, 1e-9) * 19.0 + seed % 17)
        + 0.004 * math.sin(dt / max(sigma, 1e-9) * 41.0 + seed % 11)
    )

    result = height * (core + base + shoulder + tail) / (0.985 + shoulder_share)
    return max(0.0, result * ripple)


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
    sigma *= float(zone["sigma_scale"]) * float(component.get("sigma_scale", 1.0))

    family = str(component.get("family", "normal"))
    seed = int(getattr(peak, "internal_seed", 1))
    rnd = random.Random(seed ^ 0x51A7)
    tail_fraction = min(
        float(cfg["tail_max_fraction"]),
        float(zone["tail"]) + rnd.uniform(0.0, 0.0032),
    )

    return _instrument_profile(
        t - tr,
        sigma,
        height,
        family,
        seed,
        tail_fraction,
    )
