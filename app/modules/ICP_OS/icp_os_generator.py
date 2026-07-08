# -*- coding: utf-8 -*-
"""ICP OS generator for IL ITS-PB.
No external Python packages required.
Reads Excel .xlsx via stdlib, fills DOCX template via OOXML.
"""
import copy
import datetime as _dt
import os
import random
import re
import sys
import traceback
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
except Exception:
    tk = None

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = BASE_DIR / "template.docx"
OUTPUT_DIR = BASE_DIR / "output"
LOG_PATH = BASE_DIR / "generation_log.txt"

OPERATORS = ["Зуева А.С.", "Королев А.И.", "Васильева Д.В.", "Тарабанова А.А."]

# Element configs. User-facing result is mg/kg. conc_1/conc_3 are mg/L, conc_2/conc_4 are mg/kg.
ELEMENTS = {
    "Pb": {"ru":"Свинец", "id":102, "name":"Pb220.353", "v":0.05, "m":0.001, "a":3118.2990, "b":70673.619, "round_result":4},
    "Cr": {"ru":"Хром", "id":105, "name":"Cr205.552", "v":0.05, "m":0.001, "a":7203.1949, "b":314383.21, "round_result":4},
    "Ni": {"ru":"Никель", "id":100, "name":"Ni231.604", "v":0.05, "m":0.001, "a":15547.223, "b":440200.38, "round_result":3},
    "Co": {"ru":"Кобальт", "id":527, "name":"Co228.615", "v":0.05, "m":0.001, "a":17901.233, "b":575168.45, "round_result":3},
    "Cu": {"ru":"Медь", "id":101, "name":"Cu324.754", "v":0.05, "m":0.001, "a":54744.778, "b":1043424.8, "round_result":3},
    "As": {"ru":"Мышьяк", "id":108, "name":"As188.979", "v":0.05, "m":0.001, "a":8830.6775, "b":314699.41, "round_result":5},
    "Sn": {"ru":"Олово", "id":109, "name":"Sn235.484", "v":0.05, "m":0.005, "a":8830.6775, "b":314699.41, "round_result":3},
    "Se": {"ru":"Селен", "id":110, "name":"Se196.028", "v":0.05, "m":0.001, "a":8830.6775, "b":314699.41, "round_result":4},
    "Sb": {"ru":"Сурьма", "id":111, "name":"Sb206.833", "v":0.05, "m":0.001, "a":8830.6775, "b":314699.41, "round_result":3},
    "Ba": {"ru":"Барий", "id":112, "name":"Ba455.403", "v":0.05, "m":0.001, "a":37398.779, "b":416532.79, "round_result":3},
    "Al": {"ru":"Алюминий", "id":113, "name":"Al396.152", "v":0.05, "m":0.005, "a":3941.1187, "b":545337.79, "c":0.0044294, "round_result":4},
    "Fe": {"ru":"Железо", "id":114, "name":"Fe238.204", "v":0.05, "m":0.005, "a":50986.208, "b":1310702.0, "round_result":2},
    "Zn": {"ru":"Цинк", "id":115, "name":"Zn206.200", "v":0.05, "m":0.005, "a":22568.344, "b":534298.68, "round_result":2},
    # Corrected Mn config from user, characteristic line Mn257.610 and nonlinear equation.
    "Mn": {"ru":"Марганец", "id":116, "name":"Mn257.610", "v":0.05, "m":0.005, "a":16668.322, "b":7417253.9, "c":0.0144066, "round_result":4},
    # Cd special intensity constants as provided.
    "Cd": {"ru":"Кадмий", "id":117, "name":"Cd214.441", "v":0.05, "m":0.001, "a":-1917.897, "b":1290747.7, "c":0.01232, "round_result":5, "int_const_1":4856, "int_const_2":3562},
    "Ag": {"ru":"Серебро", "id":118, "name":"Ag328.068", "v":0.05, "m":0.005, "a":30300.906, "b":1066774.2, "round_result":4},
}
ELEMENT_ORDER = ["Pb","Cr","Ni","Co","Cu","As","Sn","Se","Sb","Ba","Al","Fe","Zn","Mn","Cd","Ag"]

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
ET.register_namespace('w', W_NS)


def _round_half_up(value, decimals=0):
    """Round like instrument printouts: ordinary mathematical half-up rounding."""
    from decimal import Decimal, ROUND_HALF_UP
    q = Decimal('1') if int(decimals) == 0 else Decimal('1').scaleb(-int(decimals))
    return Decimal(str(value)).quantize(q, rounding=ROUND_HALF_UP)


def fmt_sig(value, digits=4):
    """Instrument-style concentration/result printing for ICP OS.

    Agreed DOC-002 rule:
    - values below 1 are printed with exactly 4 digits after the decimal point;
    - values from 1 to 999.9 keep 4 visible significant digits by reducing
      decimal places as the integer part grows;
    - values >= 1000 are printed as the first 4 significant digits, rounded by
      the next digit, without restoring the removed order digits.

    Examples:
    0.031 -> 0.0310
    0.21 -> 0.2100
    0.00362 -> 0.0036
    1.23665 -> 1.237
    26791 -> 2679
    26795 -> 2680
    267918 -> 2679
    """
    if value is None:
        return ''
    x = float(value)
    sign = '-' if x < 0 else ''
    ax = abs(x)
    digits = int(digits)
    if ax == 0:
        return '0.' + ('0' * digits)
    if ax < 1:
        return f"{_round_half_up(x, digits):.{digits}f}"
    integer_digits = len(str(int(ax)))
    if integer_digits <= digits:
        decimals = max(digits - integer_digits, 0)
        return f"{_round_half_up(x, decimals):.{decimals}f}"
    scale = 10 ** (integer_digits - digits)
    short = int(_round_half_up(ax / scale, 0))
    return sign + str(short)

def fmt_float(value, decimals=4):
    return f"{float(value):.{decimals}f}"


def parse_float(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(',', '.')
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def normalize_placeholder_text(text):
    # Convert {{ item.c\nonce_1 }} -> {{item.conc_1}} and {%tr for item...%} -> {%trforiteminjson_properties%}
    def repl_brace(m):
        inner = re.sub(r"\s+", "", m.group(1))
        return "{{" + inner + "}}"
    text = re.sub(r"\{\{\s*(.*?)\s*\}\}", repl_brace, text, flags=re.S)
    text = re.sub(r"\{%\s*tr\s+for\s+item\s+in\s+json_properties\s*%\}", "{%trforiteminjson_properties%}", text, flags=re.S)
    text = re.sub(r"\{%\s*tr\s+endfor\s*%\}", "{%trendfor%}", text, flags=re.S)
    return text


def text_of_element(el):
    parts = []
    for t in el.findall('.//{%s}t' % W_NS):
        parts.append(t.text or '')
    return ''.join(parts)


def replace_text_in_element(el, mapping, positions=None):
    """Replace placeholders within one paragraph/cell/row. positions: list consumed for {{position}} occurrences."""
    ts = el.findall('.//{%s}t' % W_NS)
    if not ts:
        return
    raw = ''.join(t.text or '' for t in ts)
    norm = normalize_placeholder_text(raw)
    if "{{" not in norm and "{%" not in norm:
        return
    s = norm

    # Replace positions sequentially, because first and second blocks must differ.
    if positions is not None:
        while "{{position}}" in s and positions:
            s = s.replace("{{position}}", str(positions.pop(0)), 1)
        while "{{position}}" in s:
            s = s.replace("{{position}}", str(random.randint(1, 105)), 1)

    # Handle action_t or action_time collapsed form.
    if "{{action_toraction_time}}" in s:
        s = s.replace("{{action_toraction_time}}", mapping.get("action_t", mapping.get("action_time", "")))

    for key, val in mapping.items():
        s = s.replace("{{" + key + "}}", str(val))
    # The template has no text for row control markers after processing; blank them if left.
    s = s.replace("{%trforiteminjson_properties%}", "").replace("{%trendfor%}", "")

    ts[0].text = s
    for t in ts[1:]:
        t.text = ""


def replace_item_placeholders(row_el, item):
    ts = row_el.findall('.//{%s}t' % W_NS)
    for parent in row_el.findall('.//{%s}p' % W_NS):
        replace_text_in_element(parent, {f"item.{k}": v for k, v in item.items()})
    # fallback whole row if some placeholders remain across cells
    replace_text_in_element(row_el, {f"item.{k}": v for k, v in item.items()})


def clear_paragraph_runs(p):
    for child in list(p):
        # Keep paragraph properties only.
        if child.tag != '{%s}pPr' % W_NS:
            p.remove(child)


def make_run(text=None, italic=False, tab=False, size='18'):
    r = ET.Element('{%s}r' % W_NS)
    rPr = ET.SubElement(r, '{%s}rPr' % W_NS)
    if italic:
        ET.SubElement(rPr, '{%s}i' % W_NS)
    sz = ET.SubElement(rPr, '{%s}sz' % W_NS); sz.set('{%s}val' % W_NS, str(size))
    lang = ET.SubElement(rPr, '{%s}lang' % W_NS); lang.set('{%s}val' % W_NS, 'ru-RU')
    if tab:
        ET.SubElement(r, '{%s}tab' % W_NS)
    if text is not None:
        t = ET.SubElement(r, '{%s}t' % W_NS)
        if text.startswith(' ') or text.endswith(' '):
            t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
        t.text = text
    return r


def repair_operator_line(root, lab_employee):
    """Restore List&Label-like operator line after placeholder replacement.

    The placeholder can be split into several Word runs. A naive replacement collapses
    the tab after `Оператор:` and makes the output visually differ from the device
    report. This function reconstructs the line as: italic label, tab, regular value.
    """
    for p in root.findall('.//{%s}p' % W_NS):
        txt = text_of_element(p).strip()
        if txt == f'Оператор:{lab_employee}' or txt == f'Оператор: {lab_employee}' or txt.startswith('Оператор:') and lab_employee in txt:
            clear_paragraph_runs(p)
            p.append(make_run('Оператор:', italic=True))
            p.append(make_run(tab=True, italic=True))
            p.append(make_run(str(lab_employee), italic=False))


def process_tables(root, items):
    # Iterate all tables and expand docxtpl-like row loops.
    for tbl in root.findall('.//{%s}tbl' % W_NS):
        rows = list(tbl.findall('{%s}tr' % W_NS))
        i = 0
        while i < len(rows):
            row_text = normalize_placeholder_text(text_of_element(rows[i]))
            if "{%trforiteminjson_properties%}" in row_text:
                # find end marker and template data row between them
                end_idx = None
                for j in range(i+1, len(rows)):
                    if "{%trendfor%}" in normalize_placeholder_text(text_of_element(rows[j])):
                        end_idx = j
                        break
                if end_idx is None or end_idx <= i+1:
                    i += 1
                    continue
                data_row = rows[i+1]
                insert_at = list(tbl).index(rows[i])
                # remove control row, data row(s), end row
                for r in rows[i:end_idx+1]:
                    tbl.remove(r)
                # insert new rows
                for offset, item in enumerate(items):
                    nr = copy.deepcopy(data_row)
                    replace_item_placeholders(nr, item)
                    tbl.insert(insert_at + offset, nr)
                rows = list(tbl.findall('{%s}tr' % W_NS))
                i = insert_at + len(items)
            else:
                i += 1


def fill_docx(template_path, out_path, context, items):
    with zipfile.ZipFile(template_path, 'r') as zin:
        xml_bytes = zin.read('word/document.xml')
        root = ET.fromstring(xml_bytes)
        process_tables(root, items)
        # Replace remaining placeholders. Use two positions, first for first block, second for second block.
        positions = [context["position_1"], context["position_2"]]
        for p in root.findall('.//{%s}p' % W_NS):
            replace_text_in_element(p, context, positions)
        repair_operator_line(root, context.get('lab_employee', ''))
        new_xml = ET.tostring(root, encoding='utf-8', xml_declaration=True)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out_path, 'w', compression=zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == 'word/document.xml':
                    data = new_xml
                zout.writestr(item, data)


def compute_intensity(cfg, conc_mg_l, second=False):
    if cfg.get("name") == "Cd214.441" and "int_const_1" in cfg:
        base = cfg["int_const_2"] if second else cfg["int_const_1"]
        return round(base + cfg["b"] * conc_mg_l)
    a, b = cfg["a"], cfg["b"]
    c = cfg.get("c")
    if c is not None:
        return round((a + (b * conc_mg_l)) / (1 + (c * conc_mg_l)))
    return round(a + (b * conc_mg_l))


def make_item(element, target_result, mode="normal"):
    cfg = ELEMENTS[element]
    target = float(target_result)
    # difference between two mg/kg readings. Keep small and plausible relative to result.
    if target == 0:
        rel = 0.0
    else:
        if mode == "precise":
            rel = random.uniform(0.002, 0.01)
        elif mode == "rough":
            rel = random.uniform(0.015, 0.05)
        else:
            rel = random.uniform(0.005, 0.02)
    delta = max(abs(target) * rel, 0.00001)
    # random direction, maintain average target exactly before display.
    if random.random() < 0.5:
        conc2 = max(0, target - delta/2)
        conc4 = target + delta/2
    else:
        conc2 = target + delta/2
        conc4 = max(0, target - delta/2)
    conc1 = conc2 * cfg["m"] / cfg["v"]
    conc3 = conc4 * cfg["m"] / cfg["v"]
    item = {
        "id": cfg.get("id", 0),
        "name": cfg["name"],
        "v": cfg["v"],
        "m": cfg["m"],
        "a": cfg.get("a"),
        "b": cfg.get("b"),
        "SKO": round(random.uniform(0.01, 1.5), 2),
        "SKO_2": round(random.uniform(0.01, 1.5), 2),
            "conc_1": fmt_sig(conc1, 4),
        "conc_2": fmt_sig(conc2, 4),
        "conc_3": fmt_sig(conc3, 4),
        "conc_4": fmt_sig(conc4, 4),
        "intensivnost": compute_intensity(cfg, conc1, False),
        "intensivnost_2": compute_intensity(cfg, conc3, True),
        "result": fmt_sig((conc2 + conc4) / 2, 4),
    }
    return item



def make_item_from_actual(element, conc2, conc4, mode="normal"):
    """Build one ICP OS item from factual conc_2 and conc_4 values (mg/kg).

    In this mode conc_2 and conc_4 are source values from the user's table.
    The generator calculates only dependent values: conc_1, conc_3, intensities,
    SKO/SKO_2, and result.
    """
    cfg = ELEMENTS[element]
    conc2 = float(conc2)
    conc4 = float(conc4)
    if conc2 < 0 or conc4 < 0:
        raise RuntimeError(f"Отрицательная фактическая концентрация для {element}: {conc2}, {conc4}")
    conc1 = conc2 * cfg["m"] / cfg["v"]
    conc3 = conc4 * cfg["m"] / cfg["v"]
    return {
        "id": cfg.get("id", 0),
        "name": cfg["name"],
        "v": cfg["v"],
        "m": cfg["m"],
        "a": cfg.get("a"),
        "b": cfg.get("b"),
        "SKO": round(random.uniform(0.01, 1.5), 2),
        "SKO_2": round(random.uniform(0.01, 1.5), 2),
        "conc_1": fmt_sig(conc1, 4),
        "conc_2": fmt_sig(conc2, 4),
        "conc_3": fmt_sig(conc3, 4),
        "conc_4": fmt_sig(conc4, 4),
        "intensivnost": compute_intensity(cfg, conc1, False),
        "intensivnost_2": compute_intensity(cfg, conc3, True),
        "result": fmt_sig((conc2 + conc4) / 2, 4),
    }


def _row_value(row, *names):
    """Read first non-empty value from a row using several possible header names."""
    for name in names:
        if name in row and str(row.get(name, '')).strip() != '':
            return row.get(name)
    return None


def generate_from_actual_excel(excel_path, operator, start_dt, mode='normal', out_dir=OUTPUT_DIR):
    """Generate ICP OS reports from factual conc_2/conc_4 columns.

    Excel structure: first sample column, then pairs like `Pb conc_2`, `Pb conc_4`.
    Alternative separators are accepted: `Pb_conc_2`, `Pb.conc_2`, `Pb 2`, etc.
    """
    rows = read_xlsx(excel_path)
    if not rows:
        raise RuntimeError('Excel пустой или не содержит данных')
    out_dir.mkdir(parents=True, exist_ok=True)
    current = start_dt
    outputs = []
    for doc_index, row in enumerate(rows, start=1):
        sn = detect_sample_name(row)
        props = []
        for el in ELEMENT_ORDER:
            v2 = _row_value(row, f'{el} conc_2', f'{el}_conc_2', f'{el}.conc_2', f'{el} Конц.2', f'{el} конц_2', f'{el} 2')
            v4 = _row_value(row, f'{el} conc_4', f'{el}_conc_4', f'{el}.conc_4', f'{el} Конц.4', f'{el} конц_4', f'{el} 4')
            if v2 is None and v4 is None:
                continue
            if v2 is None or v4 is None:
                raise RuntimeError(f'Для {el} в строке {doc_index} нужно заполнить оба значения: conc_2 и conc_4')
            c2 = parse_float(v2)
            c4 = parse_float(v4)
            if c2 is None or c4 is None:
                raise RuntimeError(f'Некорректные фактические значения для {el} в строке {doc_index}: {v2}, {v4}')
            props.append(make_item_from_actual(el, c2, c4, mode))
        if not props:
            continue
        position_1 = random.randint(1, 105)
        position_2 = random.randint(1, 105)
        while position_2 == position_1:
            position_2 = random.randint(1, 105)
        action_t = current.strftime('%d.%m.%Y. %H:%M:%S')
        second = current + _dt.timedelta(seconds=random.randint(307, 350))
        test_var = second.strftime('%d.%m.%Y. %H:%M:%S')
        context = {
            'lab_employee': operator,
            'sn': sn,
            'position': str(position_1),
            'position_1': str(position_1),
            'position_2': str(position_2),
            'action_t': action_t,
            'action_time': action_t,
            'test_var': test_var,
        }
        out_name = f"ICP_OS_FACT_{doc_index:03d}_{safe_filename(sn)}.docx"
        out_path = out_dir / out_name
        fill_docx(TEMPLATE_PATH, out_path, context, props)
        outputs.append(out_path)
        with open(LOG_PATH, 'a', encoding='utf-8') as log:
            log.write(f"{_dt.datetime.now().isoformat(timespec='seconds')}\tFACT\t{operator}\t{sn}\t{action_t}\t{test_var}\t{position_1}/{position_2}\t{','.join(p['name'] for p in props)}\t{out_name}\n")
        current = second + _dt.timedelta(seconds=random.randint(180, 450))
    if not outputs:
        raise RuntimeError('В Excel не найдено ни одной строки с парами conc_2/conc_4')
    return outputs


def create_actual_excel_template(path):
    headers = ['Шифр образца']
    example = ['ИТС-ПБ-26-000001']
    demo = {
        'Pb': ('1.545', '1.595'),
        'Cr': ('0.785', '0.810'),
        'Ni': ('1.340', '1.365'),
    }
    for el in ELEMENT_ORDER:
        headers += [f'{el} conc_2', f'{el} conc_4']
        a, b = demo.get(el, ('', ''))
        example += [a, b]
    _write_simple_xlsx(path, [headers, example], sheet_name='ICP OS actual')


def _write_simple_xlsx(path, rows, sheet_name='Sheet1'):
    def cell_ref(col, row):
        name = ''
        col += 1
        while col:
            col, rem = divmod(col - 1, 26)
            name = chr(65 + rem) + name
        return f"{name}{row}"
    rows_xml = []
    for r_idx, values in enumerate(rows, start=1):
        cells = []
        for c_idx, val in enumerate(values):
            ref = cell_ref(c_idx, r_idx)
            val = str(val)
            cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape_xml(val)}</t></is></c>')
        rows_xml.append(f'<row r="{r_idx}">' + ''.join(cells) + '</row>')
    sheet_xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + ''.join(rows_xml) + '</sheetData></worksheet>'
    content_types = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>'
    rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'
    wb = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="{escape_xml(sheet_name)}" sheetId="1" r:id="rId1"/></sheets></workbook>'
    wb_rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>'
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', content_types)
        z.writestr('_rels/.rels', rels)
        z.writestr('xl/workbook.xml', wb)
        z.writestr('xl/_rels/workbook.xml.rels', wb_rels)
        z.writestr('xl/worksheets/sheet1.xml', sheet_xml)

def xlsx_col_to_index(cell_ref):
    m = re.match(r"([A-Z]+)", cell_ref)
    if not m:
        return 0
    col = 0
    for ch in m.group(1):
        col = col * 26 + (ord(ch) - 64)
    return col - 1


def read_xlsx(path):
    """Minimal xlsx reader for first worksheet."""
    ns = {'a': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(path, 'r') as z:
        shared = []
        if 'xl/sharedStrings.xml' in z.namelist():
            root = ET.fromstring(z.read('xl/sharedStrings.xml'))
            for si in root.findall('a:si', ns):
                texts = []
                for t in si.findall('.//a:t', ns):
                    texts.append(t.text or '')
                shared.append(''.join(texts))
        # find first sheet path
        sheet_name = 'xl/worksheets/sheet1.xml'
        if sheet_name not in z.namelist():
            sheets = [n for n in z.namelist() if n.startswith('xl/worksheets/sheet') and n.endswith('.xml')]
            if not sheets:
                raise RuntimeError('В Excel не найден лист')
            sheet_name = sorted(sheets)[0]
        root = ET.fromstring(z.read(sheet_name))
        rows = []
        for row in root.findall('.//a:row', ns):
            vals = []
            for c in row.findall('a:c', ns):
                idx = xlsx_col_to_index(c.attrib.get('r', 'A1'))
                while len(vals) <= idx:
                    vals.append('')
                t = c.attrib.get('t')
                v_el = c.find('a:v', ns)
                if t == 'inlineStr':
                    txt = ''.join(tn.text or '' for tn in c.findall('.//a:t', ns))
                elif v_el is None:
                    txt = ''
                elif t == 's':
                    txt = shared[int(v_el.text)] if v_el.text is not None else ''
                else:
                    txt = v_el.text or ''
                vals[idx] = txt
            if any(str(x).strip() for x in vals):
                rows.append(vals)
    if not rows:
        return []
    headers = [str(x).strip() for x in rows[0]]
    out = []
    for r in rows[1:]:
        d = {}
        for i, h in enumerate(headers):
            if h:
                d[h] = r[i] if i < len(r) else ''
        if any(str(v).strip() for v in d.values()):
            out.append(d)
    return out


def safe_filename(s):
    s = str(s).strip() or 'sample'
    return re.sub(r'[\\/:*?"<>|]+', '_', s)


def detect_sample_name(row):
    for key in ['Шифр образца', 'Шифр', 'Название пробы', 'sn', 'SN', 'Sample', 'sample']:
        if key in row and str(row[key]).strip():
            return str(row[key]).strip()
    # fallback first column
    if row:
        return str(next(iter(row.values()))).strip()
    return 'sample'


def generate_from_excel(excel_path, operator, start_dt, mode='normal', out_dir=OUTPUT_DIR):
    rows = read_xlsx(excel_path)
    if not rows:
        raise RuntimeError('Excel пустой или не содержит данных')
    out_dir.mkdir(parents=True, exist_ok=True)
    current = start_dt
    outputs = []
    for doc_index, row in enumerate(rows, start=1):
        sn = detect_sample_name(row)
        props = []
        for el in ELEMENT_ORDER:
            if el in row:
                val = parse_float(row.get(el))
                if val is not None:
                    if val < 0:
                        raise RuntimeError(f"Отрицательная концентрация в Excel: строка {doc_index}, элемент {el}, значение {val}")
                    props.append(make_item(el, val, mode))
        if not props:
            continue
        position_1 = random.randint(1, 105)
        position_2 = random.randint(1, 105)
        while position_2 == position_1:
            position_2 = random.randint(1, 105)
        action_t = current.strftime('%d.%m.%Y. %H:%M:%S')
        second = current + _dt.timedelta(seconds=random.randint(307, 350))
        test_var = second.strftime('%d.%m.%Y. %H:%M:%S')
        context = {
            'lab_employee': operator,
            'sn': sn,
            'position': str(position_1),
            'position_1': str(position_1),
            'position_2': str(position_2),
            'action_t': action_t,
            'action_time': action_t,
            'test_var': test_var,
        }
        out_name = f"ICP_OS_{doc_index:03d}_{safe_filename(sn)}.docx"
        out_path = out_dir / out_name
        fill_docx(TEMPLATE_PATH, out_path, context, props)
        outputs.append(out_path)
        with open(LOG_PATH, 'a', encoding='utf-8') as log:
            log.write(f"{_dt.datetime.now().isoformat(timespec='seconds')}\t{operator}\t{sn}\t{action_t}\t{test_var}\t{position_1}/{position_2}\t{','.join(p['name'] for p in props)}\t{out_name}\n")
        # next document starts 180-450 seconds after second table of current document
        current = second + _dt.timedelta(seconds=random.randint(180, 450))
    if not outputs:
        raise RuntimeError('В Excel не найдено ни одной строки с концентрациями элементов')
    return outputs


def create_excel_template(path):
    # Minimal XLSX with inline strings, no external dependencies.
    headers = ['Шифр образца'] + ELEMENT_ORDER
    example = ['ИТС-ПБ-26-000001', '1.57', '0.7975', '1.3525', '', '1.8175', '0.6525', '', '', '', '', '', '', '', '', '', '']
    def cell_ref(col, row):
        name = ''
        col += 1
        while col:
            col, rem = divmod(col-1, 26)
            name = chr(65+rem) + name
        return f"{name}{row}"
    rows_xml = []
    for r_idx, values in enumerate([headers, example], start=1):
        cells = []
        for c_idx, val in enumerate(values):
            ref = cell_ref(c_idx, r_idx)
            val = str(val)
            cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape_xml(val)}</t></is></c>')
        rows_xml.append(f'<row r="{r_idx}">' + ''.join(cells) + '</row>')
    sheet_xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + ''.join(rows_xml) + '</sheetData></worksheet>'
    content_types = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>'
    rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'
    wb = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="ICP OS" sheetId="1" r:id="rId1"/></sheets></workbook>'
    wb_rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>'
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', content_types)
        z.writestr('_rels/.rels', rels)
        z.writestr('xl/workbook.xml', wb)
        z.writestr('xl/_rels/workbook.xml.rels', wb_rels)
        z.writestr('xl/worksheets/sheet1.xml', sheet_xml)


def escape_xml(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def run_gui():
    if tk is None:
        raise RuntimeError('Tkinter недоступен. Используйте CLI.')
    root = tk.Tk()
    root.title('ICP OS 1.0 — ИЛ ИТС-ПБ')
    root.geometry('720x520')
    root.lift()
    root.attributes('-topmost', True)
    root.after(1000, lambda: root.attributes('-topmost', False))

    excel_var = tk.StringVar()
    op_var = tk.StringVar(value=OPERATORS[0])
    now = _dt.datetime.now()
    date_var = tk.StringVar(value=now.strftime('%d.%m.%Y'))
    time_var = tk.StringVar(value=now.strftime('%H:%M:%S'))
    mode_var = tk.StringVar(value='normal')
    status_var = tk.StringVar(value='Загрузите Excel с шифрами и концентрациями.')

    main = ttk.Frame(root, padding=14)
    main.pack(fill='both', expand=True)

    ttk.Label(main, text='ICP OS — ИЛ «ИТС-ПБ»', font=('Arial', 16, 'bold')).grid(row=0, column=0, columnspan=3, sticky='w', pady=(0,12))
    ttk.Label(main, text='Оператор').grid(row=1, column=0, sticky='w')
    ttk.Combobox(main, textvariable=op_var, values=OPERATORS, state='readonly', width=30).grid(row=1, column=1, sticky='w')

    ttk.Label(main, text='Дата первого анализа').grid(row=2, column=0, sticky='w', pady=4)
    ttk.Entry(main, textvariable=date_var, width=20).grid(row=2, column=1, sticky='w')
    ttk.Label(main, text='ДД.ММ.ГГГГ').grid(row=2, column=2, sticky='w')

    ttk.Label(main, text='Время первого анализа').grid(row=3, column=0, sticky='w', pady=4)
    ttk.Entry(main, textvariable=time_var, width=20).grid(row=3, column=1, sticky='w')
    ttk.Label(main, text='ЧЧ:ММ:СС').grid(row=3, column=2, sticky='w')

    ttk.Label(main, text='Режим разброса').grid(row=4, column=0, sticky='w', pady=4)
    modes = ttk.Frame(main)
    modes.grid(row=4, column=1, columnspan=2, sticky='w')
    ttk.Radiobutton(modes, text='обычный', variable=mode_var, value='normal').pack(side='left')
    ttk.Radiobutton(modes, text='точный', variable=mode_var, value='precise').pack(side='left')
    ttk.Radiobutton(modes, text='грубый', variable=mode_var, value='rough').pack(side='left')

    ttk.Label(main, text='Excel-файл серии').grid(row=5, column=0, sticky='w', pady=8)
    ttk.Entry(main, textvariable=excel_var, width=55).grid(row=5, column=1, sticky='we')
    def browse():
        p = filedialog.askopenfilename(title='Выберите Excel', filetypes=[('Excel files','*.xlsx'),('All files','*.*')])
        if p:
            excel_var.set(p)
    ttk.Button(main, text='Выбрать...', command=browse).grid(row=5, column=2, sticky='w')

    def make_tpl():
        p = filedialog.asksaveasfilename(title='Сохранить шаблон Excel', defaultextension='.xlsx', filetypes=[('Excel files','*.xlsx')], initialfile='ICP_OS_template.xlsx')
        if p:
            create_excel_template(Path(p))
            messagebox.showinfo('Готово', 'Шаблон Excel сохранен.')
    ttk.Button(main, text='Создать шаблон Excel', command=make_tpl).grid(row=6, column=1, sticky='w', pady=4)

    info = ('Структура Excel: первый столбец — «Шифр образца», далее столбцы элементов: Pb, Cr, Ni, Co, Cu, As, Sn, Se, Sb, Ba, Al, Fe, Zn, Mn, Cd, Ag.\n'
            'Для каждой строки будет создан отдельный DOCX только по заполненным элементам.\n'
            'Позиции виал генерируются 1–105 и различаются в двух блоках отчета.')
    ttk.Label(main, text=info, wraplength=680).grid(row=7, column=0, columnspan=3, sticky='w', pady=10)

    def generate():
        try:
            p = excel_var.get().strip()
            if not p:
                messagebox.showerror('Ошибка', 'Выберите Excel-файл.')
                return
            start_dt = _dt.datetime.strptime(date_var.get().strip() + ' ' + time_var.get().strip(), '%d.%m.%Y %H:%M:%S')
            outputs = generate_from_excel(Path(p), op_var.get(), start_dt, mode_var.get(), OUTPUT_DIR)
            status_var.set(f'Готово: создано {len(outputs)} документов в папке output.')
            messagebox.showinfo('Готово', f'Создано документов: {len(outputs)}\nПапка: {OUTPUT_DIR}')
        except Exception as e:
            traceback.print_exc()
            messagebox.showerror('Ошибка', str(e))
            status_var.set('Ошибка: ' + str(e))
    ttk.Button(main, text='СФОРМИРОВАТЬ ОТЧЕТЫ', command=generate).grid(row=8, column=1, sticky='w', pady=14)
    ttk.Label(main, textvariable=status_var, foreground='blue').grid(row=9, column=0, columnspan=3, sticky='w')

    main.columnconfigure(1, weight=1)
    root.mainloop()


def cli_test():
    tpl = BASE_DIR / 'ICP_OS_template.xlsx'
    if not tpl.exists():
        create_excel_template(tpl)
    outputs = generate_from_excel(tpl, OPERATORS[0], _dt.datetime.now().replace(microsecond=0), 'normal', OUTPUT_DIR)
    print(f'Created {len(outputs)} document(s):')
    for p in outputs:
        print(' -', p)


if __name__ == '__main__':
    try:
        if '--make-template' in sys.argv:
            create_excel_template(BASE_DIR / 'ICP_OS_template.xlsx')
            print('Excel template created:', BASE_DIR / 'ICP_OS_template.xlsx')
        elif '--cli-test' in sys.argv:
            cli_test()
        else:
            run_gui()
    except Exception:
        traceback.print_exc()
        input('\n[ERROR] Нажмите Enter для выхода...')
