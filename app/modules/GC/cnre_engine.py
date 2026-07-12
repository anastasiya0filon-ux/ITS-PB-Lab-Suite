# -*- coding: utf-8 -*-
"""Chromatek Native Rendering Engine (CNRE) 0.1.

Архитектура:
- LayoutEngine: нативная геометрия 718x321, оси, деления, шкалы;
- RasterTextEngine: Windows GDI для прибороподобной растеризации текста;
- SignalEngine: база и аналитические пики;
- IntegrationEngine: аналитические и фоновые подписи/метки;
- Composer: сборка PNG.

Эта версия заменяет монолитный renderer, но сохраняет интерфейс
render_chromatogram(peaks, output_path, detector=...).
"""
from __future__ import annotations

import ctypes
import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont


W, H = 718, 321
X0, X1 = 22, 717
Y_TOP, Y_BASE = 1, 297
PLOT_W = X1 - X0
PLOT_H = Y_BASE - Y_TOP
X_MIN, X_MAX = 0.0, 38.96

PID1 = (0, 0, 0)
PID2 = (0, 0, 255)
TOP_RULE = (150, 150, 150)


@dataclass(frozen=True)
class DetectorStyle:
    color: tuple[int, int, int]
    y_intervals: int = 5
    x_major: float = 2.5
    x_minor: float = 0.5
    font_face: str = "Arial"
    tick_px: int = 10
    label_px: int = 10


STYLES = {
    "ПИД-1": DetectorStyle(PID1),
    "ПИД-2": DetectorStyle(PID2),
}


def _tx(t: float) -> float:
    return X0 + PLOT_W * (t - X_MIN) / (X_MAX - X_MIN)


def _ty(v: float, y_max: float) -> float:
    return Y_BASE - PLOT_H * max(0.0, min(v, y_max)) / y_max


def _nice_ymax(v: float) -> float:
    v = max(v, 1e-9) * 1.10
    e = 10 ** math.floor(math.log10(v))
    f = v / e
    for q in (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if f <= q:
            return q * e
    return 10 * e


class RasterTextEngine:
    """GDI-растризация на Windows; Pillow fallback вне Windows."""

    def __init__(self, face: str = "Arial") -> None:
        self.face = face

    def _fallback_font(self, px: int):
        candidates = [
            Path("C:/Windows/Fonts/arial.ttf"),
            Path("C:/Windows/Fonts/tahoma.ttf"),
            Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ]
        for p in candidates:
            if p.exists():
                try:
                    return ImageFont.truetype(str(p), px, layout_engine=ImageFont.Layout.BASIC)
                except Exception:
                    try:
                        return ImageFont.truetype(str(p), px)
                    except Exception:
                        pass
        return ImageFont.load_default()

    def text_rgba(self, text: str, px: int, color: tuple[int, int, int], *, vertical: bool = False) -> Image.Image:
        if sys.platform == "win32":
            try:
                img = self._gdi_text(text, px, color)
                if vertical:
                    return img.rotate(90, expand=True, resample=Image.Resampling.NEAREST)
                return img
            except Exception:
                pass
        font = self._fallback_font(px)
        probe = Image.new("L", (4, 4), 0)
        d = ImageDraw.Draw(probe)
        box = d.textbbox((0, 0), text, font=font)
        w = max(1, box[2] - box[0] + 2)
        h = max(1, box[3] - box[1] + 2)
        img = Image.new("RGBA", (w, h), (255, 255, 255, 0))
        ImageDraw.Draw(img).text((1 - box[0], 1 - box[1]), text, font=font, fill=(*color, 255), stroke_width=0)
        return img.rotate(90, expand=True, resample=Image.Resampling.NEAREST) if vertical else img

    def _gdi_text(self, text: str, px: int, color: tuple[int, int, int]) -> Image.Image:
        # 32-bit top-down DIB. NONANTIALIASED_QUALITY reproduces old GDI glyph edges.
        gdi32 = ctypes.windll.gdi32
        user32 = ctypes.windll.user32
        hdc = user32.GetDC(0)
        memdc = gdi32.CreateCompatibleDC(hdc)
        width = max(32, len(text) * (px + 2) + 16)
        height = max(20, px * 3)

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                        ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                        ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                        ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
                        ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
                        ("biClrImportant", ctypes.c_uint32)]
        class BITMAPINFO(ctypes.Structure):
            _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", ctypes.c_uint32 * 3)]

        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = width
        bmi.bmiHeader.biHeight = -height
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0
        bits = ctypes.c_void_p()
        hbmp = gdi32.CreateDIBSection(memdc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
        oldbmp = gdi32.SelectObject(memdc, hbmp)
        ctypes.memset(bits, 0xFF, width * height * 4)

        FW_NORMAL = 400
        NONANTIALIASED_QUALITY = 3
        font = gdi32.CreateFontW(-px, 0, 0, 0, FW_NORMAL, 0, 0, 0, 204,
                                 0, 0, NONANTIALIASED_QUALITY, 0x20, self.face)
        oldfont = gdi32.SelectObject(memdc, font)
        gdi32.SetBkMode(memdc, 1)
        r, g, b = color
        gdi32.SetTextColor(memdc, r | (g << 8) | (b << 16))
        gdi32.TextOutW(memdc, 1, 1, text, len(text))

        raw = ctypes.string_at(bits, width * height * 4)
        im = Image.frombuffer("RGBA", (width, height), raw, "raw", "BGRA", 0, 1).copy()
        # White -> transparent, preserve dark/blue glyph pixels.
        pix = im.load()
        xs, ys = [], []
        for y in range(height):
            for x in range(width):
                rr, gg, bb, aa = pix[x, y]
                if (rr, gg, bb) != (255, 255, 255):
                    xs.append(x); ys.append(y)
                    pix[x, y] = (rr, gg, bb, 255)
                else:
                    pix[x, y] = (255, 255, 255, 0)
        if xs:
            im = im.crop((min(xs), min(ys), max(xs) + 1, max(ys) + 1))

        gdi32.SelectObject(memdc, oldfont)
        gdi32.DeleteObject(font)
        gdi32.SelectObject(memdc, oldbmp)
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(memdc)
        user32.ReleaseDC(0, hdc)
        return im

    def paste(self, canvas: Image.Image, text: str, x: float, y: float, px: int,
              color: tuple[int, int, int], *, vertical: bool = False,
              anchor: str = "lt") -> None:
        glyph = self.text_rgba(text, px, color, vertical=vertical)
        ix, iy = int(round(x)), int(round(y))
        if anchor == "bc":
            ix -= glyph.width // 2; iy -= glyph.height
        elif anchor == "tc":
            ix -= glyph.width // 2
        elif anchor == "rc":
            ix -= glyph.width; iy -= glyph.height // 2
        elif anchor == "lc":
            iy -= glyph.height // 2
        canvas.alpha_composite(glyph, (max(0, ix), max(0, iy)))


class LayoutEngine:
    def __init__(self, detector: str, y_max: float, text: RasterTextEngine):
        self.detector = detector
        self.style = STYLES[detector]
        self.y_max = y_max
        self.text = text

    def draw(self, image: Image.Image) -> None:
        d = ImageDraw.Draw(image)
        c = self.style.color
        d.line((0, 0, W - 1, 0), fill=TOP_RULE, width=1)
        d.line((X0, Y_TOP, X0, Y_BASE), fill=c, width=1)
        d.line((X0, Y_BASE, X1, Y_BASE), fill=c, width=1)

        # X axis exactly in native pixels. Labels start at 2.5, as in originals.
        v = 0.0
        while v <= X_MAX + 1e-9:
            x = _tx(v)
            major = abs(v / self.style.x_major - round(v / self.style.x_major)) < 1e-8
            d.line((x, Y_BASE, x, Y_BASE + (5 if major else 2)), fill=c, width=1)
            if major and 0.0 < v < 38.8:
                s = f"{v:g}"
                self.text.paste(image, s, x, Y_BASE + 5, self.style.tick_px, c, anchor="tc")
            v += self.style.x_minor

        step = self.y_max / self.style.y_intervals
        for i in range(self.style.y_intervals + 1):
            val = i * step
            y = _ty(val, self.y_max)
            d.line((X0 - 5, y, X0, y), fill=c, width=1)
            if i > 0:
                self.text.paste(image, f"{val:g}", X0 - 7, y, self.style.tick_px, c, anchor="rc")
            if i < self.style.y_intervals:
                for j in range(1, 5):
                    yy = _ty(val + j * step / 5, self.y_max)
                    d.line((X0 - 2, yy, X0, yy), fill=c, width=1)
        self.text.paste(image, "мВ", 5, 1, self.style.tick_px, c, vertical=True)
        self.text.paste(image, "мин", W - 2, H - 3, self.style.tick_px, c, anchor="rc")


class SignalEngine:
    def __init__(self, detector: str, y_max: float, seed: int):
        self.detector = detector
        self.y_max = y_max
        self.rnd = random.Random(seed)

    def peak(self, t: float, p) -> float:
        if p.calculated_height <= 0:
            return 0.0
        pix_dt = (X_MAX - X_MIN) / PLOT_W
        tr = p.retention_time_generated
        # Instrument footprint: 1.2–2.7 pixels sigma depending on retention.
        sigma = max(float(p.sigma), pix_dt * (0.55 + 0.018 * tr))
        rr = random.Random(p.internal_seed ^ 0xC0A7)
        asym = rr.uniform(-0.06, 0.14)
        s = sigma * (1 + asym if t >= tr else 1 - 0.45 * asym)
        dt = t - tr
        y = p.calculated_height * math.exp(-0.5 * (dt / s) ** 2)
        if dt > 0:
            y += p.calculated_height * rr.uniform(0.004, 0.020) * math.exp(-dt / max(0.028, sigma * 3.2))
        return y

    def background_events(self):
        # Non-uniform clusters measured from the eight originals.
        if self.detector == "ПИД-1":
            bands = [(0.8, 8.0, 10), (8.0, 16.5, 12), (16.5, 22.0, 5),
                     (22.0, 25.5, 7), (25.5, 31.0, 10), (31.0, 34.0, 5), (34.0, 38.8, 24)]
        else:
            bands = [(0.8, 8.0, 12), (8.0, 16.5, 13), (16.5, 22.0, 7),
                     (22.0, 25.2, 13), (25.2, 32.8, 25), (32.8, 34.6, 5), (34.6, 38.8, 30)]
        events = []
        for lo, hi, n in bands:
            for _ in range(max(1, n + self.rnd.randint(-2, 2))):
                c = self.rnd.uniform(lo, hi)
                a = self.y_max * self.rnd.uniform(0.00045, 0.0045 if c < 34 else 0.009)
                s = self.rnd.uniform(0.008, 0.030) * (1 + c / 110)
                events.append((c, a, s, self.rnd.random()))
        return events

    def samples(self, peaks: list, events: list):
        n = 6500
        fast = slow = 0.0
        out = []
        for i in range(n):
            t = X_MIN + (X_MAX - X_MIN) * i / (n - 1)
            fast = 0.66 * fast + 0.34 * self.rnd.gauss(0, 1)
            slow = 0.994 * slow + 0.006 * self.rnd.gauss(0, 1)
            phase = 0.2 if self.detector == "ПИД-1" else 0.9
            start = 33.45 if self.detector == "ПИД-1" else 33.65
            u = max(0.0, t - start)
            frac = 0.0020 + 0.000032 * t + 0.00030 * math.sin(0.62 * t + phase)
            frac += 0.00022 * fast + 0.00036 * slow
            if u:
                frac += 0.00105 * u ** 1.44 + 0.00042 * u * math.sin(1.10 * t + phase)
                frac += 0.00023 * u * math.sin(4.75 * t + 0.6)
            y = max(0.0, self.y_max * frac)
            for c, a, s, q in events:
                dt = t - c
                if abs(dt) < 4.5 * s:
                    y += a * math.exp(-0.5 * (dt / s) ** 2)
            for p in peaks:
                y += self.peak(t, p)
            out.append((t, y, _tx(t), _ty(y, self.y_max)))
        return out


class IntegrationEngine:
    def __init__(self, detector: str, text: RasterTextEngine, seed: int):
        self.detector = detector
        self.style = STYLES[detector]
        self.text = text
        self.rnd = random.Random(seed ^ 0x5A11)

    def _label_name(self, p, at: float) -> str:
        n = p.component
        if self.detector == "ПИД-2" and 20.1 <= at <= 21.4 and n in {"п-Ксилол", "м-Ксилол"}:
            return "м-Ксилол, п-Ксилол"
        if self.detector == "ПИД-2" and 21.5 <= at <= 22.9 and n in {"Стирол", "о-Ксилол"}:
            return "Стирол, о-Ксилол"
        return n

    def draw(self, image: Image.Image, peaks: list, events: list, samples: list) -> None:
        c = self.style.color
        ordered = sorted(peaks, key=lambda p: p.retention_time_generated)
        for i, p in enumerate(ordered):
            tr = p.retention_time_generated
            left = tr - max(0.050, p.sigma * 4.0)
            right = tr + max(0.060, p.sigma * 4.8)
            if i:
                left = max(left, (ordered[i-1].retention_time_generated + tr) / 2)
            if i + 1 < len(ordered):
                right = min(right, (tr + ordered[i+1].retention_time_generated) / 2)
            local = [s for s in samples if left <= s[0] <= right]
            apex = max(local, key=lambda z: z[1]) if local else min(samples, key=lambda z: abs(z[0] - tr))
            at, av, ax, ay = apex
            p.retention_time_generated = round(float(at), 6)
            label = f"{at:.3f} {self._label_name(p, at)} {p.calculated_area:.3f}"
            self.text.paste(image, label, ax, Y_BASE - 2, self.style.label_px, c, vertical=True, anchor="bc")

        # Not every event receives a label; labels form clusters and gaps.
        for center, amp, sigma, q in events:
            prob = 0.25 if center < 22 else (0.60 if center < 34 else 0.82)
            if q > prob:
                continue
            local = [s for s in samples if center - 2.5*sigma <= s[0] <= center + 2.5*sigma]
            if not local:
                continue
            at, av, ax, ay = max(local, key=lambda z: z[1])
            label = f"{at:.3f} {amp * 8.7:.3f}" if q < 0.52 else f"{amp / max(1.0, av) * 100:.3f}"
            self.text.paste(image, label, ax + self.rnd.uniform(-0.8, 0.8), Y_BASE - 2,
                            9, c, vertical=True, anchor="bc")


class Composer:
    def render(self, peaks: list, output_path: Path, detector: str, stable_seed_fn) -> Path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        style = STYLES[detector]
        positive = [p for p in peaks if p.input_concentration > 0 and p.calculated_height > 0]
        y_max = _nice_ymax(max((p.calculated_height for p in positive), default=1.0))
        sample = positive[0].sample_code if positive else "blank"
        idx = positive[0].chromatogram_index if positive else 0
        seed = stable_seed_fn("CNRE-0.1", detector, sample, idx)

        image = Image.new("RGBA", (W, H), (255, 255, 255, 255))
        text = RasterTextEngine(style.font_face)
        LayoutEngine(detector, y_max, text).draw(image)
        signal = SignalEngine(detector, y_max, seed)
        events = signal.background_events()
        samples = signal.samples(positive, events)
        ImageDraw.Draw(image).line([(x, y) for _, _, x, y in samples], fill=style.color, width=1)
        IntegrationEngine(detector, text, seed).draw(image, positive, events, samples)
        image.convert("RGB").save(output_path, "PNG")
        return output_path


def render_chromatogram_cnre(peaks: list, output_path: Path, *, detector: str, stable_seed_fn) -> Path:
    return Composer().render(peaks, output_path, detector, stable_seed_fn)
