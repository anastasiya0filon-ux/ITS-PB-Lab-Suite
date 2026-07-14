# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw

from . import geometry
from .axes import draw_axes
from .integration import draw_labels
from .signal import build_signal
from .spec import detector_spec


TARGET_APEX_FRACTION = 0.89
SIGNAL_TOP_MARGIN_PX = 4
MIN_Y_MAX = 1e-9


def _seed(*parts):
    digest = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return int.from_bytes(digest[:8], "big") & 0x7FFFFFFF


def _pixel_trace(samples, *, y_max, x_min, x_max, rnd):
    columns: dict[int, list[float]] = {}
    for t, value in samples:
        x = int(round(geometry.x_to_px(t, x_min, x_max)))
        y = geometry.y_to_px(value, y_max)
        columns.setdefault(x, []).append(y)

    points = []
    last_y = geometry.PLOT_Y1
    recorder = 0.0

    for x in range(geometry.PLOT_X0, geometry.PLOT_X1 + 1):
        ys = columns.get(x)
        y = min(ys) if ys else last_y

        level = max(
            0.0,
            min(1.0, (geometry.PLOT_Y1 - y) / max(1, geometry.PLOT_HEIGHT)),
        )
        recorder = 0.78 * recorder + 0.22 * rnd.uniform(-0.72, 0.72)
        y += recorder * (1.0 - 0.50 * level)

        y = max(geometry.PLOT_Y0, min(geometry.PLOT_Y1, y))
        y = float(int(round(y)))
        points.append((x, y))
        last_y = y

    return points


def _nice_ceiling(value: float) -> float:
    value = max(float(value), MIN_Y_MAX)
    exponent = math.floor(math.log10(value))
    base = 10.0 ** exponent
    fraction = value / base

    for candidate in (1.0, 1.2, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0):
        if fraction <= candidate + 1e-12:
            return candidate * base
    return 10.0 * base


def _nearest_time_value(samples, target):
    if not samples:
        return 0.0
    return min(samples, key=lambda row: abs(row[0] - target))[1]


def _chromatek_scale(peaks, samples):
    integrated_max = max(
        (
            float(_nearest_time_value(samples, float(peak.retention_time_generated)))
            for peak in peaks
        ),
        default=MIN_Y_MAX,
    )
    full_signal_max = max(
        (float(value) for _, value in samples),
        default=integrated_max,
    )

    by_integrated_peak = integrated_max / TARGET_APEX_FRACTION
    usable_fraction = max(
        0.01,
        (geometry.PLOT_HEIGHT - SIGNAL_TOP_MARGIN_PX) / geometry.PLOT_HEIGHT,
    )
    by_full_signal = full_signal_max / usable_fraction

    y_max = _nice_ceiling(max(MIN_Y_MAX, by_integrated_peak, by_full_signal))
    return y_max, y_max / 5.0


def render_chromatogram(
    peaks,
    output_path: Path,
    *,
    detector: str,
    x_min: float = 0.0,
    x_max: float = 38.96,
    y_max: float | None = None,
    y_tick_step: float | None = None,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    positive = [
        peak for peak in peaks
        if float(getattr(peak, "input_concentration", 0.0)) > 0.0
        and float(getattr(peak, "calculated_height", 0.0)) > 0.0
    ]

    sample_code = positive[0].sample_code if positive else "blank"
    chromatogram_index = positive[0].chromatogram_index if positive else 0
    seed = _seed("CHROMATEK_ENGINE_3_0", detector, sample_code, chromatogram_index)

    max_height = max(
        (float(getattr(peak, "calculated_height", 0.0)) for peak in positive),
        default=1e-6,
    )
    provisional_y = max(max_height * 1.15, 1e-6)

    provisional_samples, _ = build_signal(
        positive,
        detector=detector,
        y_max=provisional_y,
        seed=seed,
        x_min=x_min,
        x_max=x_max,
    )

    y_max, y_tick_step = _chromatek_scale(positive, provisional_samples)

    samples, events = build_signal(
        positive,
        detector=detector,
        y_max=y_max,
        seed=seed,
        x_min=x_min,
        x_max=x_max,
    )

    image = Image.new(
        "RGBA",
        (geometry.WIDTH, geometry.HEIGHT),
        (255, 255, 255, 255),
    )

    draw_axes(
        image,
        detector=detector,
        y_max=y_max,
        x_min=x_min,
        x_max=x_max,
        y_tick_step=y_tick_step,
    )

    draw = ImageDraw.Draw(image)
    color = tuple(detector_spec(detector)["rgb"])
    rnd = random.Random(seed ^ 0x5A17)
    points = _pixel_trace(
        samples, y_max=y_max, x_min=x_min, x_max=x_max, rnd=rnd,
    )

    for index in range(1, len(points)):
        x0, y0 = points[index - 1]
        x1, y1 = points[index]

        if index % 181 == 0 and rnd.random() < 0.22:
            continue

        # Основная линия 1 px.
        draw.line((x0, y0, x1, y1), fill=color, width=1)

        # Редкий соседний пиксель создаёт визуальную плотность Хроматэка,
        # но не превращает кривую в сплошную линию шириной 2 px.
        if index % 3 == 0 and abs(y1 - y0) >= 1:
            py = int(max(geometry.PLOT_Y0, min(geometry.PLOT_Y1, y1 + 1)))
            draw.point((x1, py), fill=color)

        if index % 71 == 0 and rnd.random() < 0.34:
            py = int(max(
                geometry.PLOT_Y0,
                min(geometry.PLOT_Y1, y1 + rnd.choice((-1, 1))),
            ))
            draw.point((x1, py), fill=color)

    draw_labels(
        image,
        peaks=positive,
        samples=samples,
        events=events,
        detector=detector,
        y_max=y_max,
        seed=seed,
        x_min=x_min,
        x_max=x_max,
    )

    image.convert("RGB").save(output_path, "PNG")
    return output_path
