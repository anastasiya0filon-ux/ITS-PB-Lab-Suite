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

# CNRE загружается рядом с gc_generator.py.
# main.pyw импортирует этот файл как самостоятельный модуль, поэтому
# относительный импорт `.cnre_engine` здесь использовать нельзя.
import importlib.util as _cnre_importlib_util

_CNRE_PATH = Path(__file__).resolve().with_name("cnre_engine.py")
_CNRE_SPEC = _cnre_importlib_util.spec_from_file_location(
    "gc_cnre_engine_runtime",
    _CNRE_PATH,
)
if _CNRE_SPEC is None or _CNRE_SPEC.loader is None:
    raise ImportError(f"Не удалось создать спецификацию CNRE: {_CNRE_PATH}")

_CNRE_MODULE = _cnre_importlib_util.module_from_spec(_CNRE_SPEC)

# Python 3.14: dataclasses обращается к sys.modules по cls.__module__
# уже во время выполнения декоратора, поэтому модуль должен быть
# зарегистрирован ДО exec_module().
import sys as _cnre_sys
_cnre_sys.modules[_CNRE_SPEC.name] = _CNRE_MODULE

try:
    _CNRE_SPEC.loader.exec_module(_CNRE_MODULE)
except Exception:
    _cnre_sys.modules.pop(_CNRE_SPEC.name, None)
    raise

render_chromatogram_cnre = _CNRE_MODULE.render_chromatogram_cnre

ROOT = Path(__file__).resolve().parent

# CHROMATEK_RENDERER_1_0
import sys as _chromatek_sys
if str(ROOT) not in _chromatek_sys.path:
    _chromatek_sys.path.insert(0, str(ROOT))
from chromatek_renderer import render_chromatogram as _render_chromatek_image
from chromatek_renderer.scale_profiles import choose_reference_scale
DATA_DIR = ROOT / "data"
TEMPLATE_DIR = ROOT / "excel_templates"
OUTPUT_DIR = ROOT / "output"

METHOD_ID = "MUK_4_1_3166"
METHOD_TITLE = "МУК 4.1.3166"
GC_RENDERER_PATCH = "GC_REFERENCE_LAYOUT_V8"
DETECTORS = ("ПИД-1", "ПИД-2")
CHROMATOGRAM_COUNT = 2
FINAL_RENDERER_VERSION = "chromatek-renderer-2.3-chromatek-final-style"

COMPONENT_DEFAULTS = [
    ("Гексан", 0.00001),
    ("Гептан", 0.00001),
    ("Ацетальдегид", 0.0001),
    ("Метанол", 0.0001),
    ("Ацетон", 0.0001),
    ("Метилацетат", 0.0001),
    ("Этилацетат", 0.0001),
    ("Изопропанол", 0.0001),
    ("Акрилонитрил", 0.003),
    ("Н-пропанол", 0.0001),
    ("Толуол", 0.00001),
    ("Изобутанол", 0.0001),
    ("Бензол", 0.00001),
    ("Н-бутанол", 0.0001),
    ("Бутилацетат", 0.0001),
    ("Этилбензол", 0.00001),
    ("п-Ксилол", 0.00001),
    ("м-Ксилол", 0.00001),
    ("Изопропилбензол", 0.00001),
    ("о-Ксилол", 0.00001),
    ("Стирол", 0.00001),
    ("Метилстирол", 0.00001),
]

ALIASES = {
    "альфа-метилстирол": "Метилстирол",
    "метилстирол": "Метилстирол",
    "кумол": "Изопропилбензол",
    "кумол (изопропил бензол)": "Изопропилбензол",
    "кумол (изопропилбензол)": "Изопропилбензол",
    "изопропил бензол": "Изопропилбензол",
    "изопропилбензол": "Изопропилбензол",
    "спирт изобутиловый": "Изобутанол",
    "изобутанол": "Изобутанол",
    "спирт метиловый": "Метанол",
    "метанол": "Метанол",
    "спирт изопропиловый": "Изопропанол",
    "изопропанол": "Изопропанол",
    "спирт бутиловый": "Н-бутанол",
    "бутанол": "Н-бутанол",
    "н-бутанол": "Н-бутанол",
    "спирт пропиловый": "Н-пропанол",
    "пропанол": "Н-пропанол",
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


def format_sig5(value: float) -> str:
    """Ровно пять значащих цифр, включая конечные нули."""
    number = float(value)
    if number == 0:
        return "0.0000"
    exponent = math.floor(math.log10(abs(number)))
    if exponent < -4 or exponent >= 5:
        return f"{number:.4e}"
    return f"{number:.{max(0, 4-exponent)}f}"


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
    rnd = random.Random(peak.internal_seed ^ 0x51A7)
    level = max(0, min(int(peak.peak_imperfection_level), 3))
    time_broadening = 1.0 + 0.0105 * max(0.0, peak.retention_time_generated - 2.0)
    base_sigma = max(peak.sigma * time_broadening, 0.0065)
    asym = rnd.uniform(-0.035, 0.085) * (0.45 + 0.28 * level)
    sigma_left = base_sigma * max(0.72, 1.0 - asym)
    sigma_right = base_sigma * max(0.78, 1.0 + asym)
    dt = t - peak.retention_time_generated
    sigma = sigma_left if dt < 0.0 else sigma_right
    value = peak.calculated_height * math.exp(-(dt * dt) / (2.0 * sigma * sigma))
    tail_share = rnd.uniform(0.0, 0.026) * (level / 2.0)
    if dt > 0.0 and tail_share > 0.0:
        tail_tau = max(base_sigma * rnd.uniform(2.2, 4.2), 0.018)
        value += peak.calculated_height * tail_share * math.exp(-dt / tail_tau)
    return value

def _reference_baseline(t: float, detector: str, rnd: random.Random, state: dict) -> float:
    prev_fast = state.get("fast", 0.0)
    prev_mid = state.get("mid", 0.0)
    prev_fast = 0.72 * prev_fast + 0.28 * rnd.gauss(0.0, 1.0)
    prev_mid = 0.975 * prev_mid + 0.025 * rnd.gauss(0.0, 1.0)
    state["fast"] = prev_fast
    state["mid"] = prev_mid
    if detector == "ПИД-1":
        base, drift, start, late_scale = 0.018, 0.00038 * t, 33.35, 0.0078
        wave = 0.0048 * math.sin(0.43*t+0.35) + 0.0025 * math.sin(1.31*t+1.2) + 0.0014 * math.sin(3.70*t)
        noise = 0.0037 * prev_fast + 0.0030 * prev_mid
        phase = 0.4
    else:
        base, drift, start, late_scale = 0.021, 0.00044 * t, 33.75, 0.0067
        wave = 0.0042 * math.sin(0.37*t+0.95) + 0.0029 * math.sin(1.08*t+0.15) + 0.0016 * math.sin(3.25*t+0.7)
        noise = 0.0040 * prev_fast + 0.0033 * prev_mid
        phase = 1.1
    u = max(0.0, t - start)
    late = late_scale * (u ** 1.48)
    late_ripple = (0.0012 + 0.00035*u) * math.sin(5.3*t + phase)
    return max(0.0, base + drift + wave + noise + late + late_ripple)

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



def _instrument_font(size: int, *, bold: bool = False):
    """Фиксированный Windows-шрифт для нативной приборной растризации."""
    names = (["arialbd.ttf", "tahomabd.ttf"] if bold else
             ["arial.ttf", "tahoma.ttf", "micross.ttf", "segoeui.ttf"])
    for name in names:
        p = Path("C:/Windows/Fonts") / name
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size=size, layout_engine=ImageFont.Layout.BASIC)
            except Exception:
                try:
                    return ImageFont.truetype(str(p), size=size)
                except Exception:
                    pass
    return _font(size, bold=bold)


def _vertical_text_native(image: Image.Image, text: str, x: float, baseline_y: int,
                          font, color, *, bottom_gap: int = 2) -> None:
    """Вертикальный текст как в PNG Хроматэк: снизу вверх, без подложки."""
    probe = Image.new("RGBA", (4, 4), (255,255,255,0))
    d = ImageDraw.Draw(probe)
    box = d.textbbox((0,0), text, font=font)
    w = max(1, box[2]-box[0]+2); h = max(1, box[3]-box[1]+1)
    layer = Image.new("RGBA", (w,h), (255,255,255,0))
    ImageDraw.Draw(layer).text((1,-box[1]), text, fill=color, font=font, spacing=0)
    rot = layer.rotate(90, expand=True, resample=Image.Resampling.NEAREST)
    px = int(round(x - rot.width/2))
    px = max(0, min(px, image.width-rot.width))
    py = max(0, baseline_y-bottom_gap-rot.height)
    image.alpha_composite(rot, (px,py))


def _native_peak_value(t: float, peak: PeakRecord) -> float:
    """Узкий, но не игольчатый профиль в нативном разрешении 718 px."""
    if peak.calculated_height <= 0 or peak.sigma <= 0:
        return 0.0
    rnd = random.Random(peak.internal_seed ^ 0x13A5)
    tr = peak.retention_time_generated
    # Минимум соответствует примерно 1.4 пикселя по X в приборном PNG.
    pixel_time = 38.96 / 678.0
    sigma0 = max(peak.sigma, pixel_time * (0.42 + 0.006*tr))
    skew = rnd.uniform(-0.04, 0.12)
    sl = sigma0 * (1.0-skew*0.45)
    sr = sigma0 * (1.0+skew)
    dt = t-tr
    s = sl if dt < 0 else sr
    v = peak.calculated_height * math.exp(-0.5*(dt/s)**2)
    if dt > 0 and rnd.random() < 0.62:
        v += peak.calculated_height*rnd.uniform(0.004,0.018)*math.exp(-dt/max(0.025, sigma0*3.0))
    return v


def _native_y_scale(heights: list[float], detector: str) -> tuple[float,float]:
    m = max(heights or [1.0])
    raw = m*1.12
    exp = 10**math.floor(math.log10(max(raw,1e-9)))
    frac = raw/exp
    for q in (1,1.2,1.5,2,2.5,3,4,5,6,8,10):
        if frac <= q:
            ymax=q*exp; break
    # 5 основных интервалов, как на приборных PNG.
    return ymax, ymax/5.0


def render_chromatek_native(peaks: list[PeakRecord], output_path: Path, *, detector: str,
                             x_min: float=0.0, x_max: float=38.96) -> Path:
    """Нативный renderer 718×321 для ПИД-1 и ПИД-2 по 8 приборным эталонам."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    W,H = 718,321
    L,R,T,B = 22,1,1,24
    X0,X1,Y0,YB = L,W-R,T,H-B
    PW,PH = X1-X0,YB-Y0
    color = (0,0,255) if detector == "ПИД-2" else (0,0,0)
    soft = color
    image = Image.new("RGBA", (W,H), (255,255,255,255))
    draw = ImageDraw.Draw(image)
    font = _instrument_font(10)
    small = _instrument_font(9)

    positive=[p for p in peaks if p.input_concentration>0 and p.calculated_height>0]
    ymax, ystep = _native_y_scale([p.calculated_height for p in positive], detector)

    # Приборная геометрия: тонкая верхняя линия, левая и нижняя оси.
    draw.line((0,0,W-1,0), fill=(150,150,150), width=1)
    draw.line((X0,Y0,X0,YB), fill=color, width=1)
    draw.line((X0,YB,X1,YB), fill=color, width=1)

    def tx(t): return X0 + PW*(t-x_min)/(x_max-x_min)
    def ty(v): return YB - PH*max(0.0,min(v,ymax))/ymax

    # X: основные деления каждые 2.5 мин, мелкие каждые 0.5 мин.
    k=0
    v=0.0
    while v <= x_max+1e-9:
        x=tx(v)
        major = abs((v/2.5)-round(v/2.5))<1e-8
        draw.line((x,YB,x,YB+(5 if major else 2)), fill=color, width=1)
        if major and v>0 and v < x_max-0.2:
            s=(f"{v:.1f}" if abs(v-round(v))>1e-8 else f"{int(v)}")
            bb=draw.textbbox((0,0),s,font=small)
            draw.text((x-(bb[2]-bb[0])/2,YB+5),s,fill=color,font=small)
        v += 0.5

    # Y: 5 главных интервалов + 4 малых между ними.
    for i in range(6):
        val=i*ystep; y=ty(val)
        draw.line((X0-5,y,X0,y),fill=color,width=1)
        if i>0:
            s=f"{val:g}"
            bb=draw.textbbox((0,0),s,font=small)
            draw.text((X0-7-(bb[2]-bb[0]),y-(bb[3]-bb[1])/2),s,fill=color,font=small)
        if i<5:
            for j in range(1,5):
                yy=ty(val+j*ystep/5)
                draw.line((X0-2,yy,X0,yy),fill=color,width=1)
    # Единицы как в приборном PNG.
    _vertical_text_native(image, "мВ", 7, 22, small, color, bottom_gap=0)
    draw.text((W-27,H-15),"мин",fill=color,font=small)

    sample=positive[0].sample_code if positive else "blank"
    idx=positive[0].chromatogram_index if positive else 0
    rnd=random.Random(stable_seed(METHOD_ID,"native-v13",detector,sample,idx))

    # Низкая приборная база + поздний подъём. ПИДы независимы.
    n=5200
    state_fast=state_slow=0.0
    events=[]
    bands = ([(0.7,22.0,18),(22.0,34.0,38),(34.0,38.9,42)] if detector=="ПИД-1"
             else [(0.7,22.0,20),(22.0,34.0,48),(34.0,38.9,48)])
    for lo,hi,count in bands:
        for _ in range(count+rnd.randint(-3,3)):
            c=rnd.uniform(lo,hi)
            # Большинство фоновых событий — почти линии интегратора, не пики.
            amp=ymax*rnd.uniform(0.0010,0.0060 if c<34 else 0.011)
            sig=rnd.uniform(0.010,0.036)*(1+c/90)
            events.append((c,amp,sig,rnd.random()))

    samples=[]; pts=[]
    for i in range(n):
        t=x_min+(x_max-x_min)*i/(n-1)
        state_fast=.63*state_fast+.37*rnd.gauss(0,1)
        state_slow=.992*state_slow+.008*rnd.gauss(0,1)
        u=max(0.0,t-(33.45 if detector=="ПИД-1" else 33.75))
        base_frac=(0.0028 + 0.000045*t + 0.00048*math.sin(.71*t+(.4 if detector=="ПИД-1" else 1.2))
                   +0.00030*state_fast+0.00045*state_slow)
        if u>0:
            # Неровный рост без гладкого плато.
            base_frac += (0.00135*u**1.48 + 0.00055*u*math.sin(1.17*t) + 0.00032*u*math.sin(4.6*t+.7))
        baseline=max(0.0,ymax*base_frac)
        bg=0.0
        for c,a,s,_ in events:
            dt=t-c
            if abs(dt)<5*s:
                bg += a*math.exp(-0.5*(dt/s)**2)
        sigv=baseline+bg+sum(_native_peak_value(t,p) for p in positive)
        x=tx(t); y=ty(sigv)
        pts.append((x,y)); samples.append((t,sigv,x,y))
    draw.line(pts,fill=color,width=1)

    # Аналитические подписи: исходят от базовой линии; без искусственного разнесения.
    ordered=sorted(positive,key=lambda p:p.retention_time_generated)
    for j,p in enumerate(ordered):
        tr=p.retention_time_generated
        left=tr-max(0.06,p.sigma*4); right=tr+max(0.07,p.sigma*5)
        if j: left=max(left,(ordered[j-1].retention_time_generated+tr)/2)
        if j+1<len(ordered): right=min(right,(tr+ordered[j+1].retention_time_generated)/2)
        loc=[s for s in samples if left<=s[0]<=right]
        apex=max(loc,key=lambda z:z[1]) if loc else min(samples,key=lambda z:abs(z[0]-tr))
        at, av, ax, ay=apex
        name=p.component
        if detector=="ПИД-2" and 20.2<=at<=21.3 and name in {"п-Ксилол","м-Ксилол"}:
            name="м-Ксилол, п-Ксилол"
        if detector=="ПИД-2" and 21.6<=at<=22.8 and name in {"Стирол","о-Ксилол"}:
            name="Стирол, о-Ксилол"
        label=f"{at:.3f} {name} {p.calculated_area:.3f}"
        _vertical_text_native(image,label,ax,YB,font,color,bottom_gap=2)
        p.retention_time_generated=round(float(at),6)

    # Фоновые подписи: смесь коротких чисел и время+площадь, кластерами.
    for c,a,s,q in events:
        if q<0.42 and c<22: continue
        if q<0.18 and 22<=c<34: continue
        loc=[z for z in samples if c-2.5*s<=z[0]<=c+2.5*s]
        if not loc: continue
        at,av,ax,ay=max(loc,key=lambda z:z[1])
        if q<0.62:
            label=f"{a/ymax*100:.3f}"
        else:
            label=f"{at:.3f} {a*8.7:.3f}"
        # Поздний кластер имеет небольшой горизонтальный разброс.
        ax += rnd.uniform(-1.2,1.2) if c>=22 else 0
        _vertical_text_native(image,label,ax,YB,small,color,bottom_gap=2)

    image.convert("RGB").save(output_path,"PNG")
    return output_path


def render_chromatogram(
    peaks: list[PeakRecord],
    output_path: Path,
    *,
    detector: str,
    width: int = 1600,
    height: int = 720,
    x_min: float = 0.0,
    x_max: float = 38.96,
    y_max: float | None = None,
    y_tick_step: float | None = None,
) -> Path:
    # width/height оставлены для совместимости со старым API.
    return _render_chromatek_image(
        peaks,
        output_path,
        detector=detector,
        x_min=x_min,
        x_max=x_max,
        y_max=y_max,
        y_tick_step=y_tick_step,
    )

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
    canonical_values = {}
    for raw_name, raw_value in values.items():
        canonical_name = normalize_component(raw_name)
        if canonical_name not in canonical_values:
            canonical_values[canonical_name] = raw_value
    values = canonical_values
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
        "scales": [],
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
            component_values = {name: float(pair[chrom_idx - 1]) for name, pair in pairs.items()}
            scale = choose_reference_scale(component_values, detector)
            render_chromatogram(
                peaks,
                sample_dir / image_name,
                detector=detector,
                x_max=float(scale["x_max"]),
                y_max=float(scale["y_max"]),
                y_tick_step=float(scale["y_tick_step"]),
            )
            package["images"].append({
                "chromatogram_index": chrom_idx,
                "detector": detector,
                "file": image_name,
            })
            package["scales"].append({"chromatogram_index": chrom_idx, "detector": detector, **scale})

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
