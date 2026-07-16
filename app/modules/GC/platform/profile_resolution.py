# -*- coding: utf-8 -*-
"""Разрешение профилей по выбранной методике.

Методика имеет право переключать только:
- math_profile;
- report_profile.

Все приборные профили берутся из instrument_profile и являются общими.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

GC_DIR = Path(__file__).resolve().parents[1]
REGISTRY_PATH = GC_DIR / "methods" / "registry.json"
PROFILES_DIR = GC_DIR / "profiles"


@dataclass(frozen=True)
class EffectiveMethodConfiguration:
    method_id: str
    title: str
    math_profile: str
    report_profile: str
    instrument_profile: str
    renderer_profile: str
    chromatogram_count: int


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _registry() -> dict[str, Any]:
    return _read_json(REGISTRY_PATH)


def _entry_id(item: dict[str, Any]) -> str:
    return str(item.get("id") or item.get("method_id") or "")


def resolve_method(method_id: str) -> EffectiveMethodConfiguration:
    entries = _registry().get("methods", [])
    for item in entries:
        if isinstance(item, dict) and _entry_id(item) == method_id:
            if not item.get("enabled", True) or not item.get("implemented", False):
                raise ValueError(f"Методика ещё не готова: {item.get('title', method_id)}")
            return EffectiveMethodConfiguration(
                method_id=method_id,
                title=str(item.get("title") or method_id),
                math_profile=str(item.get("math_profile") or method_id),
                report_profile=str(item.get("report_profile") or "chromatek_standard"),
                instrument_profile=str(
                    item.get("instrument_profile")
                    or _registry().get("shared_instrument_profile")
                    or "chromatek_crystal5000_v03_21_17_721"
                ),
                renderer_profile=str(item.get("renderer_profile") or "chromatek_standard"),
                chromatogram_count=int(item.get("chromatogram_count", 2)),
            )
    raise ValueError(f"Неизвестная методика GC: {method_id}")


def load_instrument_profile(profile_id: str) -> dict[str, Any]:
    return _read_json(PROFILES_DIR / "firmwares" / f"{profile_id}.json")


def load_report_profile(profile_id: str) -> dict[str, Any]:
    return _read_json(PROFILES_DIR / "reports" / f"{profile_id}.json")


def effective_profiles(method_id: str) -> dict[str, Any]:
    method = resolve_method(method_id)
    instrument = load_instrument_profile(method.instrument_profile)
    report = load_report_profile(method.report_profile)
    return {
        "method": method,
        "instrument": instrument,
        "report": report,
        "math_profile": method.math_profile,
        "renderer_profile": method.renderer_profile,
    }


def clear_cache() -> None:
    _registry.cache_clear()
