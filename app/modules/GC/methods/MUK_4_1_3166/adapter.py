from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

METHOD_ID = "MUK_4_1_3166"
RETENTION_TIME_RELATIVE_LIMIT = 0.05
METHOD_DIR = Path(__file__).resolve().parent
GC_DIR = METHOD_DIR.parents[1]
CORE_PATH = GC_DIR / "gc_generator.py"
ENGINE_PATH = METHOD_DIR / "math_engine.py"
MODEL_PATH = METHOD_DIR / "calibration_model.json"

def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Не удалось загрузить модуль: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

_core = _load_module("gc_core_frozen_runtime", CORE_PATH)
_math = _load_module("muk_4_1_3166_math_runtime", ENGINE_PATH)
_payload = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
_index = {
    (str(item["component"]).strip().casefold(), str(item["detector"]).strip()): item
    for item in _payload["models"]
}

def _normalise_component(component: str) -> str:
    normaliser = getattr(_core, "normalize_component", None)
    if callable(normaliser):
        return str(normaliser(component)).strip()
    return str(component).strip()

def _method_model(component: str, detector: str) -> dict[str, Any] | None:
    normalised = _normalise_component(component)
    return _index.get((normalised.casefold(), str(detector).strip()))


def _enforce_retention_time_limit(reference: float, generated: float) -> float:
    """Hard limit: generated retention time must stay within 5 percent."""
    reference = float(reference)
    generated = float(generated)
    if reference <= 0:
        raise ValueError("Утверждённое время удерживания должно быть положительным")

    lower = reference * (1.0 - RETENTION_TIME_RELATIVE_LIMIT)
    upper = reference * (1.0 + RETENTION_TIME_RELATIVE_LIMIT)
    return min(upper, max(lower, generated))


def calculate_peak(
    models: dict,
    *,
    sample_code: str,
    chromatogram_index: int,
    detector: str,
    component: str,
    concentration: float,
    imperfection_level: int = 2,
):
    if concentration < 0:
        raise ValueError(f"{component}: концентрация не может быть отрицательной")

    model = _method_model(component, detector)
    if model is None:
        return None

    calculated = _math.calculate_peak(
        component=str(model["component"]),
        detector=str(detector),
        concentration=float(concentration),
    )

    reference = float(model["retention_time_mean"])
    seed = _core.stable_seed(
        METHOD_ID,
        sample_code,
        chromatogram_index,
        detector,
        component,
        f"{float(concentration):.12g}",
    )
    generated = _enforce_retention_time_limit(
        reference,
        _core.generated_retention_time(reference, seed),
    )

    return _core.PeakRecord(
        method_id=METHOD_ID,
        sample_code=sample_code,
        chromatogram_index=chromatogram_index,
        detector=detector,
        component=component,
        input_concentration=float(concentration),
        calculated_area=float(calculated.area),
        calculated_height=float(calculated.height),
        retention_time_reference=reference,
        retention_time_generated=generated,
        sigma=float(calculated.sigma_minutes),
        peak_imperfection_level=imperfection_level,
        internal_seed=seed,
        model_version=str(_payload["version"]),
    )

_core.calculate_peak = calculate_peak

def get_descriptor():
    return {
        "method_id": METHOD_ID,
        "calibration_model_path": MODEL_PATH,
        "version": str(_payload["version"]),
    }

def __getattr__(name: str):
    return getattr(_core, name)

def __dir__():
    return sorted(set(globals()) | set(dir(_core)))

for _name in (
    "generate_single",
    "generate_actual",
    "generate_random",
    "generate_from_excel",
    "load_passport",
    "parse_datetime",
    "safe_name",
):
    if hasattr(_core, _name):
        globals()[_name] = getattr(_core, _name)
