# GC_PID1_LINE_WIDTH_104_INTENSITY_65_FIX_13A
# GC_GRAPH_LINE_INTENSITY_85_FIX_13
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
from .peaks import peak_value
from .signal import build_signal
from .spec import detector_spec
from .graph_line_intensity_fix_13 import soften_graph_line_color, draw_graph_line_width_104


TARGET_APEX_FRACTION = 0.80
SIGNAL_TOP_MARGIN_PX = 4
MIN_Y_MAX = 1e-9
AUTO_SCALE_PASSES = 4
DETECTOR_X_MAX = {"ПИД-1": 38.956, "ПИД-2": 38.954}


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


def _concentration_character(peaks):
    """Возвращает мягкий коэффициент приборной неидеальности.

    Он влияет только на микродрейф уже построенного растра и не меняет
    площади, высоты или времена удерживания из математического ядра.
    """
    active = [
        max(0.0, float(getattr(peak, "input_concentration", 0.0)))
        for peak in peaks
        if float(getattr(peak, "input_concentration", 0.0)) > 0.0
    ]
    if not active:
        return 1.0
    characteristic = sorted(active)[len(active) // 2]
    # Малые концентрации немного сильнее проявляют шум и дрейф,
    # но не превращаются в отдельный искусственный профиль.
    return 1.0 + 0.22 / (1.0 + 18.0 * characteristic)


def _naturalize_samples(samples, *, peaks, y_max, detector, seed, x_min, x_max):
    """Приборная неидеальность baseline без изменения расчётного ядра.

    Коррекция выполняется только над готовым сигналом рендера:
    - слабый многомасштабный дрейф по всей хроматограмме;
    - неравномерный поздний подъём после 33 минут;
    - небольшие изменения угла и локальные микроколебания;
    - подавление добавки непосредственно возле аналитических пиков.
    """
    if not samples:
        return samples

    rnd = random.Random(seed ^ 0x3D71)
    character = _concentration_character(peaks)
    detector_factor = 1.00 if detector == "ПИД-1" else 1.08
    amplitude = y_max * 0.00048 * character * detector_factor

    peak_times = sorted(
        float(getattr(peak, "retention_time_generated", 0.0))
        for peak in peaks
    )

    fast = 0.0
    medium = 0.0
    slow = 0.0
    result = []
    span = max(x_max - x_min, 1e-12)
    phase = 0.37 if detector == "ПИД-1" else 1.19

    def smoothstep(value: float) -> float:
        value = max(0.0, min(1.0, value))
        return value * value * (3.0 - 2.0 * value)

    for t, value in samples:
        fast = 0.68 * fast + 0.32 * rnd.gauss(0.0, 1.0)
        medium = 0.965 * medium + 0.035 * rnd.gauss(0.0, 1.0)
        slow = 0.9982 * slow + 0.0018 * rnd.gauss(0.0, 1.0)

        progress = max(0.0, min(1.0, (t - x_min) / span))
        late = smoothstep((t - 32.7) / 5.9)

        # Несколько неповторяющихся временных масштабов дают характер
        # самописца, а не гладкую математическую кривую.
        periodic = (
            0.34 * math.sin(0.83 * t + phase)
            + 0.19 * math.sin(2.21 * t + 0.7 * phase)
            + 0.11 * math.sin(5.17 * t + 1.6 * phase)
        )
        stochastic = 0.44 * fast + 0.36 * medium + 0.20 * slow

        # Поздняя зона получает меняющийся угол подъёма и локальные
        # замедления/ускорения, но без искусственных фоновых пиков.
        late_shape = late * (
            0.58 * math.sin(1.31 * (t - 32.7) + phase)
            + 0.27 * math.sin(3.07 * (t - 32.7) + 0.4)
        )
        drift = amplitude * (
            (0.72 + 0.28 * progress) * stochastic
            + 0.36 * periodic
            + 1.15 * late_shape
        )

        # Возле аналитических пиков baseline-коррекция ослабляется,
        # поэтому видимые вершины, RT и относительная форма пиков
        # остаются под управлением существующего peak engine.
        if peak_times:
            distance = min(abs(t - rt) for rt in peak_times)
            peak_guard = smoothstep(distance / 0.085)
        else:
            peak_guard = 1.0

        corrected = max(0.0, float(value) + drift * peak_guard)
        result.append((t, corrected))

    return result


def _peak_visual_character(peak, detector: str):
    """Детерминированные приборные вариации формы без изменения RT/height."""
    key = (
        f"{detector}|{getattr(peak, 'component', '')}|"
        f"{getattr(peak, 'chromatogram_index', 0)}"
    )
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    u0 = digest[0] / 255.0
    u1 = digest[1] / 255.0
    u2 = digest[2] / 255.0
    u3 = digest[3] / 255.0

    # Небольшая независимая вариативность переднего и заднего фронтов.
    left_stretch = 0.92 + 0.16 * u0
    right_stretch = 1.00 + 0.24 * u1
    tail_fraction = 0.006 + 0.022 * u2
    tail_tau = 0.030 + 0.055 * u3

    if detector == "ПИД-2":
        right_stretch *= 1.025
        tail_fraction *= 1.08

    return left_stretch, right_stretch, tail_fraction, tail_tau


def _visual_peak_value(t: float, peak, detector: str) -> float:
    """Визуальная форма пика с сохранением вершины в расчётном RT."""
    tr = float(getattr(peak, "retention_time_generated", 0.0))
    height = max(0.0, float(getattr(peak, "calculated_height", 0.0)))
    if height <= 0.0:
        return 0.0

    left_stretch, right_stretch, tail_fraction, tail_tau = (
        _peak_visual_character(peak, detector)
    )
    dt = t - tr
    stretch = left_stretch if dt < 0.0 else right_stretch
    mapped_t = tr + dt / max(stretch, 1e-9)

    # Основная форма берётся из действующего peak engine.
    value = peak_value(mapped_t, peak)

    # Слабый хвост начинается после вершины и равен нулю в самом RT,
    # поэтому расчётная высота и положение максимума не сдвигаются.
    if dt > 0.0:
        onset = 1.0 - math.exp(-dt / 0.010)
        value += (
            height
            * tail_fraction
            * onset
            * math.exp(-dt / max(tail_tau, 1e-9))
        )

    return max(0.0, value)


def _build_natural_peak_signal(
    peaks, *, detector, y_max, seed, x_min, x_max, count=7200,
):
    """Собирает baseline и визуально неидеальные пики раздельно.

    Математические RT, площади, высоты и концентрации не изменяются.
    Меняется только растровая форма склонов и хвостов пиков.
    """
    baseline, _ = build_signal(
        [], detector=detector, y_max=y_max, seed=seed,
        x_min=x_min, x_max=x_max, count=count,
    )

    result = []
    for t, baseline_value in baseline:
        value = float(baseline_value)
        for peak in peaks:
            value += _visual_peak_value(t, peak, detector)
        result.append((t, value))

    return result, []
def _auto_scaled_signal(peaks, *, detector, seed, x_min, x_max):
    """Строит полный сигнал и итерационно выбирает его шкалу.

    Входные y_max/y_tick_step из старых концентрационных профилей здесь
    намеренно не используются. Шкала является результатом конкретной
    хроматограммы.
    """
    max_height = max(
        (float(getattr(peak, "calculated_height", 0.0)) for peak in peaks),
        default=1e-6,
    )
    y_max = _nice_ceiling(max(max_height * 1.22, 1e-6))
    samples = []
    events = []

    for _ in range(AUTO_SCALE_PASSES):
        samples, events = _build_natural_peak_signal(
            peaks,
            detector=detector,
            y_max=y_max,
            seed=seed,
            x_min=x_min,
            x_max=x_max,
        )
        samples = _naturalize_samples(
            samples, peaks=peaks, y_max=y_max, detector=detector,
            seed=seed, x_min=x_min, x_max=x_max,
        )
        next_y_max, _ = _chromatek_scale(peaks, samples)
        if abs(next_y_max - y_max) <= max(1e-9, y_max * 0.001):
            y_max = next_y_max
            break
        y_max = next_y_max

    # Финальная сборка строго в окончательной шкале.
    samples, events = _build_natural_peak_signal(
        peaks, detector=detector, y_max=y_max, seed=seed,
        x_min=x_min, x_max=x_max,
    )
    samples = _naturalize_samples(
        samples, peaks=peaks, y_max=y_max, detector=detector,
        seed=seed, x_min=x_min, x_max=x_max,
    )
    return samples, events, y_max, y_max / 5.0


def _chromatek_scale(peaks, samples):
    integrated_max = max(
        (
            float(_nearest_time_value(
                samples,
                float(peak.retention_time_generated),
            ))
            for peak in peaks
        ),
        default=MIN_Y_MAX,
    )
    full_signal_max = max(
        (float(value) for _, value in samples),
        default=integrated_max,
    )

    longest_label = max(
        (
            len(
                f"{float(peak.retention_time_generated):.3f} "
                f"{peak.component} "
                f"{float(peak.calculated_area):.3f}"
            )
            for peak in peaks
        ),
        default=20,
    )

    # Динамический запас 20–30%:
    # короткие подписи ≈20%, длинные постепенно увеличивают запас до 30%.
    headroom = 0.20 + min(0.10, max(0.0, longest_label - 18) * 0.004)
    by_integrated_peak = integrated_max * (1.0 + headroom)

    usable_fraction = max(
        0.01,
        (geometry.PLOT_HEIGHT - SIGNAL_TOP_MARGIN_PX)
        / geometry.PLOT_HEIGHT,
    )
    by_full_signal = full_signal_max / usable_fraction

    y_max = _nice_ceiling(
        max(MIN_Y_MAX, by_integrated_peak, by_full_signal)
    )
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

    # Старые y_max/y_tick_step могли быть переданы из таблицы концентраций.
    # Для изображения они больше не являются входными параметрами.
    x_max = DETECTOR_X_MAX.get(detector, float(x_max))
    samples, events, y_max, y_tick_step = _auto_scaled_signal(
        positive,
        detector=detector,
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

        # Непрерывная приборная линия 1 px. Неидеальность формируется
        # самим сигналом и микродрейфом, а не искусственными разрывами.
        draw_graph_line_width_104(draw, (x0, y0, x1, y1), fill=soften_graph_line_color(color, detector), width=1, detector=detector)

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
