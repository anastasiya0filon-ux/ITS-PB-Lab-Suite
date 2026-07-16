# GC_AXIS_LABEL_WEIGHT_SOFTNESS_FIX_24
# GC_AXIS_LABEL_WEIGHT_INTENSITY_FIX_23A
# GC_AXIS_LABEL_FINE_TUNE_FIX_22
# GC_AXIS_LABEL_POSITION_AND_SIZE_FIX_21A
# GC_AXIS_WIDTH_ISOLATION_FIX_20A
# GC_AXIS_GDI_WIDTH_AND_OFFSET_FIX_20
# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
import os
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont


@dataclass(frozen=True)
class FontSpec:
    size: int
    bold: bool = False
    face: str = "Arial Narrow"
    render_scale: int = 4
    width_scale: float = 1.0
    size_scale: float = 1.0
    weight_scale: float = 1.0
    intensity: float = 1.0
    softness: float = 0.0


def load_font(
    size: int, *, bold: bool = False,
    face: str = "Arial Narrow", render_scale: int = 4,
    width_scale: float = 1.0,
    size_scale: float = 1.0,
    weight_scale: float = 1.0,
    intensity: float = 1.0,
    softness: float = 0.0,
):
    """Описание нативного GDI-шрифта для конкретной роли текста."""
    return FontSpec(
        size=max(1, int(round(size))),
        bold=bool(bold),
        face=str(face),
        render_scale=max(1, int(render_scale)),
        width_scale=max(0.5, float(width_scale)),
        size_scale=max(0.5, float(size_scale)),
        weight_scale=max(1.0, float(weight_scale)),
        intensity=max(0.0, min(1.0, float(intensity))),
        softness=max(0.0, min(1.0, float(softness))),
    )


def _fallback_mask(text: str, font: FontSpec, *, angle_tenths: int = 0) -> Image.Image:
    """Резервный рендер для не-Windows окружения и диагностики."""
    candidates = [
        r"C:\Windows\Fonts\arialn.ttf",
        r"C:\Windows\Fonts\tahoma.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf",
    ]
    pil_font = None
    for path in candidates:
        try:
            pil_font = ImageFont.truetype(path, font.size * font.render_scale)
            break
        except Exception:
            pass
    pil_font = pil_font or ImageFont.load_default()

    probe = Image.new("L", (4, 4), 0)
    box = ImageDraw.Draw(probe).textbbox((0, 0), text, font=pil_font, stroke_width=0)
    mask = Image.new(
        "L",
        (max(1, box[2] - box[0] + 4), max(1, box[3] - box[1] + 4)),
        0,
    )
    ImageDraw.Draw(mask).text(
        (2 - box[0], 2 - box[1]),
        text,
        font=pil_font,
        fill=255,
        stroke_width=0,
    )
    if angle_tenths:
        # Только аварийный путь вне Windows. Рабочий Windows-рендер не использует PIL rotate.
        mask = mask.rotate(angle_tenths / 10.0, expand=True, resample=Image.Resampling.BICUBIC)
    return mask


def _gdi_mask(text: str, font: FontSpec, *, angle_tenths: int = 0) -> Image.Image:
    """Создаёт маску текста напрямую средствами Windows GDI.

    angle_tenths задаётся в десятых долях градуса. Для вертикальной подписи
    используется 900, поэтому поворачивается сам шрифт, а не готовый растр.
    """
    if os.name != "nt":
        return _fallback_mask(text, font, angle_tenths=angle_tenths)

    import ctypes
    from ctypes import wintypes

    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

    FW_NORMAL = 400

    FW_MEDIUM = 500
    FW_BOLD = 700
    RUSSIAN_CHARSET = 204
    OUT_TT_PRECIS = 4
    CLIP_DEFAULT_PRECIS = 0
    ANTIALIASED_QUALITY = 4
    DEFAULT_PITCH = 0
    FF_SWISS = 32
    DIB_RGB_COLORS = 0
    BI_RGB = 0
    OPAQUE = 2
    TA_CENTER = 6
    TA_BASELINE = 24

    class SIZE(ctypes.Structure):
        _fields_ = [("cx", wintypes.LONG), ("cy", wintypes.LONG)]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", wintypes.LONG),
            ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", wintypes.LONG),
            ("biYPelsPerMeter", wintypes.LONG),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [
            ("bmiHeader", BITMAPINFOHEADER),
            ("bmiColors", wintypes.DWORD * 3),
        ]

    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateFontW.argtypes = [
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
        wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
        wintypes.LPCWSTR,
    ]
    gdi32.CreateFontW.restype = wintypes.HFONT
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.GetTextExtentPoint32W.argtypes = [
        wintypes.HDC, wintypes.LPCWSTR, ctypes.c_int, ctypes.POINTER(SIZE)
    ]
    gdi32.GetTextExtentPoint32W.restype = wintypes.BOOL
    gdi32.CreateDIBSection.argtypes = [
        wintypes.HDC, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
        ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD,
    ]
    gdi32.CreateDIBSection.restype = wintypes.HBITMAP
    gdi32.SetBkMode.argtypes = [wintypes.HDC, ctypes.c_int]
    gdi32.SetBkColor.argtypes = [wintypes.HDC, wintypes.COLORREF]
    gdi32.SetTextColor.argtypes = [wintypes.HDC, wintypes.COLORREF]
    gdi32.SetTextAlign.argtypes = [wintypes.HDC, wintypes.UINT]
    gdi32.TextOutW.argtypes = [
        wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.LPCWSTR, ctypes.c_int
    ]
    gdi32.TextOutW.restype = wintypes.BOOL
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteDC.argtypes = [wintypes.HDC]

    measure_dc = gdi32.CreateCompatibleDC(None)
    if not measure_dc:
        return _fallback_mask(text, font, angle_tenths=angle_tenths)

    weight = FW_BOLD if font.bold else FW_NORMAL
    gdi_size = max(1, int(font.size * font.render_scale))
    measure_font = gdi32.CreateFontW(
        -gdi_size, 0, 0, 0, weight,
        0, 0, 0,
        RUSSIAN_CHARSET,
        OUT_TT_PRECIS,
        CLIP_DEFAULT_PRECIS,
        ANTIALIASED_QUALITY,
        DEFAULT_PITCH | FF_SWISS,
        font.face,
    )
    if not measure_font:
        gdi32.DeleteDC(measure_dc)
        return _fallback_mask(text, font, angle_tenths=angle_tenths)

    old_measure_font = gdi32.SelectObject(measure_dc, measure_font)
    extent = SIZE()
    measured = gdi32.GetTextExtentPoint32W(
        measure_dc, text, len(text), ctypes.byref(extent)
    )
    gdi32.SelectObject(measure_dc, old_measure_font)
    gdi32.DeleteObject(measure_font)
    gdi32.DeleteDC(measure_dc)

    if not measured:
        return _fallback_mask(text, font, angle_tenths=angle_tenths)

    # Квадратный холст исключает обрезание при любом повороте шрифта.
    side = max(16, int(extent.cx + extent.cy + 16))

    hdc = gdi32.CreateCompatibleDC(None)
    if not hdc:
        return _fallback_mask(text, font, angle_tenths=angle_tenths)

    hfont = gdi32.CreateFontW(
        -gdi_size, 0,
        int(angle_tenths), int(angle_tenths),
        weight,
        0, 0, 0,
        RUSSIAN_CHARSET,
        OUT_TT_PRECIS,
        CLIP_DEFAULT_PRECIS,
        ANTIALIASED_QUALITY,
        DEFAULT_PITCH | FF_SWISS,
        font.face,
    )
    if not hfont:
        gdi32.DeleteDC(hdc)
        return _fallback_mask(text, font, angle_tenths=angle_tenths)

    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = side
    bmi.bmiHeader.biHeight = -side
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = BI_RGB

    bits = ctypes.c_void_p()
    bitmap = gdi32.CreateDIBSection(
        hdc, ctypes.byref(bmi), DIB_RGB_COLORS, ctypes.byref(bits), None, 0
    )
    if not bitmap or not bits.value:
        gdi32.DeleteObject(hfont)
        gdi32.DeleteDC(hdc)
        return _fallback_mask(text, font, angle_tenths=angle_tenths)

    old_bitmap = gdi32.SelectObject(hdc, bitmap)
    old_font = gdi32.SelectObject(hdc, hfont)
    try:
        ctypes.memset(bits, 0xFF, side * side * 4)
        gdi32.SetBkMode(hdc, OPAQUE)
        gdi32.SetBkColor(hdc, 0x00FFFFFF)
        gdi32.SetTextColor(hdc, 0x00000000)
        gdi32.SetTextAlign(hdc, TA_CENTER | TA_BASELINE)

        # Центр холста + базовая линия обеспечивают одинаковую привязку
        # горизонтального и вертикального текста.
        gdi32.TextOutW(hdc, side // 2, side // 2, text, len(text))

        raw = ctypes.string_at(bits, side * side * 4)
        rgba = Image.frombuffer(
            "RGBA", (side, side), raw, "raw", "BGRA", 0, 1
        ).copy()

        # Белый фон -> прозрачность 0, чёрный текст -> 255,
        # полутона GDI сохраняются как сглаженный alpha-канал.
        luminance = rgba.convert("L")
        mask = Image.eval(luminance, lambda value: 255 - value)
        box = mask.getbbox()
        if not box:
            return Image.new("L", (1, 1), 0)
        mask = mask.crop(box)
        if font.render_scale > 1:
            target_w = max(1, int(round(mask.width / font.render_scale)))
            target_h = max(1, int(round(mask.height / font.render_scale)))
            mask = mask.resize((target_w, target_h), Image.Resampling.LANCZOS)

        # FIX 20A: расширение применяется только к явно назначенной роли текста.
        if abs(float(font.width_scale) - 1.0) > 1e-9:
            if angle_tenths % 1800 == 0:
                scaled_w = max(1, int(round(mask.width * font.width_scale)))
                mask = mask.resize((scaled_w, mask.height), Image.Resampling.LANCZOS)
            else:
                scaled_h = max(1, int(round(mask.height * font.width_scale)))
                mask = mask.resize((mask.width, scaled_h), Image.Resampling.LANCZOS)

        # FIX 22: отдельное увеличение размера только у явно назначенной роли.
        if abs(float(font.size_scale) - 1.0) > 1e-9:
            scaled_w = max(1, int(round(mask.width * font.size_scale)))
            scaled_h = max(1, int(round(mask.height * font.size_scale)))
            mask = mask.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)

        # FIX 23: локальная коррекция толщины только назначенной роли текста.
        # 2% реализуются мягким смешиванием исходной маски с расширенной,
        # без изменения подписей пиков и без скачка толщины на целый пиксель.
        if float(font.weight_scale) > 1.0 + 1e-9:
            expanded = mask.filter(ImageFilter.MaxFilter(3))
            amount = max(0.0, min(1.0, float(font.weight_scale) - 1.0))
            mask = Image.blend(mask, expanded, amount)

        # Интенсивность начертания регулируется отдельно от геометрии.
        if float(font.intensity) < 1.0 - 1e-9:
            factor = max(0.0, min(1.0, float(font.intensity)))
            mask = mask.point(lambda value: int(round(value * factor)))

        # FIX 24: мягкость края только для явно назначенной роли текста.
        # 8% смешивает исходную маску с лёгким GaussianBlur, сохраняя размер.
        if float(font.softness) > 1e-9:
            softened = mask.filter(ImageFilter.GaussianBlur(radius=0.65))
            amount = max(0.0, min(1.0, float(font.softness)))
            mask = Image.blend(mask, softened, amount)
        return mask
    finally:
        gdi32.SelectObject(hdc, old_font)
        gdi32.SelectObject(hdc, old_bitmap)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteObject(hfont)
        gdi32.DeleteDC(hdc)


def _paste(image, mask, x, y, color):
    layer = Image.new("RGBA", mask.size, tuple(color) + (255,))
    layer.putalpha(mask)
    image.alpha_composite(layer, (int(x), int(y)))


def draw_bitmap_text(image, text, x, y, font, color, *, anchor="lt"):
    if not text:
        return (0, 0)

    mask = _gdi_mask(text, font, angle_tenths=0)
    px, py = int(round(x)), int(round(y))

    if anchor == "mm":
        px -= mask.width // 2
        py -= mask.height // 2
    elif anchor == "rm":
        px -= mask.width
        py -= mask.height // 2
    elif anchor == "lm":
        py -= mask.height // 2
    elif anchor == "rt":
        px -= mask.width

    _paste(image, mask, px, py, color)
    return mask.size


def draw_vertical_text(
    image, text, x, bottom_y, font, color, *,
    bottom_gap=0, min_y=1, min_x=0, max_x=None,
    center_on_y=False,
):
    if not text:
        return

    # Нативное GDI-вращение на 90°, без PIL transpose/rotate.
    mask = _gdi_mask(text, font, angle_tenths=900)
    if center_on_y:
        py = int(round(bottom_y - mask.height / 2))
    else:
        py = int(round(bottom_y - bottom_gap)) - mask.height

    if py < min_y:
        cut = min(mask.height - 1, min_y - py)
        mask = mask.crop((0, cut, mask.width, mask.height))
        py = min_y

    if max_x is None:
        max_x = image.width - 1

    px = int(round(x - mask.width / 2))
    px = max(min_x, min(px, max_x - mask.width + 1))

    if mask.width > 0 and mask.height > 0:
        _paste(image, mask, px, py, color)
