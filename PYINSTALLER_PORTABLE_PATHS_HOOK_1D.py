# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
from pathlib import Path

bundle = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
exe_dir = Path(sys.executable).resolve().parent

app_candidates = (
    bundle / "app",
    exe_dir / "_internal" / "app",
    exe_dir / "app",
)

paths: list[Path] = []

for app_dir in app_candidates:
    if not app_dir.is_dir():
        continue

    modules_dir = app_dir / "modules"
    paths.extend((app_dir, modules_dir))

    if modules_dir.is_dir():
        paths.extend(
            item for item in modules_dir.iterdir()
            if item.is_dir()
        )

    gc_dir = modules_dir / "GC"
    paths.extend((
        gc_dir,
        gc_dir / "chromatek_renderer",
        gc_dir / "methods",
        gc_dir / "platform",
        gc_dir / "passports",
        gc_dir / "profiles",
    ))

for path in reversed(paths):
    if not path.is_dir():
        continue
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)
