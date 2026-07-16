# -*- coding: utf-8 -*-
"""Единый реестр выбора методики для GC-интерфейса.

Этот модуль не выполняет расчёты и не рисует хроматограммы. Он только сообщает
интерфейсу, какие методы готовы к использованию и какие профили им назначены.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

GC_DIR = Path(__file__).resolve().parents[1]
REGISTRY_PATH = GC_DIR / "methods" / "registry.json"


@dataclass(frozen=True)
class MethodDescriptor:
    method_id: str
    title: str
    chromatogram_count: int
    math_profile: str
    report_profile: str
    renderer_profile: str
    enabled: bool = True
    implemented: bool = False


@lru_cache(maxsize=1)
def load_registry() -> dict[str, MethodDescriptor]:
    raw = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    entries = raw.get("methods", raw if isinstance(raw, list) else [])
    result: dict[str, MethodDescriptor] = {}
    for item in entries:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        descriptor = MethodDescriptor(
            method_id=str(item["id"]),
            title=str(item.get("title") or item["id"]),
            chromatogram_count=int(item.get("chromatogram_count", 2)),
            math_profile=str(item.get("math_profile") or item["id"]),
            report_profile=str(item.get("report_profile") or "chromatek_standard"),
            renderer_profile=str(item.get("renderer_profile") or "chromatek_crystal_5000"),
            enabled=bool(item.get("enabled", False)),
            implemented=bool(item.get("implemented", False)),
        )
        result[descriptor.method_id] = descriptor
    return result


def available_methods() -> list[MethodDescriptor]:
    return [
        item for item in load_registry().values()
        if item.enabled and item.implemented
    ]


def combo_items() -> list[tuple[str, str]]:
    return [(item.method_id, item.title) for item in available_methods()]


def get_method(method_id: str) -> MethodDescriptor:
    try:
        descriptor = load_registry()[method_id]
    except KeyError as exc:
        raise ValueError(f"Неизвестная методика GC: {method_id}") from exc
    if not descriptor.enabled or not descriptor.implemented:
        raise ValueError(f"Методика ещё не готова к использованию: {descriptor.title}")
    return descriptor


def clear_cache() -> None:
    load_registry.cache_clear()
