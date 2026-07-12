# -*- coding: utf-8 -*-
from __future__ import annotations
import json
from pathlib import Path
PROFILE_LIBRARY=json.loads(Path(__file__).with_name("profile_library.json").read_text(encoding="utf-8"))
def zone_for(t:float):
    for z in PROFILE_LIBRARY["zones"]:
        if float(z["from"]) <= t < float(z["to"]): return z
    return PROFILE_LIBRARY["zones"][-1]
def component_profile(name:str):
    return PROFILE_LIBRARY["component_overrides"].get(str(name),{})
def clusters_for(detector:str):
    return PROFILE_LIBRARY["background_clusters"][detector]
def late_knots(detector:str):
    return PROFILE_LIBRARY["late_rise_knots"][detector]
