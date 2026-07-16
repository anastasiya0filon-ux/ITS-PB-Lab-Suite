from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

METHOD_ID = "MUK_4_1_3166"

@dataclass(frozen=True)
class CalculatedPeak:
    method_id: str
    component: str
    detector: str
    concentration: float
    area: float
    height: float
    sigma_minutes: float
    fwhm_minutes: float

def _load_payload() -> dict:
    path = Path(__file__).with_name("calibration_model.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("method_id") != METHOD_ID:
        raise ValueError(f"Ожидалась модель {METHOD_ID}")
    return payload

def _models() -> dict[tuple[str, str], dict]:
    return {
        (str(item["component"]), str(item["detector"])): item
        for item in _load_payload()["models"]
    }

def _linear(model: dict, concentration: float) -> float:
    c = max(0.0, float(concentration))
    return max(0.0, float(model["slope"]) * c + float(model["intercept"]))

def _interpolate_width(width_model: dict, concentration: float) -> tuple[float, float]:
    points = sorted(width_model["points"], key=lambda p: float(p["concentration"]))
    c = max(0.0, float(concentration))
    if c <= float(points[0]["concentration"]):
        p = points[0]
        return float(p["sigma_minutes"]), float(p["fwhm_minutes"])
    if c >= float(points[-1]["concentration"]):
        p = points[-1]
        return float(p["sigma_minutes"]), float(p["fwhm_minutes"])
    for left, right in zip(points, points[1:]):
        c0 = float(left["concentration"])
        c1 = float(right["concentration"])
        if c <= c1:
            f = 0.0 if c1 <= c0 else (c - c0) / (c1 - c0)
            sigma = float(left["sigma_minutes"]) + f * (
                float(right["sigma_minutes"]) - float(left["sigma_minutes"])
            )
            fwhm = float(left["fwhm_minutes"]) + f * (
                float(right["fwhm_minutes"]) - float(left["fwhm_minutes"])
            )
            return max(0.0, sigma), max(0.0, fwhm)
    p = points[-1]
    return float(p["sigma_minutes"]), float(p["fwhm_minutes"])

def calculate_peak(*, component: str, detector: str, concentration: float) -> CalculatedPeak:
    model = _models().get((str(component), str(detector)))
    if model is None:
        raise KeyError(f"Нет градуировки {METHOD_ID}: {component} / {detector}")
    area = _linear(model["area"], concentration)
    height = _linear(model["height"], concentration)
    sigma, fwhm = _interpolate_width(model["width"], concentration)
    return CalculatedPeak(
        method_id=METHOD_ID,
        component=str(component),
        detector=str(detector),
        concentration=float(concentration),
        area=area,
        height=height,
        sigma_minutes=sigma,
        fwhm_minutes=fwhm,
    )
