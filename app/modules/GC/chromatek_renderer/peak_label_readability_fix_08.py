# -*- coding: utf-8 -*-
"""Рабочий runtime-адаптер отрисовки вертикальных подписей пиков."""
from __future__ import annotations

from .fonts import draw_vertical_text


def draw_vertical_text_readable(
    image,
    text,
    x,
    bottom_y,
    font,
    color,
    *,
    min_y=1,
    min_x=0,
    max_x=None,
    bottom_gap=0,
):
    """Рисует подпись пика без изменения её координат и типографики."""
    return draw_vertical_text(
        image,
        text,
        x,
        bottom_y,
        font,
        color,
        bottom_gap=bottom_gap,
        min_y=min_y,
        min_x=min_x,
        max_x=max_x,
    )
