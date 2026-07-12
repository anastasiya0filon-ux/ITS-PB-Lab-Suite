# -*- coding: utf-8 -*-
"""Отчёты ГХ на общем движке клонирования приборных документов."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Mapping, Sequence

ROOT = Path(__file__).resolve().parent
APP_ROOT = ROOT.parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

try:
    from core.docx_clone_engine import (
        clone_docx,
        clone_table_rows,
        replace_text,
        set_table_cell,
        set_text_preserve_style,
        unique_cells,
    )
except ModuleNotFoundError:
    import importlib.util
    engine_path = APP_ROOT / "core" / "docx_clone_engine.py"
    spec = importlib.util.spec_from_file_location("docx_clone_engine_gc", engine_path)
    if spec is None or spec.loader is None:
        raise
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)
    clone_docx = engine.clone_docx
    clone_table_rows = engine.clone_table_rows
    replace_text = engine.replace_text
    set_table_cell = engine.set_table_cell
    set_text_preserve_style = engine.set_text_preserve_style
    unique_cells = engine.unique_cells

TEMPLATE = ROOT / "report_templates" / "GC_ANALYSIS_REPORT_TEMPLATE.docx"
COUNTER = ROOT / "data" / "chromatogram_counter.txt"


def _next_counter() -> int:
    try:
        current = int(COUNTER.read_text(encoding="utf-8").strip())
    except Exception:
        current = 1228
    current += 1
    COUNTER.parent.mkdir(parents=True, exist_ok=True)
    COUNTER.write_text(str(current), encoding="utf-8")
    return current


def _fmt_sig(value: float) -> str:
    return f"{float(value):.5g}"


def generate_gc_report(
    *,
    output_path: Path,
    passport: Mapping[str, object],
    results: Sequence[Mapping[str, object]],
    pid1_image: Path,
    pid2_image: Path,
    pid1_interval: str = "38.955",
    pid2_interval: str = "38.954",
) -> Path:
    if not results:
        raise ValueError("Нет результатов для отчёта ГХ")

    def transform(root):
        replacements = {
            "Дрынина А.П.": passport["operator"],
            "№116   2022-02-03 08:43:44":
                f'№{passport["chromatogram_number"]}   {passport["analysis_datetime"]}',
            r"C:\Analytic 3\Projects\МУК 4_1_3166_5\.chromatograms\2022-02-03 08-43-44 0116.chrx":
                passport["chromatogram_file"],
            "Хроматэк-Кристалл 5000  №: 2052641  Версия прошивки: v 03.21.17.721":
                passport["chromatograph"],
            "С = 1,0 мг/дм3": passport["sample"],
            "2026-01-21 08:42:56": passport["report_datetime"],
            "Интервал от 0.000 мин до  38.961 мин":
                f"Интервал от 0.000 мин до  {pid1_interval} мин",
            "Интервал от 0.000 мин до  38.959 мин":
                f"Интервал от 0.000 мин до  {pid2_interval} мин",
        }
        for old, new in replacements.items():
            replace_text(root, old, new, all_occurrences=True, required=True)

        set_table_cell(root, 0, 8, 1, passport.get("sample_volume", 2))
        set_table_cell(root, 0, 9, 1, passport.get("dilution", 1))

        row_values = [
            [
                item["component"],
                f'{float(item["retention_time"]):.3f}',
                f'{float(item["area"]):.3f}',
                f'{float(item["height"]):.3f}',
                item["concentration"],
                item.get("unit", "мг/дм3"),
                item["detector"],
            ]
            for item in results
        ]
        total_row = clone_table_rows(
            root,
            table_index=0,
            first_data_row=13,
            original_data_rows=20,
            values=row_values,
            total_row_offset=20,
        )

        totals = [
            "Сумма",
            "",
            f'{sum(float(x["area"]) for x in results):.3f}',
            f'{sum(float(x["height"]) for x in results):.3f}',
            f'{sum(float(x["concentration"]) for x in results):.3f}',
            "",
            "",
        ]
        for cell, value in zip(unique_cells(total_row), totals):
            set_text_preserve_style(cell, value)

    return clone_docx(
        TEMPLATE,
        Path(output_path),
        transform_document=transform,
        media_replacements={
            "word/media/image1.png": Path(pid1_image),
            "word/media/image2.png": Path(pid2_image),
        },
    )


def generate_reports_for_sample(
    sample_dir: Path,
    *,
    operator: str = "Васильева Д.В.",
    chromatograph: str = (
        "Хроматэк-Кристалл 5000  №: 2052641  "
        "Версия прошивки: v 03.21.17.721"
    ),
    sample_volume: int = 2,
    dilution: int = 1,
) -> list[Path]:
    sample_dir = Path(sample_dir)
    package = json.loads(
        (sample_dir / "generation.json").read_text(encoding="utf-8")
    )
    image_index = {
        (int(item["chromatogram_index"]), str(item["detector"])):
            sample_dir / str(item["file"])
        for item in package.get("images", [])
    }
    times = [
        datetime.fromisoformat(value)
        for value in package["chromatogram_times"]
    ]
    peaks = package.get("peaks", [])
    sample_code = str(package["sample_code"])
    created = []

    for index in (1, 2):
        analysis_time = times[index - 1]
        rows = []
        for peak in peaks:
            if int(peak["chromatogram_index"]) != index:
                continue
            concentration = float(peak["input_concentration"])
            if concentration <= 0:
                continue
            rows.append(
                {
                    "component": peak["component"],
                    "retention_time": peak["retention_time_generated"],
                    "area": peak["calculated_area"],
                    "height": peak["calculated_height"],
                    "concentration": _fmt_sig(concentration),
                    "unit": "мг/дм3",
                    "detector": peak["detector"],
                }
            )
        rows.sort(key=lambda row: float(row["retention_time"]))
        if not rows:
            raise ValueError(
                f"В хроматограмме {index} нет ненулевых компонентов"
            )

        number = _next_counter()
        file_time = analysis_time.strftime("%Y-%m-%d %H-%M-%S")
        chromatogram_file = (
            rf"C:\Analytic 3\Projects\МУК 4_1_3166_5\.chromatograms"
            rf"\{file_time} {number:04d}.chrx"
        )
        report_time = analysis_time + timedelta(
            seconds=6540 + ((number * 137) % 1021)
        )
        output = sample_dir / f"Отчёт_ГХ_{sample_code}_{index}.docx"

        generate_gc_report(
            output_path=output,
            passport={
                "operator": operator,
                "chromatogram_number": number,
                "analysis_datetime":
                    analysis_time.strftime("%Y-%m-%d %H:%M:%S"),
                "chromatogram_file": chromatogram_file,
                "chromatograph": chromatograph,
                "sample": sample_code,
                "sample_volume": sample_volume,
                "dilution": dilution,
                "report_datetime":
                    report_time.strftime("%Y-%m-%d %H:%M:%S"),
            },
            results=rows,
            pid1_image=image_index[(index, "ПИД-1")],
            pid2_image=image_index[(index, "ПИД-2")],
        )
        created.append(output)

    return created


def generate_reports_for_batch(
    sample_dirs,
    *,
    operator: str = "Васильева Д.В.",
) -> list[Path]:
    created = []
    for sample_dir in sample_dirs:
        created.extend(
            generate_reports_for_sample(
                Path(sample_dir),
                operator=operator,
            )
        )
    return created
