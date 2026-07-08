# -*- coding: utf-8 -*-
"""
Генератор отчетов ААС v3 Excel.
Поддерживает:
- одиночную генерацию;
- массовую генерацию из Excel без внешних зависимостей.

Excel-формат:
  A: Шифр пробы
  B: Дата (необязательно, если задана в окне)
  C...N: элементы Fe, Mn, Cr, Cd, Ba, As, Se, Sb, Pb, Ti, Sn, Hg
  В ячейках элементов указывается средняя концентрация, мкг/л.
  Пустая ячейка = отчет по этому элементу не создается.
"""
import json
import math
import os
import random
import shutil
import statistics
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
except Exception:
    tk = None

ROOT = Path(__file__).resolve().parent
TEMPLATE_DIR = ROOT / "templates"
CONFIG_DIR = ROOT / "configs"
OUTPUT_DIR = ROOT / "output"
ELEMENTS = ["Fe", "Mn", "Cr", "Cd", "Ba", "As", "Se", "Sb", "Pb", "Ti", "Sn", "Hg"]
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
ET.register_namespace("w", W_NS)


def fmt6(x: float) -> str:
    return f"{x:.6f}"


def fmt2(x: float) -> str:
    return f"{x:.2f}"


def load_config(element: str) -> dict:
    element = normalize_element(element)
    path = CONFIG_DIR / f"{element}.json"
    if not path.exists():
        raise FileNotFoundError(f"Не найден конфиг: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def normalize_element(value: str) -> str:
    s = str(value).strip()
    low = s.lower().replace(" ", "")
    aliases = {
        "fe": "Fe", "железо": "Fe",
        "mn": "Mn", "марганец": "Mn",
        "cr": "Cr", "сr": "Cr", "хром": "Cr",  # second key may contain Cyrillic С
        "cd": "Cd", "кадмий": "Cd",
        "ba": "Ba", "барий": "Ba",
        "as": "As", "мышьяк": "As",
        "se": "Se", "селен": "Se",
        "sb": "Sb", "сурьма": "Sb",
        "pb": "Pb", "свинец": "Pb",
        "ti": "Ti", "титан": "Ti",
        "sn": "Sn", "олово": "Sn",
        "hg": "Hg", "ртуть": "Hg",
    }
    return aliases.get(low, s)


# Границы относительной погрешности/неопределенности по присланной таблице ГОСТ.
ACCURACY_LIMITS = {
    "Fe": [(0.04, 0.25, 20)],
    "Mn": [(0.001, 0.05, 20)],
    "Cd": [(0.0001, 0.001, 50), (0.001, 0.01, 25)],
    "Ba": [(0.01, 0.2, 30)],
    "As": [(0.005, 0.02, 50), (0.02, 0.05, 25), (0.05, 0.3, 15)],
    "Cr": [(0.001, 0.01, 40), (0.01, 0.05, 25)],
    "Se": [(0.02, 0.05, 20)],
    "Sb": [(0.005, 0.02, 35)],
    "Pb": [(0.001, 0.01, 40), (0.01, 0.05, 20)],
    "Ti": [(0.1, 0.5, 40)],
    "Sn": [(0.005, 0.02, 40)],
    "Hg": [(0, 999999, 20)],
}


def get_accuracy_limit(element: str, mean_c: float) -> float:
    ranges = ACCURACY_LIMITS.get(element, [])
    for lo, hi, limit in ranges:
        if lo <= mean_c <= hi:
            return float(limit)
    if ranges:
        nearest = min(ranges, key=lambda r: min(abs(mean_c - r[0]), abs(mean_c - r[1])))
        return float(nearest[2])
    return 20.0


def pick_target_rel_cv(element: str, mean_c: float, seed_text: str, mode: str) -> float:
    rnd = random.Random(seed_text + "|cv")
    mode = (mode or "normal").lower()
    if mode in ("precise", "точный", "very_precise"):
        return rnd.uniform(0.01, 0.05)
    if mode in ("rough", "bad", "плохой", "poor"):
        limit = get_accuracy_limit(element, mean_c) / 100.0
        lo = max(0.10, limit * 0.75)
        hi = max(lo, limit)
        return rnd.uniform(lo, hi)
    return rnd.uniform(0.05, 0.10)


def interp_linear(x_values, y_values, x):
    xs = list(map(float, x_values))
    ys = list(map(float, y_values))
    if len(xs) < 2:
        raise ValueError("В конфиге градуировки должно быть минимум 2 точки")
    if x <= xs[0]:
        x0, x1, y0, y1 = xs[0], xs[1], ys[0], ys[1]
    elif x >= xs[-1]:
        x0, x1, y0, y1 = xs[-2], xs[-1], ys[-2], ys[-1]
    else:
        for i in range(len(xs) - 1):
            if xs[i] <= x <= xs[i + 1]:
                x0, x1, y0, y1 = xs[i], xs[i + 1], ys[i], ys[i + 1]
                break
    if x1 == x0:
        return y0
    return y0 + (x - x0) * (y1 - y0) / (x1 - x0)


def generate_three_values(mean_c: float, seed_text: str, mode: str = "normal", element: str = ""):
    rnd = random.Random(seed_text)
    rel_sd = pick_target_rel_cv(element, mean_c, seed_text, mode)
    base = mean_c * rel_sd
    if mean_c - base <= 0:
        base = mean_c * 0.45
    vals = [mean_c - base, mean_c, mean_c + base]
    rnd.shuffle(vals)
    return vals


def build_context(element: str, action_time: str, sn: str, mean_c: float, mode: str = "normal") -> dict:
    element = normalize_element(element)
    cfg = load_config(element)
    v = float(cfg["v"])
    cc_div = float(cfg["ccDivided"])
    seed = f"{element}|{action_time}|{sn}|{mean_c:.9f}|{mode}"
    c_values = generate_three_values(mean_c, seed, mode, element)

    rows = []
    for c in c_values:
        cxm = c * v
        ci = interp_linear(cfg["x"], cfg["y"], cxm)
        cc = c / cc_div
        rows.append({
            "C": fmt6(c),
            "CXm": fmt6(cxm),
            "Ci": fmt6(ci),
            "CC": fmt6(cc),
        })

    masses = [float(r["CXm"]) for r in rows]
    concs = [float(r["C"]) for r in rows]
    avg_m = sum(masses) / 3
    avg_c = sum(concs) / 3
    sd_m = statistics.stdev(masses)
    sd_c = statistics.stdev(concs)
    rel = (sd_c / avg_c * 100) if avg_c else 0

    ctx = {
        "action_time": action_time,
        "sn": sn,
        "v": fmt2(v),
        "result": mean_c,
        "row_1.C": rows[0]["C"],
        "row_1.CXm": rows[0]["CXm"],
        "row_1.Ci": rows[0]["Ci"],
        "row_1.CC": rows[0]["CC"],
        "row_2.C": rows[1]["C"],
        "row_2.CXm": rows[1]["CXm"],
        "row_2.Ci": rows[1]["Ci"],
        "row_2.CC": rows[1]["CC"],
        "row_3.C": rows[2]["C"],
        "row_3.CXm": rows[2]["CXm"],
        "row_3.Ci": rows[2]["Ci"],
        "row_3.CC": rows[2]["CC"],
        "row_avg.M": fmt6(avg_m),
        "row_avg.MM": fmt6(avg_c),
        "row_avg_abs.M": fmt6(sd_m),
        "row_avg_abs.MM": fmt6(sd_c),
        "row_avg_rel.M": fmt6(rel),
        "row_avg_rel.MM": fmt6(rel),
    }
    return ctx


def _placeholder_patterns(context: dict):
    patterns = []
    for key in sorted(context.keys(), key=len, reverse=True):
        value = str(context[key])
        patterns.append(("{{ " + key + " }}", key, value))
        patterns.append(("{{" + key + "}}", key, value))
        if "." in key:
            a, b = key.split(".", 1)
            patterns.append(("{{" + a + ". " + b + "}}", key, value))
            patterns.append(("{{ " + a + ". " + b + " }}", key, value))
            if b == "CXm":
                patterns.append(("{{" + a + ".C Xm}}", key, value))
                patterns.append(("{{ " + a + ".C Xm }}", key, value))
        if key.endswith(".MM"):
            a = key[:-3]
            patterns.append(("{{" + a + ". MM}}", key, value))
            patterns.append(("{{ " + a + ". MM }}", key, value))
    return patterns


def _replace_span_in_text_nodes(text_nodes, start: int, end: int, repl: str):
    positions = []
    pos = 0
    for node in text_nodes:
        txt = node.text or ""
        positions.append((node, pos, pos + len(txt)))
        pos += len(txt)
    affected = [(node, a, b) for node, a, b in positions if b > start and a < end]
    if not affected:
        return
    first, fa, fb = affected[0]
    last, la, lb = affected[-1]
    first_txt = first.text or ""
    prefix = first_txt[:max(0, start - fa)]
    if first is last:
        suffix = first_txt[max(0, end - fa):]
        first.text = prefix + repl + suffix
    else:
        last_txt = last.text or ""
        suffix = last_txt[max(0, end - la):]
        first.text = prefix + repl
        for node, _, _ in affected[1:-1]:
            node.text = ""
        last.text = suffix


def replace_paragraph_placeholders(p, context: dict, state: dict):
    t_tag = f"{{{W_NS}}}t"
    text_nodes = [el for el in p.iter(t_tag)]
    if not text_nodes:
        return
    while True:
        full = "".join(el.text or "" for el in text_nodes)
        best = None
        for pat, key, value in _placeholder_patterns(context):
            idx = full.find(pat)
            if idx >= 0 and (best is None or idx < best[0] or (idx == best[0] and len(pat) > len(best[1]))):
                best = (idx, pat, key, value)
        if best is None:
            break
        idx, pat, key, value = best
        if key == "row_2.CXm":
            state["row2_cxm_count"] = state.get("row2_cxm_count", 0) + 1
            if state["row2_cxm_count"] >= 2 and "row_3.CXm" in context:
                value = str(context["row_3.CXm"])
        _replace_span_in_text_nodes(text_nodes, idx, idx + len(pat), value)


def replace_in_xml(xml_bytes: bytes, context: dict) -> bytes:
    root = ET.fromstring(xml_bytes)
    state = {}
    for p in root.iter(f"{{{W_NS}}}p"):
        replace_paragraph_placeholders(p, context, state)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def fill_docx(template_path: Path, out_path: Path, context: dict):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        with zipfile.ZipFile(template_path, "r") as zin:
            zin.extractall(tmp)
        for rel in ["word/document.xml", "word/header1.xml", "word/footer1.xml"]:
            p = tmp / rel
            if p.exists():
                p.write_bytes(replace_in_xml(p.read_bytes(), context))
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zout:
            for file in tmp.rglob("*"):
                if file.is_file():
                    zout.write(file, file.relative_to(tmp).as_posix())


def safe_name(s: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(s))


def generate_report(element: str, action_time: str, sn: str, mean_c: float, mode: str = "normal", output_dir: Path = OUTPUT_DIR) -> Path:
    element = normalize_element(element)
    template = TEMPLATE_DIR / f"{element}.docx"
    if not template.exists():
        raise FileNotFoundError(f"Не найден шаблон: {template}")
    ctx = build_context(element, action_time, sn, mean_c, mode)
    safe_sn = safe_name(sn)
    out = output_dir / f"Отчет_{element}_{safe_sn}.docx"
    # Если такой отчет уже есть, добавляем номер, чтобы не перезаписать.
    if out.exists():
        for i in range(2, 10000):
            candidate = output_dir / f"Отчет_{element}_{safe_sn}_{i}.docx"
            if not candidate.exists():
                out = candidate
                break
    fill_docx(template, out, ctx)
    json_out = out.with_suffix(".json")
    with json_out.open("w", encoding="utf-8") as f:
        json.dump(ctx, f, ensure_ascii=False, indent=2)
    return out

# ---------------- Excel reader without external dependencies ----------------
SS_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _col_to_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    n = 0
    for ch in letters.upper():
        n = n * 26 + (ord(ch) - ord('A') + 1)
    return n - 1


def _parse_shared_strings(z: zipfile.ZipFile):
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    out = []
    for si in root.findall(f"{{{SS_NS}}}si"):
        texts = []
        for t in si.iter(f"{{{SS_NS}}}t"):
            texts.append(t.text or "")
        out.append("".join(texts))
    return out


def _first_sheet_path(z: zipfile.ZipFile):
    # Для наших шаблонов достаточно sheet1.xml. Но если есть workbook rels, используем первую вкладку.
    if "xl/worksheets/sheet1.xml" in z.namelist():
        return "xl/worksheets/sheet1.xml"
    for name in z.namelist():
        if name.startswith("xl/worksheets/sheet") and name.endswith(".xml"):
            return name
    raise ValueError("В Excel не найден лист")


def read_xlsx_rows(path: Path):
    with zipfile.ZipFile(path, "r") as z:
        shared = _parse_shared_strings(z)
        sheet_path = _first_sheet_path(z)
        root = ET.fromstring(z.read(sheet_path))
        rows = []
        for row in root.iter(f"{{{SS_NS}}}row"):
            values = {}
            max_col = -1
            for c in row.findall(f"{{{SS_NS}}}c"):
                ref = c.attrib.get("r", "A1")
                col = _col_to_index(ref)
                max_col = max(max_col, col)
                typ = c.attrib.get("t")
                v_el = c.find(f"{{{SS_NS}}}v")
                is_el = c.find(f"{{{SS_NS}}}is")
                val = ""
                if typ == "s" and v_el is not None:
                    idx = int(v_el.text or 0)
                    val = shared[idx] if 0 <= idx < len(shared) else ""
                elif typ == "inlineStr" and is_el is not None:
                    val = "".join(t.text or "" for t in is_el.iter(f"{{{SS_NS}}}t"))
                elif v_el is not None:
                    val = v_el.text or ""
                values[col] = val
            if max_col >= 0:
                rows.append([values.get(i, "") for i in range(max_col + 1)])
        return rows


def parse_excel_batch(xlsx_path: Path, default_date: str):
    rows = read_xlsx_rows(xlsx_path)
    if not rows:
        return []
    headers = [str(x).strip() for x in rows[0]]
    if not headers:
        return []
    # header aliases
    sn_idx = None
    date_idx = None
    element_cols = []
    for i, h in enumerate(headers):
        h_clean = h.strip()
        h_low = h_clean.lower().replace(" ", "")
        if h_low in ["шифр", "шифрпробы", "образец", "названиепробы", "sample", "sampleid"]:
            sn_idx = i
        elif h_low in ["дата", "date", "action_time", "actiontime"]:
            date_idx = i
        else:
            el = normalize_element(h_clean)
            if el in ELEMENTS:
                element_cols.append((i, el))
    if sn_idx is None:
        raise ValueError("В Excel должен быть столбец 'Шифр пробы'")
    if not element_cols:
        raise ValueError("В Excel не найдены столбцы элементов: Fe, Mn, Cr, Cd, Ba, As, Se, Sb, Pb, Ti, Sn, Hg")

    tasks = []
    for rnum, row in enumerate(rows[1:], start=2):
        if sn_idx >= len(row):
            continue
        sn = str(row[sn_idx]).strip()
        if not sn:
            continue
        action_time = default_date
        if date_idx is not None and date_idx < len(row) and str(row[date_idx]).strip():
            action_time = str(row[date_idx]).strip()
        for col_idx, el in element_cols:
            if col_idx >= len(row):
                continue
            raw = str(row[col_idx]).strip().replace(",", ".")
            if raw == "":
                continue
            try:
                mean_c = float(raw)
            except ValueError:
                raise ValueError(f"Некорректная концентрация в строке {rnum}, столбец {headers[col_idx]}: {row[col_idx]}")
            tasks.append({"row": rnum, "sn": sn, "action_time": action_time, "element": el, "mean_c": mean_c})
    return tasks


def generate_from_excel(xlsx_path: Path, default_date: str, mode: str = "normal", output_dir: Path = OUTPUT_DIR):
    tasks = parse_excel_batch(xlsx_path, default_date)
    if not tasks:
        raise ValueError("В Excel не найдено ни одного заполненного результата")
    batch_dir = output_dir / ("AAS_batch_" + Path(xlsx_path).stem)
    batch_dir.mkdir(parents=True, exist_ok=True)
    created = []
    log = []
    for t in tasks:
        out = generate_report(t["element"], t["action_time"], t["sn"], t["mean_c"], mode, batch_dir)
        created.append(out)
        log.append({**t, "file": str(out.name)})
    with (batch_dir / "generation_log.json").open("w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    return created, batch_dir


class App:
    def __init__(self, root):
        self.root = root
        root.title("Генератор отчетов ААС v3 Excel")
        root.geometry("560x430")
        frm = ttk.Frame(root, padding=16)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Одиночный отчет", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
        ttk.Label(frm, text="Элемент").grid(row=1, column=0, sticky="w", pady=4)
        self.element = tk.StringVar(value="Fe")
        ttk.Combobox(frm, textvariable=self.element, values=ELEMENTS, state="readonly", width=18).grid(row=1, column=1, sticky="ew", pady=4)

        ttk.Label(frm, text="Дата").grid(row=2, column=0, sticky="w", pady=4)
        self.action_time = tk.StringVar(value="07.07.2026")
        ttk.Entry(frm, textvariable=self.action_time, width=25).grid(row=2, column=1, sticky="ew", pady=4)

        ttk.Label(frm, text="Шифр пробы").grid(row=3, column=0, sticky="w", pady=4)
        self.sn = tk.StringVar(value="ИТС-ПБ-26-000001")
        ttk.Entry(frm, textvariable=self.sn, width=25).grid(row=3, column=1, sticky="ew", pady=4)

        ttk.Label(frm, text="Средняя концентрация, мкг/л").grid(row=4, column=0, sticky="w", pady=4)
        self.mean_c = tk.StringVar(value="0.529780")
        ttk.Entry(frm, textvariable=self.mean_c, width=25).grid(row=4, column=1, sticky="ew", pady=4)

        ttk.Label(frm, text="Режим СКО").grid(row=5, column=0, sticky="w", pady=4)
        self.mode = tk.StringVar(value="normal")
        ttk.Combobox(frm, textvariable=self.mode, values=["precise", "normal", "rough"], state="readonly", width=18).grid(row=5, column=1, sticky="ew", pady=4)

        ttk.Button(frm, text="Сформировать одиночный Word-отчет", command=self.run_single).grid(row=6, column=0, columnspan=3, pady=(10, 18), sticky="ew")

        ttk.Separator(frm).grid(row=7, column=0, columnspan=3, sticky="ew", pady=6)
        ttk.Label(frm, text="Массовая генерация из Excel", font=("Segoe UI", 10, "bold")).grid(row=8, column=0, columnspan=3, sticky="w", pady=(8, 6))

        ttk.Label(frm, text="Excel-файл").grid(row=9, column=0, sticky="w", pady=4)
        self.excel_path = tk.StringVar(value="")
        ttk.Entry(frm, textvariable=self.excel_path).grid(row=9, column=1, sticky="ew", pady=4)
        ttk.Button(frm, text="Выбрать", command=self.pick_excel).grid(row=9, column=2, sticky="ew", padx=(8, 0), pady=4)

        ttk.Button(frm, text="Сгенерировать серию из Excel", command=self.run_excel).grid(row=10, column=0, columnspan=3, pady=12, sticky="ew")
        ttk.Button(frm, text="Открыть папку output", command=self.open_output).grid(row=11, column=0, columnspan=3, sticky="ew")

        self.status = tk.StringVar(value="")
        ttk.Label(frm, textvariable=self.status, wraplength=520).grid(row=12, column=0, columnspan=3, sticky="w", pady=(12, 0))
        frm.columnconfigure(1, weight=1)

    def pick_excel(self):
        p = filedialog.askopenfilename(title="Выберите Excel", filetypes=[("Excel files", "*.xlsx")])
        if p:
            self.excel_path.set(p)

    def run_single(self):
        try:
            mean = float(self.mean_c.get().replace(",", "."))
            out = generate_report(self.element.get(), self.action_time.get().strip(), self.sn.get().strip(), mean, self.mode.get())
            self.status.set(f"Готово: {out}")
            messagebox.showinfo("Готово", f"Отчет сохранен:\n{out}")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def run_excel(self):
        try:
            p = Path(self.excel_path.get().strip())
            if not p.exists():
                raise FileNotFoundError("Выберите Excel-файл")
            created, batch_dir = generate_from_excel(p, self.action_time.get().strip(), self.mode.get())
            self.status.set(f"Готово: создано {len(created)} отчетов. Папка: {batch_dir}")
            messagebox.showinfo("Готово", f"Создано отчетов: {len(created)}\nПапка:\n{batch_dir}")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def open_output(self):
        OUTPUT_DIR.mkdir(exist_ok=True)
        try:
            os.startfile(str(OUTPUT_DIR))
        except Exception:
            self.status.set(str(OUTPUT_DIR))


def main():
    # CLI одиночный: python aas_report_generator.py Fe 07.07.2026 SAMPLE 0.529780 [mode]
    if len(sys.argv) >= 5 and sys.argv[1] != "--excel":
        element, action_time, sn, mean = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4].replace(",", "."))
        mode = sys.argv[5] if len(sys.argv) >= 6 else "normal"
        print(generate_report(element, action_time, sn, mean, mode))
        return
    # CLI Excel: python aas_report_generator.py --excel input.xlsx 07.07.2026 normal
    if len(sys.argv) >= 3 and sys.argv[1] == "--excel":
        xlsx = Path(sys.argv[2])
        default_date = sys.argv[3] if len(sys.argv) >= 4 else "07.07.2026"
        mode = sys.argv[4] if len(sys.argv) >= 5 else "normal"
        created, batch_dir = generate_from_excel(xlsx, default_date, mode)
        print(f"Создано отчетов: {len(created)}")
        print(batch_dir)
        return
    if tk is None:
        print("Tkinter недоступен.")
        print("Одиночный запуск: python aas_report_generator.py Fe 07.07.2026 SAMPLE 0.529780")
        print("Excel-запуск: python aas_report_generator.py --excel AAS_template.xlsx 07.07.2026 normal")
        return
    OUTPUT_DIR.mkdir(exist_ok=True)
    root = tk.Tk()
    try:
        root.attributes("-topmost", True)
        root.after(1000, lambda: root.attributes("-topmost", False))
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
