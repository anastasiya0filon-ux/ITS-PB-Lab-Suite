# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
import os
from PIL import Image, ImageDraw, ImageFont


@dataclass(frozen=True)
class FontSpec:
    size: int
    bold: bool = False
    face: str = "Arial Narrow"


def load_font(size: int, *, bold: bool = False):
    return FontSpec(
        size=max(1, int(round(size))),
        bold=bool(bold),
    )


def _fallback_mask(text: str, font: FontSpec) -> Image.Image:
    candidates = [
        r"C:\Windows\Fonts\arialn.ttf",
        r"C:\Windows\Fonts\tahoma.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf",
    ]
    pil_font = None
    for path in candidates:
        try:
            pil_font = ImageFont.truetype(path, font.size)
            break
        except Exception:
            pass
    pil_font = pil_font or ImageFont.load_default()

    probe = Image.new("L", (4, 4), 0)
    box = ImageDraw.Draw(probe).textbbox((0, 0), text, font=pil_font, stroke_width=0)
    mask = Image.new(
        "L",
        (max(1, box[2] - box[0] + 2), max(1, box[3] - box[1] + 2)),
        0,
    )
    ImageDraw.Draw(mask).text(
        (1 - box[0], 1 - box[1]),
        text,
        font=pil_font,
        fill=255,
        stroke_width=0,
    )
    return mask


def _gdi_mask(text: str, font: FontSpec) -> Image.Image:
    if os.name != "nt":
        return _fallback_mask(text, font)

    import ctypes
    from ctypes import wintypes

    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

    FW_NORMAL = 400
    FW_MEDIUM = 500
    FW_BOLD = 700
    RUSSIAN_CHARSET = 204
    OUT_TT_PRECIS = 4
    CLIP_DEFAULT_PRECIS = 0
    NONANTIALIASED_QUALITY = 3
    DEFAULT_PITCH = 0
    FF_SWISS = 32
    DIB_RGB_COLORS = 0
    BI_RGB = 0
    OPAQUE = 2

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
    gdi32.TextOutW.argtypes = [
        wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.LPCWSTR, ctypes.c_int
    ]
    gdi32.TextOutW.restype = wintypes.BOOL
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteDC.argtypes = [wintypes.HDC]

    hdc = gdi32.CreateCompatibleDC(None)
    if not hdc:
        return _fallback_mask(text, font)

    # Чуть плотнее обычного начертания, но не bold.
    weight = FW_BOLD if font.bold else FW_MEDIUM
    hfont = gdi32.CreateFontW(
        -font.size, 0, 0, 0, weight,
        0, 0, 0,
        RUSSIAN_CHARSET,
        OUT_TT_PRECIS,
        CLIP_DEFAULT_PRECIS,
        NONANTIALIASED_QUALITY,
        DEFAULT_PITCH | FF_SWISS,
        font.face,
    )
    if not hfont:
        gdi32.DeleteDC(hdc)
        return _fallback_mask(text, font)

    old_font = gdi32.SelectObject(hdc, hfont)
    extent = SIZE()

    if not gdi32.GetTextExtentPoint32W(hdc, text, len(text), ctypes.byref(extent)):
        gdi32.SelectObject(hdc, old_font)
        gdi32.DeleteObject(hfont)
        gdi32.DeleteDC(hdc)
        return _fallback_mask(text, font)

    width = max(1, int(extent.cx) + 4)
    height = max(1, int(extent.cy) + 4)

    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = width
    bmi.bmiHeader.biHeight = -height
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = BI_RGB

    bits = ctypes.c_void_p()
    bitmap = gdi32.CreateDIBSection(
        hdc, ctypes.byref(bmi), DIB_RGB_COLORS, ctypes.byref(bits), None, 0
    )
    if not bitmap or not bits.value:
        gdi32.SelectObject(hdc, old_font)
        gdi32.DeleteObject(hfont)
        gdi32.DeleteDC(hdc)
        return _fallback_mask(text, font)

    old_bitmap = gdi32.SelectObject(hdc, bitmap)
    try:
        ctypes.memset(bits, 0xFF, width * height * 4)
        gdi32.SetBkMode(hdc, OPAQUE)
        gdi32.SetBkColor(hdc, 0x00FFFFFF)
        gdi32.SetTextColor(hdc, 0x00000000)
        gdi32.TextOutW(hdc, 2, 2, text, len(text))

        raw = ctypes.string_at(bits, width * height * 4)
        rgba = Image.frombuffer(
            "RGBA", (width, height), raw, "raw", "BGRA", 0, 1
        ).copy()
        mask = Image.eval(rgba.convert("L"), lambda value: 255 - value)
        box = mask.getbbox()
        return mask.crop(box) if box else Image.new("L", (1, 1), 0)
    finally:
        gdi32.SelectObject(hdc, old_bitmap)
        gdi32.SelectObject(hdc, old_font)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteObject(hfont)
        gdi32.DeleteDC(hdc)


def _paste(image, mask, x, y, color):
    layer = Image.new("RGBA", mask.size, tuple(color) + (255,))
    layer.putalpha(mask)
    image.alpha_composite(layer, (x, y))


def draw_bitmap_text(image, text, x, y, font, color, *, anchor="lt"):
    if not text:
        return (0, 0)
    mask = _gdi_mask(text, font)
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
):
    if not text:
        return

    mask = _gdi_mask(text, font).transpose(Image.Transpose.ROTATE_90)
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
