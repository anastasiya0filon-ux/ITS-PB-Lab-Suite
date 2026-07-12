# -*- coding: utf-8 -*-
from __future__ import annotations

import math
import random

from .peaks import peak_value
from .profiles import clusters_for, late_knots
from .spec import detector_spec


def _interp_knots(t, knots):
    if t <= knots[0][0]:
        return knots[0][1]
    for (x0, y0), (x1, y1) in zip(knots, knots[1:]):
        if x0 <= t <= x1:
            u = (t - x0) / (x1 - x0)
            u = u * u * (3.0 - 2.0 * u)
            return y0 + (y1 - y0) * u
    return knots[-1][1]


def build_background_events(rnd, detector, y_max):
    events = []
    for lo, hi, count in clusters_for(detector):
        actual = max(1, count + rnd.randint(-2, 3))
        centers = sorted(rnd.uniform(lo, hi) for _ in range(actual))
        for index, center in enumerate(centers):
            late = center >= 33.5
            amplitude = y_max * rnd.uniform(
                0.00018,
                0.00145 if not late else 0.0048,
            )
            if late and index % 5 == 0:
                amplitude *= rnd.uniform(1.35, 2.45)
            width = rnd.uniform(0.008, 0.031) * (1.0 + center / 145.0)
            kind = rnd.random()
            events.append((center, amplitude, width, kind))
    return events


def build_signal(peaks, *, detector, y_max, seed, x_min, x_max, count=7200):
    rnd = random.Random(seed)
    ds = detector_spec(detector)
    events = build_background_events(rnd, detector, y_max)
    knots = late_knots(detector)

    fast = 0.0
    medium = 0.0
    slow = 0.0
    random_walk = 0.0
    samples = []
    phase = 0.17 if detector == "ПИД-1" else 1.11

    for i in range(count):
        t = x_min + (x_max - x_min) * i / (count - 1)

        fast = 0.58 * fast + 0.42 * rnd.gauss(0.0, 1.0)
        medium = 0.94 * medium + 0.06 * rnd.gauss(0.0, 1.0)
        slow = 0.997 * slow + 0.003 * rnd.gauss(0.0, 1.0)
        random_walk = 0.9992 * random_walk + 0.0008 * rnd.gauss(0.0, 1.0)

        late_factor = max(0.0, min(1.0, (t - 25.0) / 13.96))
        noise_scale = 1.0 + 1.9 * late_factor * late_factor

        fraction = float(ds["baseline_fraction"])
        fraction += float(ds["noise_fraction"]) * noise_scale * (
            0.50 * fast + 0.30 * medium + 0.20 * slow
        )
        fraction += 0.00023 * math.sin(0.47 * t + phase)
        fraction += 0.00010 * math.sin(2.08 * t + 0.7 * phase)
        fraction += 0.000045 * math.sin(6.35 * t + phase)
        fraction += 0.00035 * random_walk
        fraction += _interp_knots(t, knots)

        value = y_max * max(0.0, fraction)

        for center, amplitude, width, kind in events:
            dt = t - center
            if abs(dt) >= 5.5 * width:
                continue
            # Narrow instrument event with small asymmetric after-tail.
            value += amplitude * math.exp(-0.5 * (dt / width) ** 2)
            if dt > 0.0 and kind > 0.72:
                value += amplitude * 0.10 * math.exp(
                    -dt / max(0.025, width * 2.8)
                )

        for peak in peaks:
            value += peak_value(t, peak)

        samples.append((t, value))

    return samples, events
