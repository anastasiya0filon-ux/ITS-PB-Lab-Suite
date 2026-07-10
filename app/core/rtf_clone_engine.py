# -*- coding: utf-8 -*-
"""Универсальный движок клонирования приборных RTF-документов.

Принцип:
- исходный RTF используется как неизменяемый эталон;
- оформление, таблицы, границы, шрифты и графика не создаются заново;
- меняются только значения;
- длинные значения переносятся внутри существующей ячейки;
- широкие таблицы при необходимости вписываются в печатную область
  изменением только координат cellx, без перестройки строк.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Mapping, Sequence


class RtfCloneError(RuntimeError):
    pass


def rtf_escape(value: object, encoding: str = "cp1251") -> str:
    out: list[str] = []
    for ch in str(value):
        if ch in "\\{}":
            out.append("\\" + ch)
            continue
        code = ord(ch)
        if 32 <= code <= 126:
            out.append(ch)
            continue
        try:
            raw = ch.encode(encoding)
        except UnicodeEncodeError:
            out.append(r"\u%d?" % (code if code < 32768 else code - 65536))
        else:
            out.extend(r"\'%02x" % b for b in raw)
    return "".join(out)


def read_rtf(path: Path, encoding: str = "cp1251") -> str:
    if not path.exists():
        raise FileNotFoundError(path)
    return path.read_bytes().decode(encoding)


def write_rtf(path: Path, source: str, encoding: str = "cp1251") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(source.encode(encoding))
    return path


def replace_once(source: str, old: str, new: object, *, required: bool = True) -> str:
    pos = source.find(old)
    if pos < 0:
        if required:
            raise RtfCloneError(f"В RTF не найдено эталонное значение: {old!r}")
        return source
    encoded = rtf_escape(new)
    return source[:pos] + encoded + source[pos + len(old):]


def replace_all(source: str, old: str, new: object, *, required: bool = False) -> str:
    if old not in source:
        if required:
            raise RtfCloneError(f"В RTF не найдено эталонное значение: {old!r}")
        return source
    return source.replace(old, rtf_escape(new))


def replace_value_line(source: str, anchor_tail: str, new_value: object) -> str:
    """Заменяет значение справа от ': ' до ближайшего '\\par'."""
    idx = source.find(anchor_tail)
    if idx < 0:
        raise RtfCloneError(f"Не найдено эталонное значение: {anchor_tail}")
    start = source.rfind(": ", 0, idx)
    end = source.find(r"\par", idx)
    if start < 0 or end < 0:
        raise RtfCloneError(f"Не удалось определить границы поля: {anchor_tail}")
    start += 2
    return source[:start] + rtf_escape(new_value) + source[end:]


def wrap_cell_text(value: object, max_chars: int = 12) -> str:
    """Переносит длинное значение внутри текущей ячейки, предпочтительно по дефисам."""
    text = str(value).strip()
    if len(text) <= max_chars:
        return rtf_escape(text)

    parts = text.split("-")
    lines: list[str] = []
    current = ""
    for part in parts:
        candidate = part if not current else f"{current}-{part}"
        if current and len(candidate) > max_chars:
            lines.append(current)
            current = part
        else:
            current = candidate
    if current:
        lines.append(current)

    if len(lines) == 1:
        lines = [text[i:i + max_chars] for i in range(0, len(text), max_chars)]

    return r"\line ".join(rtf_escape(line) for line in lines)


def find_data_rows(
    source: str,
    first_row_pattern: str = r"\\intbl 1\\cell .*?\\cell\\row\r?\n",
    second_row_pattern: str = r"\\intbl 2\\cell .*?\\cell\\row\r?\n",
) -> tuple[int, int, str]:
    row1 = re.search(first_row_pattern, source)
    if not row1:
        raise RtfCloneError("Не найдена первая строка таблицы результатов")
    row2 = re.search(second_row_pattern, source[row1.end():])
    if not row2:
        raise RtfCloneError("Не найдена вторая строка таблицы результатов")
    return row1.start(), row1.end() + row2.end(), row1.group(0)


def build_simple_data_rows(
    prototype: str,
    row_values: Sequence[Sequence[str]],
) -> str:
    """Создает валидные строки с той же RTF-структурой данных.

    Применяется только к строкам, где исходная структура представлена
    последовательностью \\intbl ... \\cell ... \\row.
    """
    newline = "\r\n" if prototype.endswith("\r\n") else "\n"
    out: list[str] = []
    for values in row_values:
        out.append(
            r"\intbl "
            + r"\cell ".join(values)
            + r"\cell\row"
            + newline
        )
    return "".join(out)


def fit_tables_to_page(source: str, right_edge: int = 9800) -> str:
    """Вписывает широкие таблицы в печатную область.

    Меняются только координаты cellx в определении строк.
    Содержимое, границы, шрифты и управляющие слова строк не перестраиваются.
    """
    pattern = re.compile(r"(\\trowd.*?\\pard\\intbl)", re.S)

    def _fit(match: re.Match[str]) -> str:
        block = match.group(1)
        coords = [int(v) for v in re.findall(r"\\cellx(\d+)", block)]
        if not coords or coords[-1] <= right_edge:
            return block

        scale = right_edge / coords[-1]
        scaled: list[int] = []
        previous = 0
        for coord in coords:
            value = max(previous + 220, int(round(coord * scale)))
            scaled.append(value)
            previous = value
        scaled[-1] = right_edge

        iterator = iter(scaled)
        fitted = re.sub(r"\\cellx\d+", lambda _: rf"\cellx{next(iterator)}", block)
        if r"\trautofit0" not in fitted:
            fitted = fitted.replace(r"\trowd", r"\trowd\trautofit0", 1)
        return fitted

    return pattern.sub(_fit, source)


def clone_instrument_report(
    template_path: Path,
    output_path: Path,
    *,
    literal_once: Mapping[str, object] | None = None,
    literal_all: Mapping[str, object] | None = None,
    value_lines: Mapping[str, object] | None = None,
    row_builder=None,
    fit_right_edge: int | None = 9800,
    encoding: str = "cp1251",
) -> Path:
    """Общий конвейер клонирования приборного RTF."""
    source = read_rtf(template_path, encoding)

    if fit_right_edge is not None:
        source = fit_tables_to_page(source, fit_right_edge)

    for old, new in (literal_once or {}).items():
        source = replace_once(source, old, new)

    for old, new in (literal_all or {}).items():
        source = replace_all(source, old, new)

    for anchor, new in (value_lines or {}).items():
        source = replace_value_line(source, anchor, new)

    if row_builder is not None:
        start, end, prototype = find_data_rows(source)
        source = source[:start] + row_builder(prototype) + source[end:]

    return write_rtf(output_path, source, encoding)
