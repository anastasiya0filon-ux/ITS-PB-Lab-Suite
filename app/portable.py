# -*- coding: utf-8 -*-
from __future__ import annotations
import sys
from pathlib import Path

def application_dir() -> Path:
    if getattr(sys, "frozen", False):
        bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        candidates = (
            bundle_root / "app",
            bundle_root,
            Path(sys.executable).resolve().parent / "_internal" / "app",
            Path(sys.executable).resolve().parent / "app",
        )
        for candidate in candidates:
            if (candidate / "modules").is_dir():
                return candidate
        raise FileNotFoundError("Не найден каталог ресурсов app/modules в portable-сборке")
    return Path(__file__).resolve().parent
