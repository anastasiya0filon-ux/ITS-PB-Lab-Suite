# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import math
import random
from functools import lru_cache
from pathlib import Path

from .peaks import peak_value


_PROFILE_PATH = Path(__file__).with_name("reference_baseline_profile.json")


@lru_cache(maxsize=1)

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


def _profiles():
    return json.loads(_PROFILE_PATH.read_text(encoding="utf-8"))["detectors"]


def _interp(t: float, knots: list[list[float]]) -> float:
    if t <= knots[0][0]:
        return float(knots[0][1])
    for (x0, y0), (x1, y1) in zip(knots, knots[1:]):
        if x0 <= t <= x1:
            u = (t - x0) / max(x1 - x0, 1e-12)
            # Плавная интерполяция без искусственных изломов.
            u = u * u * (3.0 - 2.0 * u)
            return float(y0) + (float(y1) - float(y0)) * u
    return float(knots[-1][1])


def build_signal(peaks, *, detector, y_max, seed, x_min, x_max, count=7200):
    """Строит сигнал на эталонной базовой линии.

    Случайные кластеры и придуманные фоновые пики отключены.
    Остаётся только ограниченный детерминированный шум вокруг профиля,
    снятого с эталонных хроматограмм.
    """
    rnd = random.Random(seed)
    profile = _profiles()[detector]
    baseline_knots = profile["knots"]
    noise_knots = profile["noise_fraction"]

    fast = 0.0
    medium = 0.0
    slow = 0.0
    samples = []

    phase = 0.21 if detector == "ПИД-1" else 1.17

    for i in range(count):
        t = x_min + (x_max - x_min) * i / (count - 1)

        fast = 0.55 * fast + 0.45 * rnd.gauss(0.0, 1.0)
        medium = 0.95 * medium + 0.05 * rnd.gauss(0.0, 1.0)
        slow = 0.9975 * slow + 0.0025 * rnd.gauss(0.0, 1.0)

        baseline_fraction = _interp(t, baseline_knots)
        noise_fraction = _interp(t, noise_knots)

        # Шум ограничен вокруг эталонного профиля и не создаёт ложных пиков.
        noise = noise_fraction * (
            0.52 * fast
            + 0.31 * medium
            + 0.17 * slow
        )
        noise += noise_fraction * 0.18 * math.sin(0.61 * t + phase)
        noise += noise_fraction * 0.09 * math.sin(2.37 * t + 0.4 * phase)

        value = y_max * max(0.0, baseline_fraction + noise)

        for peak in peaks:
            value += peak_value(t, peak)

        samples.append((t, value))

    # Список фоновых событий пуст: подписи без аналитических пиков невозможны.
    return samples, []
