from __future__ import annotations
from pathlib import Path

METHOD_ID = "MUK_4_1_3166"
METHOD_DIR = Path(__file__).resolve().parent
MODEL_PATH = METHOD_DIR / "calibration_model.json"

DESCRIPTOR = {
    "method_id": METHOD_ID,
    "title": "МУК 4.1.3166",
    "version": "area-height-width-6point-2.0",
    "calibration_model_path": MODEL_PATH,
    "supported_detectors": ("ПИД-1", "ПИД-2"),
    "default_duration_min": 39.0,
}
