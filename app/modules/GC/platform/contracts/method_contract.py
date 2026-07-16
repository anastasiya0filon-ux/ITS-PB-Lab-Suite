# -*- coding: utf-8 -*-
"""Универсальный контракт между математикой НД и платформой Хроматэк."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence


@dataclass(frozen=True)
class ChromatographicPeak:
    component: str
    detector: str
    retention_time: float
    area: float
    height: float
    concentration: float
    unit: str = "мг/дм3"
    sigma: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChromatogramResult:
    method_id: str
    sample_code: str
    chromatogram_index: int
    analysis_time_iso: str
    peaks: Sequence[ChromatographicPeak]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MethodDescriptor:
    method_id: str
    title: str
    version: str
    calibration_model_path: Path
    supported_detectors: tuple[str, ...]
    default_duration_min: float
    renderer_profile_id: str
    report_profile_id: str


class MethodEngine(Protocol):
    """НД обязан только рассчитывать данные, но не рисовать и не собирать DOCX."""

    descriptor: MethodDescriptor

    def calculate(self, request: Mapping[str, Any]) -> Sequence[ChromatogramResult]:
        ...


def validate_result(result: ChromatogramResult) -> None:
    if not result.method_id:
        raise ValueError("method_id не задан")
    if result.chromatogram_index < 1:
        raise ValueError("chromatogram_index должен быть >= 1")
    for peak in result.peaks:
        if not peak.component.strip():
            raise ValueError("Пустое название компонента")
        if not peak.detector.strip():
            raise ValueError(f"Не задан детектор для {peak.component}")
        if peak.retention_time < 0:
            raise ValueError(f"Отрицательное RT для {peak.component}")
        if peak.area < 0 or peak.height < 0 or peak.concentration < 0:
            raise ValueError(f"Отрицательное расчётное значение для {peak.component}")
