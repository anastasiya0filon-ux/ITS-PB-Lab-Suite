# -*- coding: utf-8 -*-
from __future__ import annotations

# Масштабы сняты с восьми исходных отчётов Хроматэк.
# family, nominal -> detector: x_max, y_max, y_tick_step
REFERENCE_SCALES = {
    "part1": {
        0.1: {"ПИД-1": (38.943, 17.0, 1.0), "ПИД-2": (38.951, 50.0, 5.0)},
        0.2: {"ПИД-1": (38.963, 65.0, 5.0), "ПИД-2": (38.961, 90.0, 10.0)},
        0.5: {"ПИД-1": (38.949, 150.0, 25.0), "ПИД-2": (38.947, 125.0, 25.0)},
        1.0: {"ПИД-1": (38.961, 350.0, 50.0), "ПИД-2": (38.959, 350.0, 50.0)},
    },
    "part2": {
        0.005: {"ПИД-1": (38.955, 25.0, 2.5), "ПИД-2": (38.954, 80.0, 10.0)},
        0.02: {"ПИД-1": (38.951, 40.0, 5.0), "ПИД-2": (38.949, 80.0, 10.0)},
        0.05: {"ПИД-1": (38.952, 125.0, 25.0), "ПИД-2": (38.949, 150.0, 25.0)},
        0.1: {"ПИД-1": (38.956, 450.0, 50.0), "ПИД-2": (38.954, 550.0, 100.0)},
    },
}

PART1_COMPONENTS = {
    "Ацетальдегид", "Метанол", "Ацетон", "Метилацетат", "Этилацетат",
    "Изопропанол", "Н-пропанол", "Изобутанол", "Н-бутанол", "Бутилацетат",
}
PART2_COMPONENTS = {
    "Гексан", "Гептан", "Бензол", "Акрилонитрил", "Толуол", "Этилбензол",
    "п-Ксилол", "м-Ксилол", "о-Ксилол", "Изопропилбензол", "Стирол", "Метилстирол",
}

def _nearest_level(family: str, concentration: float) -> float:
    levels = tuple(REFERENCE_SCALES[family])
    c = max(float(concentration), 0.0)
    return min(levels, key=lambda level: (abs(level-c), level))

def choose_reference_scale(component_values: dict[str, float], detector: str) -> dict:
    candidates=[]
    for family, names in (("part1", PART1_COMPONENTS), ("part2", PART2_COMPONENTS)):
        active=[float(v) for n,v in component_values.items() if n in names and float(v)>0]
        if not active:
            continue
        level=_nearest_level(family,max(active))
        x_max,y_max,tick=REFERENCE_SCALES[family][level][detector]
        candidates.append({"family":family,"level":level,"x_max":x_max,"y_max":y_max,"y_tick_step":tick})
    if not candidates:
        family="part2"; level=0.005
        x_max,y_max,tick=REFERENCE_SCALES[family][level][detector]
        return {"family":family,"level":level,"x_max":x_max,"y_max":y_max,"y_tick_step":tick}
    # При смешанной пробе сохраняем тот исходный масштаб, который вмещает обе группы.
    chosen=max(candidates,key=lambda x:x["y_max"] )
    return chosen
