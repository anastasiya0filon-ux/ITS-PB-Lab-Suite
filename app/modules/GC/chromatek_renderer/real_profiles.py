# -*- coding: utf-8 -*-
from __future__ import annotations
import json
from functools import lru_cache
from pathlib import Path

_PATH = Path(__file__).with_name("real_peak_profiles_levels.json")

@lru_cache(maxsize=1)
def _profiles():
    return json.loads(_PATH.read_text(encoding="utf-8"))["profiles"]

def _lerp(a: float, b: float, f: float) -> float:
    return a + (b - a) * f

def interpolated_peak_profile(
    detector: str,
    component: str,
    calculated_height: float,
) -> dict:
    profile = _profiles().get(f"{detector}|{component}")
    if profile is None:
        raise KeyError(f"Нет профиля для {detector} / {component}")

    levels = profile["levels"]
    h = max(0.0, float(calculated_height))
    if h <= levels[0]["height"]:
        left = right = levels[0]
        fraction = 0.0
    elif h >= levels[-1]["height"]:
        left = right = levels[-1]
        fraction = 0.0
    else:
        left = levels[0]
        right = levels[-1]
        for index in range(1, len(levels)):
            if h <= levels[index]["height"]:
                left = levels[index - 1]
                right = levels[index]
                break
        span = right["height"] - left["height"]
        fraction = 0.0 if span <= 0 else (h - left["height"]) / span

    ratio = _lerp(left["area_height"], right["area_height"], fraction)
    # Area/height has units seconds. For a Gaussian:
    # area/height = sigma_seconds * sqrt(2*pi).
    sigma_min = ratio / (60.0 * (2.0 * 3.141592653589793) ** 0.5)

    # The real calibration data determine width. Only a small deterministic
    # right-side asymmetry is retained; there are no random peak families.
    level_spread = abs(right["area_height"] - left["area_height"]) / max(ratio, 1e-12)
    return {
        "sigma_min": max(0.0025, sigma_min),
        "left_factor": max(0.96, 1.0 - 0.04 * level_spread),
        "right_factor": min(1.18, 1.035 + 0.20 * level_spread),
        "tail_fraction": min(0.035, 0.008 + 0.08 * level_spread),
        "tail_tau_sigma": 3.4,
        "interpolation_fraction": fraction,
        "left_level": left["level"],
        "right_level": right["level"],
    }
