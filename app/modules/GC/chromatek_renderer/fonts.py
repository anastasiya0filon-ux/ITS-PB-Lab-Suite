# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .spec import SPEC


@dataclass(frozen=True)
class FontSpec:
    size: int
    bold: bool = False


def load_font(size: int, *, bold: bool = False):
    return FontSpec(max(1, int(round(size))), bool(bold))


def _fallback_mask(text: str, font: FontSpec) -> Image.Image:
    """Fallback for non-Windows test environments only."""
    candidates = [
        "/usr/share/fonts/truetype/liberation2/LiberationSansNarrow-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf",
    ]
    pil_font = None
    for path in candidates:
        try:
            pil_font = ImageFont.truetype(path, font.size)
            break
        except Exception:
            pass
    if pil_font is None:
        pil_font = ImageFont.load_default()

    probe = Image.new("L", (4, 4), 0)
    draw = ImageDraw.Draw(probe)
    box = draw.textbbox((0, 0), text, font=pil_font)
    w = max(1, box[2] - box[0] + 2)
    h = max(1, box[3] - box[1] + 2)
    canvas = Image.new("L", (w, h), 0)
    ImageDraw.Draw(canvas).text(
        (1 - box[0], 1 - box[1]),
        text,
        font=pil_font,
        fill=255,
        spacing=0,
        stroke_width=0,
    )
    return canvas


def _gdi_mask(text: str, font: FontSpec) -> Image.Image:
    """
    Render directly through Windows GDI, the same class of text engine used by
    classic Chromatek software. No Pillow/FreeType rasterization is used.
    """
    if os.name != "nt":
        return _fallback_mask(text, font)

    import ctypes
    from ctypes import wintypes

    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

    # Constants
    FW_NORMAL = 400
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
    TRANSPARENT = 1

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
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    gdi32.DeleteDC.restype = wintypes.BOOL
    gdi32.CreateFontW.restype = wintypes.HFONT
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteObject.restype = wintypes.BOOL
    gdi32.GetTextExtentPoint32W.argtypes = [
        wintypes.HDC, wintypes.LPCWSTR, ctypes.c_int, ctypes.POINTER(SIZE)
    ]
    gdi32.GetTextExtentPoint32W.restype = wintypes.BOOL
    gdi32.CreateDIBSection.argtypes = [
        wintypes.HDC,
        ctypes.POINTER(BITMAPINFO),
        wintypes.UINT,
        ctypes.POINTER(ctypes.c_void_p),
        wintypes.HANDLE,
        wintypes.DWORD,
    ]
    gdi32.CreateDIBSection.restype = wintypes.HBITMAP
    gdi32.SetBkMode.argtypes = [wintypes.HDC, ctypes.c_int]
    gdi32.SetBkMode.restype = ctypes.c_int
    gdi32.SetBkColor.argtypes = [wintypes.HDC, wintypes.COLORREF]
    gdi32.SetTextColor.argtypes = [wintypes.HDC, wintypes.COLORREF]
    gdi32.TextOutW.argtypes = [
        wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.LPCWSTR, ctypes.c_int
    ]
    gdi32.TextOutW.restype = wintypes.BOOL

    face = str(SPEC["fonts"].get("gdi_face", "Arial Narrow"))
    weight = FW_BOLD if font.bold else int(SPEC["fonts"].get("gdi_weight", FW_NORMAL))

    hdc = gdi32.CreateCompatibleDC(None)
    if not hdc:
        return _fallback_mask(text, font)

    hfont = gdi32.CreateFontW(
        -font.size,              # exact character height in pixels
        0,                       # natural width from the actual face
        0,
        0,
        weight,
        0,                       # italic
        0,                       # underline
        0,                       # strikeout
        RUSSIAN_CHARSET,
        OUT_TT_PRECIS,
        CLIP_DEFAULT_PRECIS,
        NONANTIALIASED_QUALITY,
        DEFAULT_PITCH | FF_SWISS,
        face,
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

    width = max(1, int(extent.cx) + 2)
    height = max(1, int(extent.cy) + 2)

    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = width
    bmi.bmiHeader.biHeight = -height  # top-down bitmap
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = BI_RGB

    bits = ctypes.c_void_p()
    hbitmap = gdi32.CreateDIBSection(
        hdc, ctypes.byref(bmi), DIB_RGB_COLORS, ctypes.byref(bits), None, 0
    )
    if not hbitmap or not bits:
        gdi32.SelectObject(hdc, old_font)
        gdi32.DeleteObject(hfont)
        gdi32.DeleteDC(hdc)
        return _fallback_mask(text, font)

    old_bitmap = gdi32.SelectObject(hdc, hbitmap)

    byte_count = width * height * 4

    # DIBSection memory is initially zeroed (black). If it is not explicitly
    # filled with white before TextOutW, inversion below turns the untouched
    # rectangle into a visible border/background box around every label.
    ctypes.memset(bits, 0xFF, byte_count)

    # Draw only after the bitmap has a real white background.
    gdi32.SetBkMode(hdc, OPAQUE)
    gdi32.SetBkColor(hdc, 0x00FFFFFF)
    gdi32.SetTextColor(hdc, 0x00000000)
    gdi32.TextOutW(hdc, 1, 1, text, len(text))

    raw = ctypes.string_at(bits, byte_count)
    rgba = Image.frombuffer(
        "RGBA",
        (width, height),
        raw,
        "raw",
        "BGRA",
        0,
        1,
    ).copy()

    # Convert exact GDI black-on-white output into an alpha mask.
    grey = rgba.convert("L")
    mask = Image.eval(grey, lambda value: 255 - value)
    box = mask.getbbox()
    if box:
        mask = mask.crop(box)
    else:
        mask = Image.new("L", (1, 1), 0)

    gdi32.SelectObject(hdc, old_bitmap)
    gdi32.SelectObject(hdc, old_font)
    gdi32.DeleteObject(hbitmap)
    gdi32.DeleteObject(hfont)
    gdi32.DeleteDC(hdc)

    return mask


def _paste_mask(image: Image.Image, mask: Image.Image, x: int, y: int, color) -> None:
    layer = Image.new("RGBA", mask.size, tuple(color) + (255,))
    layer.putalpha(mask)
    image.alpha_composite(layer, (x, y))


def draw_bitmap_text(
    image: Image.Image,
    text: str,
    x: float,
    y: float,
    font,
    color,
    *,
    anchor: str = "lt",
) -> tuple[int, int]:
    if not text:
        return (0, 0)

    mask = _gdi_mask(text, font)
    px = int(round(x))
    py = int(round(y))

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

    _paste_mask(image, mask, px, py, color)
    return mask.size


def draw_vertical_text(
    image: Image.Image,
    text: str,
    x: float,
    bottom_y: int,
    font,
    color,
    *,
    bottom_gap: int = 0,
    min_y: int = 1,
    min_x: int = 0,
    max_x: int | None = None,
):
    if not text:
        return

    mask = _gdi_mask(text, font)
    rotated = mask.transpose(Image.Transpose.ROTATE_90)

    anchor_bottom = int(round(bottom_y - bottom_gap))
    py = anchor_bottom - rotated.height

    if py < min_y:
        crop_top = min(rotated.height - 1, min_y - py)
        rotated = rotated.crop((0, crop_top, rotated.width, rotated.height))
        py = min_y

    if max_x is None:
        max_x = image.width - 1

    px = int(round(x - rotated.width / 2))
    px = max(min_x, min(px, max_x - rotated.width + 1))

    if rotated.width <= 0 or rotated.height <= 0:
        return

    _paste_mask(image, rotated, px, py, color)
