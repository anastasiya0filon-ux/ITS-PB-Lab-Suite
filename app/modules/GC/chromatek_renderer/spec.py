# -*- coding: utf-8 -*-
from __future__ import annotations
import json
from pathlib import Path
_SPEC_PATH=Path(__file__).with_name("rendering_spec.json")
SPEC=json.loads(_SPEC_PATH.read_text(encoding="utf-8"))
def detector_spec(detector:str):
    return SPEC["pid1" if detector=="ПИД-1" else "pid2"]


# Measured overrides from the eight instrument reports.
try:
    from .passport import PASSPORT as _MP
    SPEC['canvas']['width']=int(_MP['canvas']['width'])
    SPEC['canvas']['height']=int(_MP['canvas']['height'])
    SPEC['plot']['x0']=int(_MP['geometry']['x_axis_left'])
    SPEC['plot']['x1']=int(_MP['geometry']['x_axis_right'])
    SPEC['plot']['y1']=int(_MP['geometry']['baseline_y'])
    SPEC['fonts']['axis_size']=int(_MP['text']['axis_px'])
    SPEC['fonts']['analytic_size']=int(_MP['text']['analytic_px'])
    SPEC['fonts']['background_size']=int(_MP['text']['background_px'])
    SPEC['fonts']['family_order']=list(_MP['text']['family_order'])
    for _det in ('ПИД-1','ПИД-2'):
        _key='pid1' if _det=='ПИД-1' else 'pid2'
        SPEC[_key]['rgb']=list(_MP['detectors'][_det]['primary_rgb'])
        SPEC[_key]['axis_rgb']=list(_MP['detectors'][_det]['axis_rgb'])
        SPEC[_key]['late_start']=float(_MP['detectors'][_det]['late_start'])
        SPEC[_key]['late_end_fraction']=float(_MP['detectors'][_det]['late_end_fraction'])
except Exception:
    pass
