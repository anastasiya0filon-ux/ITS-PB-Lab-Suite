# -*- coding: utf-8 -*-
from __future__ import annotations
WIDTH = 718
HEIGHT = 321
PLOT_X0 = 21
PLOT_X1 = 717
PLOT_Y0 = 0
PLOT_Y1 = 298
PLOT_WIDTH = PLOT_X1 - PLOT_X0
PLOT_HEIGHT = PLOT_Y1 - PLOT_Y0
X_MIN = 0.0
X_MAX = 38.96

def x_to_px(t: float, x_min: float = X_MIN, x_max: float = X_MAX) -> float:
    return PLOT_X0 + PLOT_WIDTH * (float(t) - float(x_min)) / (float(x_max) - float(x_min))

def y_to_px(value: float, y_max: float) -> float:
    y_max = max(float(y_max), 1e-12)
    value = max(0.0, min(float(value), y_max))
    return PLOT_Y1 - PLOT_HEIGHT * value / y_max
