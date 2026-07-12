# -*- coding: utf-8 -*-
from __future__ import annotations
from .spec import SPEC
WIDTH=int(SPEC["canvas"]["width"]); HEIGHT=int(SPEC["canvas"]["height"])
PLOT_X0=int(SPEC["plot"]["x0"]); PLOT_X1=int(SPEC["plot"]["x1"])
PLOT_Y0=int(SPEC["plot"]["y0"]); PLOT_Y1=int(SPEC["plot"]["y1"])
PLOT_WIDTH=PLOT_X1-PLOT_X0; PLOT_HEIGHT=PLOT_Y1-PLOT_Y0
X_MIN=0.0; X_MAX=38.96
def x_to_px(t:float,x_min:float=X_MIN,x_max:float=X_MAX)->float:
    return PLOT_X0+PLOT_WIDTH*(float(t)-x_min)/(x_max-x_min)
def y_to_px(value:float,y_max:float)->float:
    y_max=max(float(y_max),1e-12); v=max(0.0,min(float(value),y_max))
    return PLOT_Y1-PLOT_HEIGHT*v/y_max
