# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import random
from pathlib import Path

from PIL import Image, ImageDraw

from . import geometry
from .axes import draw_axes, nice_y_max
from .integration import draw_labels
from .signal import build_signal
from .spec import detector_spec


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

        # Native one-pixel quantization is part of the Chromatek appearance.
        y = float(int(round(y)))
        points.append((x, y))
        last_y = y

    return points


def render_chromatogram(
    peaks,
    output_path: Path,
    *,
    detector: str,
    x_min: float = 0.0,
    x_max: float = 38.96,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    image = Image.new(
        "RGBA",
        (geometry.WIDTH, geometry.HEIGHT),
        (255, 255, 255, 255),
    )

    positive = [
        peak
        for peak in peaks
        if float(getattr(peak, "input_concentration", 0.0)) > 0.0
        and float(getattr(peak, "calculated_height", 0.0)) > 0.0
    ]

    max_height = max(
        (float(peak.calculated_height) for peak in positive),
        default=1.0,
    )
    y_max = nice_y_max(max_height * 1.08)

    sample_code = positive[0].sample_code if positive else "blank"
    chromatogram_index = positive[0].chromatogram_index if positive else 0
    seed = _seed(
        "CHROMATEK_ENGINE_3_0",
        detector,
        sample_code,
        chromatogram_index,
    )

    draw_axes(
        image,
        detector=detector,
        y_max=y_max,
        x_min=x_min,
        x_max=x_max,
    )

    samples, events = build_signal(
        positive,
        detector=detector,
        y_max=y_max,
        seed=seed,
        x_min=x_min,
        x_max=x_max,
    )

    draw = ImageDraw.Draw(image)
    color = tuple(detector_spec(detector)["rgb"])
    rnd = random.Random(seed ^ 0x5A17)
    points = _pixel_trace(
        samples,
        y_max=y_max,
        x_min=x_min,
        x_max=x_max,
        rnd=rnd,
    )

    for index in range(1, len(points)):
        x0, y0 = points[index - 1]
        x1, y1 = points[index]

        # Rare recorder dropouts and isolated double pixels.
        if index % 181 == 0 and rnd.random() < 0.22:
            continue

        draw.line((x0, y0, x1, y1), fill=color, width=1)

        if index % 71 == 0 and rnd.random() < 0.34:
            draw.point((x1, int(y1 + rnd.choice((-1, 1)))), fill=color)
        if index % 239 == 0 and rnd.random() < 0.38:
            draw.point((x1, int(y1)), fill=color)

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
