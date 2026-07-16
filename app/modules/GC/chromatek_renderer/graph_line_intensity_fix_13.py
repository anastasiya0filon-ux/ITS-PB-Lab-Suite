# -*- coding: utf-8 -*-
"""Рабочий runtime-модуль визуальной линии хроматограммы.

Восстановлен по активному вызову compositor.py и маркерам:
- GC_GRAPH_LINE_INTENSITY_85_FIX_13;
- GC_PID1_LINE_WIDTH_104_INTENSITY_65_FIX_13A.
"""
from __future__ import annotations

import hashlib


def _blend_to_white(color, intensity: float):
    factor = max(0.0, min(1.0, float(intensity)))
    return tuple(
        int(round(255 - (255 - int(channel)) * factor))
        for channel in tuple(color)[:3]
    )


def soften_graph_line_color(color, detector):
    """Возвращает интенсивность линии, принятую последним активным FIX 13A."""
    intensity = 0.65 if str(detector) == "ПИД-1" else 0.85
    return _blend_to_white(color, intensity)


def draw_graph_line_width_104(
    draw,
    xy,
    *,
    fill,
    width=1,
    detector=None,
):
    """Рисует основную линию 1 px и мягко эмулирует 104% для ПИД-1.

    PIL принимает только целую ширину. Поэтому дополнительные соседние
    пиксели добавляются детерминированно примерно для 4% сегментов.
    Для ПИД-2 сохраняется обычная линия 1 px.
    """
    draw.line(xy, fill=fill, width=max(1, int(width)))

    if str(detector) != "ПИД-1" or int(width) != 1:
        return

    x0, y0, x1, y1 = (int(round(value)) for value in xy)
    key = f"{x0}|{y0}|{x1}|{y1}".encode("utf-8")
    selector = int.from_bytes(hashlib.sha256(key).digest()[:2], "big")

    # 4% сегментов получают один соседний пиксель.
    if selector % 100 < 4:
        if abs(x1 - x0) >= abs(y1 - y0):
            shifted = (x0, y0 + 1, x1, y1 + 1)
        else:
            shifted = (x0 + 1, y0, x1 + 1, y1)
        draw.line(shifted, fill=fill, width=1)
