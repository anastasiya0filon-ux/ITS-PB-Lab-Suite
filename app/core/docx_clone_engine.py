# -*- coding: utf-8 -*-
"""Общий движок клонирования приборных DOCX без внешних библиотек."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Callable, Mapping, Sequence
from xml.etree import ElementTree as ET
import os
import zipfile

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = {"w": W_NS, "r": R_NS}
ET.register_namespace("w", W_NS)
ET.register_namespace("r", R_NS)


class DocxCloneError(RuntimeError):
    pass


def text_of(element: ET.Element) -> str:
    return "".join(node.text or "" for node in element.findall(".//w:t", NS))


def set_text_preserve_style(container: ET.Element, value: object) -> None:
    nodes = container.findall(".//w:t", NS)
    if not nodes:
        paragraph = container.find(".//w:p", NS)
        if paragraph is None:
            paragraph = ET.SubElement(container, f"{{{W_NS}}}p")
        run = paragraph.find("./w:r", NS)
        if run is None:
            run = ET.SubElement(paragraph, f"{{{W_NS}}}r")
        node = ET.SubElement(run, f"{{{W_NS}}}t")
        nodes = [node]
    nodes[0].text = str(value)
    for node in nodes[1:]:
        node.text = ""


def unique_cells(row: ET.Element) -> list[ET.Element]:
    return list(row.findall("./w:tc", NS))


def replace_text(
    root: ET.Element,
    old: str,
    new: object,
    *,
    all_occurrences: bool = True,
    required: bool = True,
) -> int:
    count = 0
    for paragraph in root.findall(".//w:p", NS):
        full = text_of(paragraph)
        if old not in full:
            continue
        replacement = (
            full.replace(old, str(new))
            if all_occurrences
            else full.replace(old, str(new), 1)
        )
        set_text_preserve_style(paragraph, replacement)
        count += full.count(old) if all_occurrences else 1
        if not all_occurrences:
            break
    if required and count == 0:
        raise DocxCloneError(f"В DOCX не найдено значение: {old!r}")
    return count


def set_table_cell(
    root: ET.Element,
    table_index: int,
    row_index: int,
    cell_index: int,
    value: object,
) -> None:
    tables = root.findall(".//w:tbl", NS)
    try:
        row = tables[table_index].findall("./w:tr", NS)[row_index]
        cell = unique_cells(row)[cell_index]
    except IndexError as exc:
        raise DocxCloneError(
            f"Нет ячейки table={table_index}, row={row_index}, cell={cell_index}"
        ) from exc
    set_text_preserve_style(cell, value)


def clone_table_rows(
    root: ET.Element,
    *,
    table_index: int,
    first_data_row: int,
    original_data_rows: int,
    values: Sequence[Sequence[object]],
    total_row_offset: int,
) -> ET.Element:
    table = root.findall(".//w:tbl", NS)[table_index]
    rows = table.findall("./w:tr", NS)
    if not values:
        raise DocxCloneError("Пустая таблица результатов")
    prototype = deepcopy(rows[first_data_row])
    total_row = rows[first_data_row + total_row_offset]

    if len(values) < original_data_rows:
        for index in range(
            first_data_row + original_data_rows - 1,
            first_data_row + len(values) - 1,
            -1,
        ):
            table.remove(table.findall("./w:tr", NS)[index])
    elif len(values) > original_data_rows:
        insert_at = list(table).index(total_row)
        for _ in range(len(values) - original_data_rows):
            table.insert(insert_at, deepcopy(prototype))
            insert_at += 1

    rows = table.findall("./w:tr", NS)
    for offset, row_values in enumerate(values):
        cells = unique_cells(rows[first_data_row + offset])
        if len(cells) != len(row_values):
            raise DocxCloneError(
                f"Строка содержит {len(cells)} ячеек вместо {len(row_values)}"
            )
        for cell, value in zip(cells, row_values):
            set_text_preserve_style(cell, value)

    return table.findall("./w:tr", NS)[first_data_row + len(values)]


def clone_docx(
    template_path: Path,
    output_path: Path,
    *,
    transform_document: Callable[[ET.Element], None] | None = None,
    media_replacements: Mapping[str, Path | bytes] | None = None,
) -> Path:
    template_path = Path(template_path)
    output_path = Path(output_path)

    with zipfile.ZipFile(template_path, "r") as source_zip:
        members = {name: source_zip.read(name) for name in source_zip.namelist()}

    root = ET.fromstring(members["word/document.xml"])
    if transform_document is not None:
        transform_document(root)
    members["word/document.xml"] = ET.tostring(
        root, encoding="utf-8", xml_declaration=True
    )

    for name, replacement in (media_replacements or {}).items():
        data = replacement if isinstance(replacement, bytes) else Path(replacement).read_bytes()
        if name not in members:
            raise DocxCloneError(f"В шаблоне отсутствует {name}")
        members[name] = data

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as target_zip:
        for name, data in members.items():
            target_zip.writestr(name, data)
    os.replace(temporary, output_path)
    return output_path
