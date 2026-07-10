# -*- coding: utf-8 -*-
from __future__ import annotations
import shutil
from datetime import datetime
from pathlib import Path

VERSION = "0.3.2"

def locate_project(start: Path) -> Path:
    for root in [start, start.parent, *start.parents]:
        if (root / "app" / "modules" / "AAS" / "aas_report_generator.py").is_file():
            return root
    raise FileNotFoundError(
        "ITS-PB-Lab-Suite root was not found. Put AAS_RELEASE_0_3_2 inside the project root."
    )

def main() -> int:
    package = Path(__file__).resolve().parent
    payload = package / "payload"
    root = locate_project(package)
    target_aas = root / "app" / "modules" / "AAS"

    marker = 'AAS_RELEASE_VERSION = "0.3.2-six-elements-time-fix"'
    source_code = (payload / "app/modules/AAS/aas_report_generator.py").read_text(encoding="utf-8")
    compile(source_code, "aas_report_generator.py", "exec")
    if marker not in source_code:
        raise RuntimeError("Release marker is missing.")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = target_aas / f"backup_before_aas_0_3_2_{stamp}"
    backup.mkdir(parents=True)

    files = [
        "aas_report_generator.py",
        "AAS_template.xlsx",
    ]
    for name in files:
        old = target_aas / name
        if old.exists():
            shutil.copy2(old, backup / name)

    for folder in ("templates", "configs"):
        (backup / folder).mkdir(exist_ok=True)
        for source in (payload / "app/modules/AAS" / folder).iterdir():
            old = target_aas / folder / source.name
            if old.exists():
                shutil.copy2(old, backup / folder / source.name)

    shutil.copytree(payload / "app/modules/AAS", target_aas, dirs_exist_ok=True)
    shutil.copytree(payload / "docs", root / "docs", dirs_exist_ok=True)

    for cache in (root / "app/__pycache__", target_aas / "__pycache__"):
        if cache.exists():
            shutil.rmtree(cache, ignore_errors=True)

    installed = (target_aas / "aas_report_generator.py").read_text(encoding="utf-8")
    if marker not in installed:
        raise RuntimeError("Post-install verification failed.")

    print()
    print("AAS RELEASE 0.3.2 INSTALLED SUCCESSFULLY")
    print(f"Project: {root}")
    print(f"Backup:  {backup}")
    print("Elements: Al, Ag, Zn, Cu, Ni, Co")
    print("Unique timestamp logic: ENABLED")
    print()
    print("Next: run RUN_FROM_SOURCE.bat and test AAS generation.")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print()
        print("INSTALLATION FAILED")
        print(str(exc))
        input("Press Enter to close...")
        raise SystemExit(1)
