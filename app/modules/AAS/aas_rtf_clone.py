# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent
APP_ROOT = ROOT.parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from core.rtf_clone_engine import (
    RtfCloneError,
    build_simple_data_rows,
    clone_instrument_report,
    find_data_rows,
    fit_tables_to_page,
    read_rtf,
    replace_all,
    replace_once,
    replace_value_line,
    rtf_escape,
    wrap_cell_text,
    write_rtf,
)

RTF_TEMPLATE_DIR = ROOT / "rtf_templates"
STANDARD_TEMPLATE = RTF_TEMPLATE_DIR / "MGA_STANDARD.rtf"
HG_TEMPLATE = RTF_TEMPLATE_DIR / "MGA_HG.rtf"


def _largest_image(docx_path: Path):
    if not docx_path.exists():
        return None
    with zipfile.ZipFile(docx_path) as z:
        images = [(name, z.read(name)) for name in z.namelist() if name.startswith("word/media/")]
    if not images:
        return None
    name, data = max(images, key=lambda item: len(item[1]))
    ext = Path(name).suffix.lower()
    if ext == ".png":
        return "pngblip", data
    if ext in (".jpg", ".jpeg"):
        return "jpegblip", data
    return None


def _pict_range(source: str):
    start = source.find(r"{\pict")
    if start < 0:
        return None
    depth = 0
    escaped = False
    for i, ch in enumerate(source[start:], start):
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1
    return None


def _replace_chart(source: str, docx_template: Path) -> str:
    image = _largest_image(docx_template)
    pict = _pict_range(source)
    if not image or not pict:
        return source

    blip, data = image
    old = source[pict[0]:pict[1]]
    match = re.match(
        r"(\{\\pict.*?(?:\\pngblip|\\jpegblip|\\emfblip|\\wmetafile\d+).*?\n)",
        old,
        re.S,
    )
    if match:
        prefix = re.sub(
            r"\\(?:pngblip|jpegblip|emfblip|wmetafile\d+)",
            "\\" + blip,
            match.group(1),
        )
    else:
        prefix = "{\\pict\\" + blip + "\n"

    hex_data = data.hex().upper()
    body = "\n".join(hex_data[i:i + 128] for i in range(0, len(hex_data), 128))
    return source[:pict[0]] + prefix + body + "\n}" + source[pict[1]:]


def _old_values(element: str) -> dict:
    if element == "Hg":
        return {
            "element": "Hg",
            "header": "17.06.24 12:55",
            "sample": r"\'d8\'31\'32\'30\'33\'39",
            "cnc": "31950Hg.cnc",
            "volume": "5000.00",
            "integral": "0.102145",
            "mass": "0.102145",
            "conc": "0.495362",
            "avgm": "2506.941800",
            "avgc": "0.501388",
            "sdm": "42.615322",
            "sdc": "0.008523",
            "rel": "1.699893",
        }
    return {
        "element": "Fe",
        "header": "19.11.24 15:30",
        "sample": "0,055",
        "cnc": "31870Fe.cnc",
        "volume": "10.00",
        "integral": "0.168154",
        "mass": "0.168154",
        "conc": "122.097575",
        "avgm": "1233.804880",
        "avgc": "123.380488",
        "sdm": "18.143133",
        "sdc": "1.814313",
        "rel": "1.470503",
    }


def _build_measurement_rows(prototype: str, rows: list[dict], sample: str, element: str, volume: str) -> str:
    sample_rtf = wrap_cell_text(sample, max_chars=12)
    values = []
    for index, row in enumerate(rows, start=1):
        values.append(
            [
                rtf_escape(index),
                sample_rtf,
                rtf_escape(row["action_time"]),
                rtf_escape(element),
                rtf_escape(row["CXm"]),
                rtf_escape(volume),
                rtf_escape(row["C"]),
                rtf_escape(row["CC"]),
            ]
        )
    return build_simple_data_rows(prototype, values)


def generate_rtf_report(
    *,
    element,
    action_time,
    sample,
    mean_c,
    mode,
    method_profile,
    measurements,
    output_dir,
    build_context: Callable,
    load_config: Callable,
    get_profile_override: Callable,
    safe_name: Callable,
    docx_template_dir: Path,
):
    if not 2 <= int(measurements) <= 5:
        raise ValueError("Количество параллельных измерений должно быть от 2 до 5")

    template = HG_TEMPLATE if element == "Hg" else STANDARD_TEMPLATE
    context = build_context(
        element,
        action_time,
        sample,
        mean_c,
        mode,
        method_profile,
        measurements,
    )
    config = load_config(element)
    override = get_profile_override(method_profile, element)

    volume = str(context["v"])
    concentration_file = str(
        override.get("concentration_file")
        or config.get("concentration_file")
        or f"ГОСТ 31870{element}.cnc"
    )
    rows = [
        {
            key: str(context[f"row_{i}.{key}"])
            for key in ("action_time", "C", "CXm", "Ci", "CC")
        }
        for i in range(1, measurements + 1)
    ]

    old = _old_values(element)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    out = output_dir / f"Отчет_{element}_{safe_name(sample)}.rtf"
    if out.exists():
        for number in range(2, 10000):
            candidate = output_dir / f"Отчет_{element}_{safe_name(sample)}_{number}.rtf"
            if not candidate.exists():
                out = candidate
                break

    def row_builder(prototype: str) -> str:
        return _build_measurement_rows(prototype, rows, sample, element, volume)

    source = read_rtf(template)
    source = fit_tables_to_page(source, 9800)
    source = replace_once(source, old["element"], element)
    source = replace_once(source, old["header"], context["action_time"])
    source = replace_all(source, old["sample"], sample)
    source = replace_value_line(source, old["cnc"], concentration_file)
    source = replace_all(source, old["volume"], volume)
    source = replace_once(source, old["integral"], rows[0]["Ci"])
    source = replace_once(source, old["mass"], rows[0]["CXm"])
    source = replace_once(source, old["conc"], rows[0]["C"])

    start, end, prototype = find_data_rows(source)
    source = source[:start] + row_builder(prototype) + source[end:]

    source = replace_once(source, old["avgm"], context["row_avg.M"])
    source = replace_once(source, old["avgc"], context["row_avg.MM"])
    source = replace_once(source, old["sdm"], context["row_avg_abs.M"])
    source = replace_once(source, old["sdc"], context["row_avg_abs.MM"])
    source = replace_all(source, old["rel"], context["row_avg_rel.M"])
    source = _replace_chart(source, docx_template_dir / f"{element}.docx")
    write_rtf(out, source)

    with out.with_suffix(".json").open("w", encoding="utf-8") as file:
        json.dump(context, file, ensure_ascii=False, indent=2)

    return out
