# -*- coding: utf-8 -*-
from __future__ import annotations
import json
from pathlib import Path
_PATH=Path(__file__).with_name('measured_passport.json')
PASSPORT=json.loads(_PATH.read_text(encoding='utf-8'))
def detector_passport(name:str)->dict:
    return PASSPORT['detectors'][name]
