# -*- coding: utf-8 -*-
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path.cwd()
APP = ROOT / "app"
CORE = APP / "core"
MODULES = APP / "modules"
TOXICITY = MODULES / "Toxicity"
TOX_TEMPLATE = TOXICITY / "tox_template.docx"
ENTRY = APP / "main.pyw"
PORTABLE = APP / "portable.py"
HOOK = ROOT / "PYINSTALLER_PORTABLE_PATHS_HOOK_1D.py"

EXE_NAME = "ITS-PB-Lab-Suite"
PACKAGE_NAME = "ITS-PB-Lab-Suite-0.4.0-rc2-WIN64"

BUILD_DIR = ROOT / "build"
DIST_DIR = ROOT / "dist"
PACKAGE_DIR = ROOT / "release_packages"
STAGE_DIR = PACKAGE_DIR / PACKAGE_NAME
ZIP_PATH = PACKAGE_DIR / f"{PACKAGE_NAME}.zip"


def fail(message: str) -> None:
    print()
    print("ОШИБКА:", message)
    print()
    raise SystemExit(1)


def run(command: list[str]) -> None:
    print()
    print(">", subprocess.list2cmdline(command))
    subprocess.run(command, cwd=ROOT, check=True)


def validate() -> None:
    required = (
        ENTRY,
        PORTABLE,
        HOOK,
        CORE / "docx_clone_engine.py",
        CORE / "rtf_clone_engine.py",
        TOX_TEMPLATE,
        MODULES / "GC" / "chromatek_renderer"
        / "peak_label_readability_fix_08.py",
        MODULES / "GC" / "chromatek_renderer"
        / "graph_line_intensity_fix_13.py",
    )
    missing = [path for path in required if not path.exists()]
    if missing:
        fail(
            "Отсутствуют обязательные файлы:\n"
            + "\n".join(str(path) for path in missing)
        )


def module_paths() -> list[Path]:
    result = [ROOT, APP, CORE, MODULES]

    for name in ("AAS", "ICP_OS", "Toxicity", "GC"):
        path = MODULES / name
        if path.is_dir():
            result.append(path)

    gc = MODULES / "GC"
    for relative in (
        "chromatek_renderer",
        "methods",
        "platform",
        "passports",
        "profiles",
    ):
        path = gc / relative
        if path.is_dir():
            result.append(path)

    unique: list[Path] = []
    seen: set[Path] = set()

    for path in result:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)

    return unique


def main() -> None:
    print("PORTABLE WIN64 BUILD 1G START")
    validate()

    run([sys.executable, "-m", "pip", "install", "pyinstaller"])

    requirements = ROOT / "requirements.txt"
    if requirements.exists():
        run([
            sys.executable,
            "-m",
            "pip",
            "install",
            "-r",
            str(requirements),
        ])

    for path in (BUILD_DIR, DIST_DIR, STAGE_DIR):
        if path.exists():
            shutil.rmtree(path)

    PACKAGE_DIR.mkdir(parents=True, exist_ok=True)

    if ZIP_PATH.exists():
        ZIP_PATH.unlink()

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onedir",
        "--name",
        EXE_NAME,
        "--runtime-hook",
        str(HOOK),
        "--collect-all",
        "PIL",
        "--collect-all",
        "openpyxl",
        "--collect-all",
        "docx",
        "--add-data",
        f"{CORE};app/core",
        "--add-data",
        f"{TOX_TEMPLATE};.",
        "--add-data",
        f"{MODULES};app/modules",
        "--add-data",
        f"{PORTABLE};app",
    ]

    hidden_imports = (
        "json",
        "ctypes",
        "ctypes.wintypes",
        "math",
        "random",
        "statistics",
        "datetime",
        "pathlib",
        "re",
        "os",
        "sys",
        "csv",
        "decimal",
        "threading",
        "tempfile",
        "shutil",
        "zipfile",
        "traceback",
        "copy",
        "time",
        "uuid",
        "importlib",
        "importlib.util",
        "dataclasses",
        "typing",
        "collections",
        "collections.abc",
        "xml",
        "xml.etree",
        "xml.etree.ElementTree",
        "core",
        "core.rtf_clone_engine",
        "core.docx_clone_engine",
    )

    for module_name in hidden_imports:
        command.extend(["--hidden-import", module_name])

    assets = APP / "assets"
    if assets.is_dir():
        command.extend([
            "--add-data",
            f"{assets};app/assets",
        ])

    for path in module_paths():
        command.extend(["--paths", str(path)])

    command.append(str(ENTRY))
    run(command)

    built = DIST_DIR / EXE_NAME
    if not built.is_dir():
        fail(f"PyInstaller не создал каталог: {built}")

    shutil.copytree(built, STAGE_DIR)

    (STAGE_DIR / "output").mkdir(exist_ok=True)
    (STAGE_DIR / "logs").mkdir(exist_ok=True)

    (STAGE_DIR / "ИНСТРУКЦИЯ_ИСПЫТАТЕЛЮ.txt").write_text(
        "ITS-PB LAB SUITE v0.4.0-rc2\n"
        "PORTABLE TEST RELEASE 1G\n\n"
        "1. Удалите старую распакованную тестовую версию.\n"
        "2. Полностью распакуйте новый ZIP.\n"
        "3. Не запускайте EXE из ZIP.\n"
        "4. Запустите ITS-PB-Lab-Suite.exe.\n"
        "5. Python и Git не требуются.\n"
        "6. Проверьте создание отчётов.\n"
        "7. При ошибке пришлите полный скриншот.\n",
        encoding="utf-8",
    )

    (STAGE_DIR / "ЗАПУСТИТЬ_ПРОГРАММУ.bat").write_text(
        '@echo off\r\n'
        'cd /d "%~dp0"\r\n'
        'start "" "ITS-PB-Lab-Suite.exe"\r\n',
        encoding="utf-8",
        newline="",
    )

    with ZipFile(ZIP_PATH, "w", ZIP_DEFLATED) as archive:
        for file in STAGE_DIR.rglob("*"):
            if file.is_file():
                archive.write(
                    file,
                    file.relative_to(PACKAGE_DIR),
                )

    print()
    print("PORTABLE WIN64 BUILD 1G COMPLETE")
    print("Архив:", ZIP_PATH)
    print("Распакуйте ZIP в новую папку и проверьте EXE.")


if __name__ == "__main__":
    main()
