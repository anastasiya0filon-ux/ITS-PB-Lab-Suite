# -*- coding: utf-8 -*-
"""Первый рабочий генератор газовой хроматографии для МУК 4.1.3166.

Выход первого этапа:
- JSON-паспорт каждой генерации;
- отдельные PNG для каждой хроматограммы и каждого детектора;
- CSV с рассчитанными пиками.

Печатная форма подключается следующим этапом через общий RTF Clone Engine.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import re
import zipfile
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
TEMPLATE_DIR = ROOT / "excel_templates"
OUTPUT_DIR = ROOT / "output"

METHOD_ID = "MUK_4_1_3166"
METHOD_TITLE = "МУК 4.1.3166"
GC_RENDERER_PATCH = "GC_REFERENCE_LAYOUT_V8"
DETECTORS = ("ПИД-1", "ПИД-2")
CHROMATOGRAM_COUNT = 2
FINAL_RENDERER_VERSION = "9.0-crystal5000-reference-locked"

COMPONENT_DEFAULTS = [
    ("Этилацетат", 0.0001),
    ("Акрилонитрил", 0.003),
    ("Альфа-метилстирол", 0.00001),
    ("Ацетальдегид", 0.0001),
    ("Ацетон", 0.0001),
    ("Бензол", 0.00001),
    ("Гексан", 0.00001),
    ("Гептан", 0.00001),
    ("Кумол (изопропил бензол)", 0.00001),
    ("Спирт изобутиловый", 0.0001),
    ("Спирт метиловый", 0.0001),
    ("Стирол", 0.00001),
    ("Спирт изопропиловый", 0.0001),
    ("Метилацетат", 0.0001),
    ("Спирт бутиловый", 0.0001),
    ("Спирт пропиловый", 0.0001),
    ("н-Бутанол", 0.0001),
    ("н-Пропанол", 0.0001),
    ("Изопропанол", 0.0001),
    ("Изобутанол", 0.0001),
    ("Метанол", 0.0001),
    ("о-Ксилол", 0.00001),
    ("п-Ксилол", 0.00001),
    ("м-ксилол", 0.00001),
    ("Ксилолы (смесь изомеров)", 0.00001),
    ("Этилбензол", 0.00001),
    ("Бутилацетат", 0.0001),
    ("Толуол", 0.00001),
]

ALIASES = {
    "альфа-метилстирол": "Метилстирол",
    "кумол (изопропил бензол)": "Изопропилбензол",
    "кумол (изопропилбензол)": "Изопропилбензол",
    "спирт изобутиловый": "Изобутанол",
    "спирт метиловый": "Метанол",
    "спирт изопропиловый": "Изопропанол",
    "спирт бутиловый": "Н-бутанол",
    "спирт пропиловый": "Н-пропанол",
    "н-бутанол": "Н-бутанол",
    "н-пропанол": "Н-пропанол",
    "бутилацетат": "Бутилацетат",
    "бутилацета": "Бутилацетат",
    "м-ксилол": "м-Ксилол",
    "п-ксилол": "п-Ксилол",
    "о-ксилол": "о-Ксилол",
}

SS_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


@dataclass
class PeakRecord:
    method_id: str
    sample_code: str
    chromatogram_index: int
    detector: str
    component: str
    input_concentration: float
    calculated_area: float
    calculated_height: float
    retention_time_reference: float
    retention_time_generated: float
    sigma: float
    peak_imperfection_level: int
    internal_seed: int
    model_version: str


def safe_name(value: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "_", str(value).strip() or "sample")


def _excel_serial_to_datetime(value: float) -> datetime:
    # Standard Windows Excel date system.
    return datetime(1899, 12, 30) + timedelta(days=float(value))


def _parse_excel_or_text_date(value) -> datetime:
    if isinstance(value, datetime):
        return value

    raw = str(value).strip()
    if not raw:
        raise ValueError("Дата не указана")

    # Excel serial date, for example 46213 or 46213.0.
    try:
        number = float(raw.replace(",", "."))
        if number >= 1:
            return _excel_serial_to_datetime(number)
    except ValueError:
        pass

    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            pass

    raise ValueError(f"Некорректная дата: {raw!r}")


def _parse_excel_or_text_time(value) -> tuple[int, int, int]:
    if isinstance(value, datetime):
        return value.hour, value.minute, value.second

    raw = str(value).strip()
    if not raw:
        return 9, 0, 0

    # Excel stores time as a fraction of one day.
    try:
        number = float(raw.replace(",", "."))
        fraction = number % 1.0
        total_seconds = int(round(fraction * 86400)) % 86400
        hour, remainder = divmod(total_seconds, 3600)
        minute, second = divmod(remainder, 60)
        return hour, minute, second
    except ValueError:
        pass

    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            parsed = datetime.strptime(raw, fmt)
            return parsed.hour, parsed.minute, parsed.second
        except ValueError:
            pass

    raise ValueError(f"Некорректное время: {raw!r}")


def parse_datetime(date_text: str, time_text: str) -> datetime:
    # Accepts text values and native Excel serial date/time values.
    date_value = _parse_excel_or_text_date(date_text)
    hour, minute, second = _parse_excel_or_text_time(time_text)
    return date_value.replace(
        hour=hour,
        minute=minute,
        second=second,
        microsecond=0,
    )


def stable_seed(*parts: object) -> int:
    raw = "|".join(str(p) for p in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big") & 0x7FFFFFFF


def load_passport() -> dict:
    with (DATA_DIR / "MUK_4_1_3166.json").open("r", encoding="utf-8") as f:
        return json.load(f)


def load_models() -> dict:
    with (DATA_DIR / "gc_muk_4_1_3166_calibration_model.json").open("r", encoding="utf-8") as f:
        payload = json.load(f)

    index = {}
    for item in payload.get("models", []):
        component = str(item.get("component", "")).strip()
        if component == "Бутилацета":
            component = "Бутилацетат"
        key = (component.casefold(), str(item.get("detector", "")).strip())
        index[key] = item
    return {"payload": payload, "index": index}


def normalize_component(name: str) -> str:
    clean = str(name).strip()
    return ALIASES.get(clean.casefold(), clean)


def model_for(models: dict, component: str, detector: str) -> dict | None:
    normalized = normalize_component(component)
    exact = models["index"].get((normalized.casefold(), detector))
    if exact:
        return exact

    # Combined detector entry, e.g. "Стирол, о-Ксилол".
    for (model_name, model_detector), item in models["index"].items():
        if model_detector != detector:
            continue
        tokens = [x.strip().casefold() for x in model_name.split(",")]
        if normalized.casefold() in tokens:
            return item
    return None


def eval_quadratic_origin(model: dict, concentration: float) -> float:
    coeff = model["coefficients"]
    return float(coeff["a_linear"]) * concentration + float(coeff["b_quadratic"]) * concentration ** 2


def generated_retention_time(reference: float, seed: int) -> float:
    rnd = random.Random(seed)
    # Жесткое окно ±5%; распределение сосредоточено ближе к среднему.
    shift = max(-0.05, min(0.05, rnd.gauss(0.0, 0.014)))
    return reference * (1.0 + shift)


def split_random_concentrations(base: float, seed: int) -> tuple[float, float]:
    """Детерминированная пара вокруг базового значения.

    Диапазон отклонения предварительный: 0,5–3,0%.
    Его можно изменить в паспорте методики без изменения остального ядра.
    """
    if base < 0:
        raise ValueError("Концентрация не может быть отрицательной")
    rnd = random.Random(seed)
    delta = rnd.uniform(0.005, 0.03)
    asym = rnd.uniform(-0.20, 0.20)
    c1 = max(0.0, base * (1.0 - delta * (1.0 + asym)))
    c2 = max(0.0, base * (1.0 + delta * (1.0 - asym)))
    return c1, c2


def calculate_peak(
    models: dict,
    *,
    sample_code: str,
    chromatogram_index: int,
    detector: str,
    component: str,
    concentration: float,
    imperfection_level: int = 2,
) -> PeakRecord | None:
    model = model_for(models, component, detector)
    if model is None:
        return None
    if concentration < 0:
        raise ValueError(f"{component}: концентрация не может быть отрицательной")

    area = max(0.0, eval_quadratic_origin(model["area"], concentration))
    height = max(0.0, eval_quadratic_origin(model["height"], concentration))
    reference = float(model["retention_time_mean"])
    seed = stable_seed(METHOD_ID, sample_code, chromatogram_index, detector, component, f"{concentration:.12g}")
    generated = generated_retention_time(reference, seed)
    sigma = area / (60.0 * height * math.sqrt(2.0 * math.pi)) if height > 0 else 0.0

    return PeakRecord(
        method_id=METHOD_ID,
        sample_code=sample_code,
        chromatogram_index=chromatogram_index,
        detector=detector,
        component=component,
        input_concentration=concentration,
        calculated_area=area,
        calculated_height=height,
        retention_time_reference=reference,
        retention_time_generated=generated,
        sigma=sigma,
        peak_imperfection_level=imperfection_level,
        internal_seed=seed,
        model_version=str(models["payload"].get("version", "unknown")),
    )


def _load_instrument_style() -> dict:
    style_path = DATA_DIR / "GC_CRYSTAL5000_STYLE.json"
    if style_path.exists():
        with style_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "detectors": {
            "ПИД-1": {"color": "#000000", "frame_color": "#000000"},
            "ПИД-2": {"color": "#2638FF", "frame_color": "#2638FF"},
        },
        "fonts": {
            "preferred_regular": ["arialn.ttf", "arial.ttf", "segoeui.ttf"],
            "preferred_bold": ["arialnb.ttf", "arialbd.ttf", "segoeuib.ttf"],
            "axis_size": 16,
            "tick_size": 14,
            "peak_label_size": 16,
        },
        "lines": {
            "signal_width": 1,
            "axis_width": 1,
            "major_tick_width": 1,
            "minor_tick_width": 1,
            "integration_width": 1,
        },
        "axes": {
            "x_min": 0.0,
            "x_max": 38.96,
            "x_major_step": 2.5,
            "x_minor_step": 0.25,
            "y_major_intervals": 5,
            "y_minor_subdivisions": 5,
            "draw_top_border": False,
            "draw_right_border": False,
        },
        "labels": {
            "x_shifts_px": [0, 3, -3, 6, -6],
            "vertical_levels_px": [2, 12, 22, 32],
        },
    }


def _hex_color(value: str) -> tuple[int, int, int]:
    raw = str(value).strip().lstrip("#")
    if len(raw) != 6:
        return (0, 0, 0)
    return tuple(int(raw[i:i + 2], 16) for i in (0, 2, 4))


def _font(size: int, *, bold: bool = False):
    style = _load_instrument_style()
    key = "preferred_bold" if bold else "preferred_regular"
    candidates = style.get("fonts", {}).get(key, [])
    for filename in candidates:
        path = Path("C:/Windows/Fonts") / filename
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def _signal_at(t: float, peak: PeakRecord) -> float:
    if peak.calculated_height <= 0 or peak.sigma <= 0:
        return 0.0
    rnd = random.Random(peak.internal_seed)
    level = peak.peak_imperfection_level
    asym = 0.0 if level == 0 else rnd.uniform(-0.07, 0.07) * min(level, 3)
    sigma_left = peak.sigma * (1.0 - asym)
    sigma_right = peak.sigma * (1.0 + asym)
    sigma = sigma_left if t < peak.retention_time_generated else sigma_right
    return peak.calculated_height * math.exp(-((t - peak.retention_time_generated) ** 2) / (2.0 * sigma ** 2))


def _reference_baseline(
    t: float,
    detector: str,
    rnd: random.Random,
    state: dict,
    *,
    y_max: float,
    x_max: float,
    style: dict,
) -> float:
    """Базовая линия по свойствам оригинальных хроматограмм МУК 4.1.3166.

    До области 33–34 мин линия низкая, слегка шумящая и медленно дрейфует.
    Затем начинается выраженный нелинейный подъем, достигающий значимой
    доли шкалы к концу анализа. Профили ПИД-1 и ПИД-2 независимы.
    """
    baseline_cfg = style.get("baseline", {})
    detector_key = "pid1" if detector == "ПИД-1" else "pid2"
    cfg = baseline_cfg.get(detector_key, {})

    prev = state.get("noise", 0.0)
    white = rnd.gauss(0.0, 1.0)
    prev = prev * 0.965 + white * 0.035
    state["noise"] = prev

    early_fraction = float(cfg.get("early_fraction", 0.005))
    slow_fraction = float(cfg.get("slow_wave_fraction", 0.002))
    noise_fraction = float(cfg.get("noise_fraction", 0.0007))

    phase = 0.35 if detector == "ПИД-1" else 0.85
    slow = (
        math.sin(t * 0.43 + phase) * 0.62
        + math.sin(t * 1.11 + phase * 0.7) * 0.38
    )
    early = early_fraction + slow_fraction * slow + noise_fraction * prev

    rise_start = float(baseline_cfg.get("rise_start_min", 33.2))
    rise_full = float(baseline_cfg.get("rise_full_min", x_max))
    rise_fraction = float(cfg.get("late_rise_fraction", 0.82))
    rise_power = float(cfg.get("late_rise_power", 1.5))

    if t <= rise_start:
        late = 0.0
    else:
        span = max(0.001, rise_full - rise_start)
        u = max(0.0, min(1.0, (t - rise_start) / span))
        # Smooth onset without a visible corner at the start of the rise.
        smooth_u = u * u * (3.0 - 2.0 * u)
        late = rise_fraction * (smooth_u ** rise_power)

    return max(0.0, y_max * (early + late))


def _draw_vertical_label(
    image: Image.Image,
    *,
    text: str,
    x: int,
    y_bottom: int,
    font,
    color=(0, 0, 0),
) -> None:
    """Рисует приборную вертикальную подпись, привязанную к пику."""
    dummy = Image.new("RGBA", (8, 8), (255, 255, 255, 0))
    d = ImageDraw.Draw(dummy)
    box = d.textbbox((0, 0), text, font=font)
    w = max(1, box[2] - box[0] + 4)
    h = max(1, box[3] - box[1] + 4)

    label = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    ld = ImageDraw.Draw(label)
    ld.text((2, 2), text, fill=color, font=font)

    rotated = label.rotate(90, expand=True)

    # GC_APEX_FIX_V6: x is the peak apex coordinate, therefore the rotated
    # label must be centered on x. The previous x + 2 treated the apex as
    # the left edge and visibly shifted every label to the right.
    px = int(round(x - rotated.width / 2))
    px = max(0, min(px, image.width - rotated.width))
    py = int(max(0, y_bottom - rotated.height))
    image.alpha_composite(rotated, (px, py))


def _nice_tick_max(value: float) -> float:
    """Округляет только шаг шкалы, не повышая видимость малых пиков."""
    if value <= 0:
        return 1.0
    exponent = math.floor(math.log10(value))
    fraction = value / (10 ** exponent)
    if fraction <= 1.2:
        nice = 1.2
    elif fraction <= 1.5:
        nice = 1.5
    elif fraction <= 2.0:
        nice = 2.0
    elif fraction <= 2.5:
        nice = 2.5
    elif fraction <= 3.0:
        nice = 3.0
    elif fraction <= 4.0:
        nice = 4.0
    elif fraction <= 5.0:
        nice = 5.0
    elif fraction <= 6.0:
        nice = 6.0
    elif fraction <= 8.0:
        nice = 8.0
    else:
        nice = 10.0
    return nice * (10 ** exponent)


def render_chromatogram(
    peaks: list[PeakRecord],
    output_path: Path,
    *,
    detector: str,
    width: int | None = None,
    height: int | None = None,
    x_min: float | None = None,
    x_max: float | None = None,
) -> Path:
    """Финальный приборный рендерер V9 для Хроматэк-Кристалл 5000."""
    style = _load_instrument_style()
    canvas = style.get("canvas", {})
    axes = style.get("axes", {})
    fonts = style.get("fonts", {})
    lines = style.get("lines", {})
    labels = style.get("labels", {})
    detector_style = style.get("detectors", {}).get(
        detector,
        {"color": "#000000", "frame_color": "#000000"},
    )

    width = int(width or canvas.get("width", 1600))
    height = int(height or canvas.get("height", 720))
    x_min = float(axes.get("x_min", 0.0) if x_min is None else x_min)
    x_max = float(axes.get("x_max", 38.96) if x_max is None else x_max)

    margins = canvas.get("margins", {})
    margin_l = int(margins.get("left", 64))
    margin_r = int(margins.get("right", 18))
    margin_t = int(margins.get("top", 10))
    margin_b = int(margins.get("bottom", 38))
    plot_w = width - margin_l - margin_r
    plot_h = height - margin_t - margin_b

    positive_peaks = [
        p for p in peaks
        if p.input_concentration > 0 and p.calculated_height > 0
    ]
    h_max = max((p.calculated_height for p in positive_peaks), default=1.0)
    y_max = _nice_tick_max(max(1.0, h_max * 1.07))

    background = _hex_color(canvas.get("background", "#FFFFFF"))
    detector_color = _hex_color(detector_style.get("color", "#000000"))
    frame_color = _hex_color(detector_style.get("frame_color", detector_style.get("color", "#000000")))

    image = Image.new("RGBA", (width, height), background + (255,))
    draw = ImageDraw.Draw(image)

    tick_font = _font(int(fonts.get("tick_size", 14)))
    label_font = _font(int(fonts.get("peak_label_size", 15)), bold=False)
    axis_font = _font(int(fonts.get("axis_size", 16)), bold=True)

    axis_width = int(lines.get("axis_width", 1))
    major_tick_width = int(lines.get("major_tick_width", 1))
    minor_tick_width = int(lines.get("minor_tick_width", 1))
    signal_width = int(lines.get("signal_width", 1))
    integration_width = int(lines.get("integration_width", 1))

    # Весь ПИД-2, включая оси, подписи, деления и выноски, рисуется одним синим.
    draw.line(
        (margin_l, margin_t, margin_l, margin_t + plot_h),
        fill=frame_color,
        width=axis_width,
    )
    draw.line(
        (margin_l, margin_t + plot_h, margin_l + plot_w, margin_t + plot_h),
        fill=frame_color,
        width=axis_width,
    )
    if axes.get("draw_top_border", False):
        draw.line(
            (margin_l, margin_t, margin_l + plot_w, margin_t),
            fill=frame_color,
            width=axis_width,
        )
    if axes.get("draw_right_border", False):
        draw.line(
            (margin_l + plot_w, margin_t, margin_l + plot_w, margin_t + plot_h),
            fill=frame_color,
            width=axis_width,
        )

    # Частые приборные засечки по X.
    major_step = float(axes.get("x_major_step", 2.5))
    minor_step = float(axes.get("x_minor_step", 0.25))
    tick = math.ceil(x_min / minor_step) * minor_step
    while tick <= x_max + 1e-9:
        x = margin_l + plot_w * (tick - x_min) / (x_max - x_min)
        major = abs((tick / major_step) - round(tick / major_step)) < 1e-7
        tick_len = 7 if major else 3
        draw.line(
            (x, margin_t + plot_h, x, margin_t + plot_h + tick_len),
            fill=frame_color,
            width=major_tick_width if major else minor_tick_width,
        )
        if major:
            txt = "0" if abs(tick) < 1e-9 else f"{tick:g}"
            box = draw.textbbox((0, 0), txt, font=tick_font)
            draw.text(
                (x - (box[2] - box[0]) / 2, margin_t + plot_h + 8),
                txt,
                fill=detector_color,
                font=tick_font,
            )
        tick += minor_step

    # Основные и мелкие деления Y тем же цветом детектора.
    y_major_intervals = int(axes.get("y_major_intervals", 5))
    y_minor_subdivisions = int(axes.get("y_minor_subdivisions", 5))
    total_minor = y_major_intervals * y_minor_subdivisions
    for i in range(total_minor + 1):
        y = margin_t + plot_h - plot_h * i / total_minor
        major = i % y_minor_subdivisions == 0
        tick_len = 7 if major else 3
        draw.line(
            (margin_l - tick_len, y, margin_l, y),
            fill=frame_color,
            width=major_tick_width if major else minor_tick_width,
        )
        if major:
            value = y_max * i / total_minor
            txt = f"{value:.0f}" if y_max >= 10 else f"{value:.1f}"
            box = draw.textbbox((0, 0), txt, font=tick_font)
            draw.text(
                (margin_l - 10 - (box[2] - box[0]), y - (box[3] - box[1]) / 2),
                txt,
                fill=detector_color,
                font=tick_font,
            )

    # Обозначения прибора в левом верхнем и правом нижнем углах.
    draw.text((5, 2), detector, fill=detector_color, font=axis_font)
    draw.text((5, 20), "мВ", fill=detector_color, font=axis_font)
    min_text = "мин"
    min_box = draw.textbbox((0, 0), min_text, font=axis_font)
    draw.text(
        (width - min_box[2] - 5, height - min_box[3] - 2),
        min_text,
        fill=detector_color,
        font=axis_font,
    )

    baseline_seed = stable_seed(
        METHOD_ID,
        detector,
        positive_peaks[0].sample_code if positive_peaks else "blank",
        positive_peaks[0].chromatogram_index if positive_peaks else 0,
        "reference-baseline-v4",
    )
    brnd = random.Random(baseline_seed)
    baseline_state = {}
    n = max(4200, width * 3)
    signal_points = []
    rendered_samples = []

    for i in range(n):
        t = x_min + (x_max - x_min) * i / (n - 1)
        baseline = _reference_baseline(
            t,
            detector,
            brnd,
            baseline_state,
            y_max=y_max,
            x_max=x_max,
            style=style,
        )
        signal = baseline + sum(_signal_at(t, peak) for peak in positive_peaks)
        x = margin_l + plot_w * (t - x_min) / (x_max - x_min)
        y = margin_t + plot_h - plot_h * min(signal, y_max) / y_max
        signal_points.append((x, y))
        rendered_samples.append((t, signal, x, y))

    draw.line(signal_points, fill=detector_color, width=signal_width)

    # GC_FINAL_RENDERER_V9 — зафиксированное приборное поведение по реальным распечаткам.
    #
    # Каждая подпись полностью независима от соседних:
    # - X строго равен retention_time_generated данного компонента;
    # - горизонтальный сдвиг отсутствует;
    # - нижний край повернутого текста находится непосредственно в вершине;
    # - наложения не предотвращаются и не корректируются.
    #
    # Это намеренно воспроизводит «грязную» приборную раскладку Хроматэк,
    # где близкие вертикальные подписи печатаются поверх друг друга.
    for peak in sorted(positive_peaks, key=lambda p: p.retention_time_generated):
        apex_time = peak.retention_time_generated
        sample_t, sample_signal, x_apex, y_apex = min(
            rendered_samples,
            key=lambda sample: abs(sample[0] - apex_time),
        )

        draw.line(
            (x_apex, y_apex, x_apex, margin_t + plot_h),
            fill=detector_color,
            width=integration_width,
        )

        label = (
            f"{sample_t:.3f} "
            f"{peak.component} "
            f"{peak.calculated_area:.3f}"
        )
        _draw_vertical_label(
            image,
            text=label,
            x=int(round(x_apex)),
            y_bottom=int(round(y_apex)),
            font=label_font,
            color=detector_color,
        )

    image.convert("RGB").save(output_path, format="PNG")
    return output_path


def build_chromatogram_times(start: datetime) -> list[datetime]:
    passport = load_passport()
    rule = passport["time_rules"]["within_sample_between_chromatograms"]
    seed = stable_seed(METHOD_ID, start.isoformat())
    rnd = random.Random(seed)
    gap = rnd.randint(int(rule["min"]), int(rule["max"]))
    return [start, start + timedelta(seconds=gap)]


def build_sample(
    sample_code: str,
    date_text: str,
    time_text: str,
    mode: str,
    values,
    output_dir: Path = OUTPUT_DIR,
    imperfection_level: int = 2,
) -> Path:
    models = load_models()
    start = parse_datetime(date_text, time_text)
    times = build_chromatogram_times(start)
    sample_dir = Path(output_dir) / safe_name(sample_code)
    sample_dir.mkdir(parents=True, exist_ok=True)

    if mode == "random":
        pairs = {}
        for component, base in values.items():
            pairs[component] = split_random_concentrations(
                float(base),
                stable_seed(METHOD_ID, sample_code, component, "random-pair"),
            )
    elif mode == "actual":
        pairs = {component: (float(pair[0]), float(pair[1])) for component, pair in values.items()}
    else:
        raise ValueError("Режим должен быть random или actual")

    package = {
        "method_id": METHOD_ID,
        "method_title": METHOD_TITLE,
        "sample_code": sample_code,
        "mode": mode,
        "chromatogram_count": CHROMATOGRAM_COUNT,
        "chromatogram_times": [dt.isoformat() for dt in times],
        "peaks": [],
        "images": [],
    }

    all_rows = []
    for chrom_idx in (1, 2):
        for detector in DETECTORS:
            peaks = []
            for component, pair in pairs.items():
                peak = calculate_peak(
                    models,
                    sample_code=sample_code,
                    chromatogram_index=chrom_idx,
                    detector=detector,
                    component=component,
                    concentration=pair[chrom_idx - 1],
                    imperfection_level=imperfection_level,
                )
                if peak is not None:
                    peaks.append(peak)
                    record = asdict(peak)
                    package["peaks"].append(record)
                    all_rows.append(record)

            image_name = f"chromatogram_{chrom_idx}_{detector.replace('-', '_')}.png"
            render_chromatogram(peaks, sample_dir / image_name, detector=detector)
            package["images"].append({
                "chromatogram_index": chrom_idx,
                "detector": detector,
                "file": image_name,
            })

    with (sample_dir / "generation.json").open("w", encoding="utf-8") as f:
        json.dump(package, f, ensure_ascii=False, indent=2)

    fields = list(PeakRecord.__dataclass_fields__.keys())
    with (sample_dir / "peaks.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter=";")
        writer.writeheader()
        writer.writerows(all_rows)

    return sample_dir


def default_random_values() -> dict[str, float]:
    return dict(COMPONENT_DEFAULTS)


def default_actual_values() -> dict[str, tuple[float, float]]:
    return {name: (value, value) for name, value in COMPONENT_DEFAULTS}


def excel_template_path(mode: str) -> Path:
    filename = "GC_MUK_4_1_3166_RANDOM.xlsx" if mode == "random" else "GC_MUK_4_1_3166_ACTUAL.xlsx"
    return TEMPLATE_DIR / filename


def _col_to_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    result = 0
    for ch in letters.upper():
        result = result * 26 + ord(ch) - 64
    return result - 1


def _shared_strings(z: zipfile.ZipFile):
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    result = []
    for item in root.findall(f"{{{SS_NS}}}si"):
        result.append("".join(x.text or "" for x in item.iter(f"{{{SS_NS}}}t")))
    return result


def read_xlsx_rows(path: Path) -> list[list[str]]:
    with zipfile.ZipFile(path, "r") as z:
        shared = _shared_strings(z)
        sheet_path = "xl/worksheets/sheet1.xml"
        if sheet_path not in z.namelist():
            sheet_path = next(n for n in z.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))
        root = ET.fromstring(z.read(sheet_path))
        output = []
        for row in root.iter(f"{{{SS_NS}}}row"):
            values = {}
            max_col = -1
            for cell in row.findall(f"{{{SS_NS}}}c"):
                col = _col_to_index(cell.attrib.get("r", "A1"))
                max_col = max(max_col, col)
                typ = cell.attrib.get("t")
                value = ""
                v = cell.find(f"{{{SS_NS}}}v")
                inline = cell.find(f"{{{SS_NS}}}is")
                if typ == "s" and v is not None:
                    value = shared[int(v.text or 0)]
                elif typ == "inlineStr" and inline is not None:
                    value = "".join(x.text or "" for x in inline.iter(f"{{{SS_NS}}}t"))
                elif v is not None:
                    value = v.text or ""
                values[col] = value
            if max_col >= 0:
                output.append([values.get(i, "") for i in range(max_col + 1)])
        return output


def generate_from_excel(
    excel_path: Path,
    mode: str,
    output_dir: Path = OUTPUT_DIR,
    imperfection_level: int = 2,
) -> tuple[list[Path], Path]:
    rows = read_xlsx_rows(excel_path)
    if len(rows) < 2:
        raise ValueError("В Excel нет данных")
    headers = [str(x).strip() for x in rows[0]]
    created = []
    batch_dir = Path(output_dir) / f"batch_{safe_name(excel_path.stem)}"
    batch_dir.mkdir(parents=True, exist_ok=True)

    previous_time = None
    passport = load_passport()
    between_rule = passport["time_rules"]["between_consecutive_samples_same_date"]

    for row_idx, row in enumerate(rows[1:], start=2):
        sample = str(row[0]).strip() if row else ""
        if not sample:
            continue
        date_text = str(row[1]).strip() or datetime.now().strftime("%d.%m.%Y")
        time_text = str(row[2]).strip() or "09:00:00"
        current = parse_datetime(date_text, time_text)
        if previous_time is not None and current.date() == previous_time.date() and not str(row[2]).strip():
            rnd = random.Random(stable_seed(METHOD_ID, excel_path.name, row_idx, "between-samples"))
            current = previous_time + timedelta(seconds=rnd.randint(int(between_rule["min"]), int(between_rule["max"])))
            date_text, time_text = current.strftime("%d.%m.%Y"), current.strftime("%H:%M:%S")

        if mode == "random":
            values = {}
            for col, component in enumerate(headers[3:], start=3):
                if component:
                    raw = row[col] if col < len(row) else ""
                    if str(raw).strip() != "":
                        values[component] = float(str(raw).replace(",", "."))
        else:
            values = {}
            for component, _ in COMPONENT_DEFAULTS:
                h1 = f"{component} — хроматограмма 1"
                h2 = f"{component} — хроматограмма 2"
                if h1 not in headers or h2 not in headers:
                    continue
                i1, i2 = headers.index(h1), headers.index(h2)
                raw1 = row[i1] if i1 < len(row) else ""
                raw2 = row[i2] if i2 < len(row) else ""
                if str(raw1).strip() != "" and str(raw2).strip() != "":
                    values[component] = (
                        float(str(raw1).replace(",", ".")),
                        float(str(raw2).replace(",", ".")),
                    )

        created.append(build_sample(
            sample,
            date_text,
            time_text,
            mode,
            values,
            batch_dir,
            imperfection_level,
        ))
        previous_time = current

    return created, batch_dir
