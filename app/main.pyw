# -*- coding: utf-8 -*-
"""ITS-PB Lab Suite Qt Edition
Редизайн интерфейса на PySide6 без изменения функций генерации.
"""
from __future__ import annotations

import os
import sys
import re
import zipfile
import datetime as dt
import importlib.util
import traceback
from pathlib import Path
from xml.sax.saxutils import escape

APP_DIR = Path(__file__).resolve().parent
MODULES = APP_DIR / "modules"
ICP_DIR = MODULES / "ICP_OS"
AAS_DIR = MODULES / "AAS"
TOX_DIR = MODULES / "Toxicity"
GC_DIR = MODULES / "GC"
ASSETS_DIR = APP_DIR / "assets"
LOGO_PATH = ASSETS_DIR / "logo.svg"
LAB_NAME = 'ИЛ «ИТС-ПБ»'
OPERATORS = ["Зуева А.С.", "Королев А.И.", "Васильева Д.В.", "Тарабанова А.А."]

try:
    from PySide6.QtCore import Qt, QSize, QPoint
    from PySide6.QtGui import QAction, QIcon, QPixmap
    from PySide6.QtSvgWidgets import QSvgWidget
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton,
        QVBoxLayout, QHBoxLayout, QGridLayout, QStackedWidget, QComboBox,
        QLineEdit, QFileDialog, QMessageBox, QTabWidget, QRadioButton,
        QButtonGroup, QCheckBox, QScrollArea, QSpinBox, QProgressDialog,
        QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy
    )
except Exception as exc:
    raise SystemExit(
        "Для запуска нужен PySide6. Запустите INSTALL_QT_ONCE.bat, затем START.bat.\n"
        f"Ошибка: {exc}"
    )


def import_from(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Не удалось загрузить модуль: {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod

icp = import_from(ICP_DIR / "icp_os_generator.py", "icp_os_generator_suite_qt")
aas = import_from(AAS_DIR / "aas_report_generator.py", "aas_report_generator_suite_qt")
tox = import_from(TOX_DIR / "toxicity_generator.py", "toxicity_generator_suite_qt")
gc = import_from(GC_DIR / "gc_generator.py", "gc_generator_suite_qt")


class AppComboBox(QComboBox):
    """Единый выпадающий список для приложения.

    На некоторых Windows стандартный popup QComboBox раскрывается поверх
    выбранного значения. Сдвигаем popup ниже поля, чтобы пользователь всегда
    видел, что выбрал.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setMinimumHeight(38)
        self.setMaxVisibleItems(12)

    def showPopup(self):
        super().showPopup()
        try:
            popup = self.view().window()
            popup.move(self.mapToGlobal(QPoint(0, self.height() + 2)))
        except Exception:
            pass


def safe_name(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', '_', str(s).strip() or 'sample')


def open_folder(path: Path):
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.startfile(str(path))
    except Exception:
        pass


def parse_float(text: str) -> float:
    return float(str(text).strip().replace(',', '.'))


def parse_dt(date_text: str, time_text: str = "00:00:00") -> dt.datetime:
    raw = f"{date_text.strip()} {time_text.strip()}".strip()
    for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(raw, fmt)
        except ValueError:
            pass
    raise ValueError("Дата/время должны быть в формате ДД.ММ.ГГГГ и ЧЧ:ММ:СС")


def cell_ref(col: int, row: int) -> str:
    name = ''
    col += 1
    while col:
        col, rem = divmod(col - 1, 26)
        name = chr(65 + rem) + name
    return f"{name}{row}"


def write_xlsx(path: Path, rows: list[list[object]]):
    rows_xml = []
    for r_idx, values in enumerate(rows, start=1):
        cells = []
        for c_idx, val in enumerate(values):
            ref = cell_ref(c_idx, r_idx)
            val = '' if val is None else str(val)
            cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(val)}</t></is></c>')
        rows_xml.append(f'<row r="{r_idx}">' + ''.join(cells) + '</row>')
    sheet_xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + ''.join(rows_xml) + '</sheetData></worksheet>'
    content_types = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>'
    rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'
    wb = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>'
    wb_rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>'
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', content_types)
        z.writestr('_rels/.rels', rels)
        z.writestr('xl/workbook.xml', wb)
        z.writestr('xl/_rels/workbook.xml.rels', wb_rels)
        z.writestr('xl/worksheets/sheet1.xml', sheet_xml)


def qss() -> str:
    return """
    * { font-family: 'Segoe UI'; font-size: 10pt; }
    QMainWindow { background: #F4F6FA; }
    #Sidebar { background: #09213D; border: none; }
    #BrandTitle { color: white; font-size: 22pt; font-weight: 800; letter-spacing: .5px; }
    #BrandSub { color: #B9C8DC; font-size: 9pt; }
    #SidebarButton { text-align: left; color: #EAF0F8; background: transparent; border: none; padding: 12px 16px; border-radius: 10px; }
    #SidebarButton:hover { background: #14385F; }
    #SidebarButton[active="true"] { background: #1C5DAA; color: white; font-weight: 700; }
    #TopBar { background: white; border-bottom: 1px solid #DDE4EE; }
    #PageTitle { color: #132338; font-size: 19pt; font-weight: 800; }
    #PageSub { color: #687488; font-size: 10pt; }
    QFrame#Card { background: white; border: 1px solid #DDE4EE; border-radius: 14px; }
    QLabel#CardTitle { color: #132338; font-size: 12pt; font-weight: 750; }
    QLabel#Hint { color: #6B7280; }
    QLineEdit, QComboBox, QSpinBox { background: white; border: 1px solid #C9D3E1; border-radius: 8px; padding: 8px 12px; min-height: 30px; }
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border: 1px solid #1C5DAA; }
    QComboBox { padding-right: 28px; }
    QComboBox QAbstractItemView { background: white; border: 1px solid #C9D3E1; selection-background-color: #D8E8FA; padding: 6px; outline: 0; }
    QTabWidget::pane { border: none; }
    QTabBar::tab { background: #E8EEF6; color: #26384F; padding: 10px 18px; margin-right: 5px; border-top-left-radius: 9px; border-top-right-radius: 9px; }
    QTabBar::tab:selected { background: white; color: #0E2F57; font-weight: 700; border: 1px solid #DDE4EE; border-bottom: none; }
    QPushButton { border: none; border-radius: 9px; padding: 9px 16px; font-weight: 600; }
    QPushButton#Primary { background: #1C5DAA; color: white; }
    QPushButton#Primary:hover { background: #174B8A; }
    QPushButton#Secondary { background: #E7EEF7; color: #174B8A; }
    QPushButton#Secondary:hover { background: #D7E5F5; }
    QPushButton#Danger { background: #C8333A; color: white; }
    QTableWidget { background: white; gridline-color: #E5EAF2; border: 1px solid #DDE4EE; border-radius: 10px; selection-background-color: #D8E8FA; }
    QHeaderView::section { background: #F2F5F9; color: #344255; border: none; border-bottom: 1px solid #DDE4EE; padding: 8px; font-weight: 700; }
    QScrollArea { border: none; background: transparent; }
    QRadioButton, QCheckBox { color: #26384F; padding: 3px; }
    """


class Card(QFrame):
    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)
        if title:
            label = QLabel(title)
            label.setObjectName("CardTitle")
            layout.addWidget(label)
        self.body = layout


class CommonParams(Card):
    def __init__(self, title="Общие параметры", show_operator=True, show_time=True, show_mode=True, method_items=None):
        super().__init__(title)
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(8)
        self.body.addLayout(grid)
        now = dt.datetime.now().replace(microsecond=0)
        self.operator = AppComboBox(); self.operator.addItems(OPERATORS)
        self.date = QLineEdit(now.strftime('%d.%m.%Y'))
        self.time = QLineEdit(now.strftime('%H:%M:%S'))
        self.method = AppComboBox()
        if method_items:
            for mid, title in method_items:
                self.method.addItem(title, mid)
        self.mode_group = QButtonGroup(self)
        self.mode_normal = QRadioButton("Обычный")
        self.mode_precise = QRadioButton("Очень точный")
        self.mode_rough = QRadioButton("Верхняя граница")
        self.mode_normal.setChecked(True)
        for b, val in ((self.mode_normal, "normal"), (self.mode_precise, "precise"), (self.mode_rough, "rough")):
            self.mode_group.addButton(b)
            b.mode_value = val
        col = 0
        if show_operator:
            grid.addWidget(self._caption("Оператор"), 0, col); grid.addWidget(self.operator, 1, col); col += 1
        grid.addWidget(self._caption("Дата"), 0, col); grid.addWidget(self.date, 1, col); col += 1
        if show_time:
            grid.addWidget(self._caption("Время"), 0, col); grid.addWidget(self.time, 1, col); col += 1
        row_base = 2
        if method_items:
            grid.addWidget(self._caption("Методика"), row_base, 0, 1, max(col, 1))
            grid.addWidget(self.method, row_base + 1, 0, 1, max(col, 1))
            row_base += 2
        if show_mode:
            mode_box = QHBoxLayout(); mode_box.setSpacing(12)
            mode_box.addWidget(self.mode_normal); mode_box.addWidget(self.mode_precise); mode_box.addWidget(self.mode_rough); mode_box.addStretch(1)
            grid.addWidget(self._caption("Режим СКО"), row_base, 0, 1, max(col, 1))
            grid.addLayout(mode_box, row_base + 1, 0, 1, max(col, 1))
        for i in range(max(col, 1)):
            grid.setColumnStretch(i, 1)

    def _caption(self, text):
        lbl = QLabel(text); lbl.setObjectName("Hint"); return lbl

    def mode(self):
        return self.mode_group.checkedButton().mode_value


class ModulePage(QWidget):
    def __init__(self, title: str, subtitle: str):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(26, 24, 26, 24)
        outer.setSpacing(16)
        head = QVBoxLayout(); head.setSpacing(2)
        t = QLabel(title); t.setObjectName("PageTitle")
        s = QLabel(subtitle); s.setObjectName("PageSub")
        head.addWidget(t); head.addWidget(s)
        outer.addLayout(head)
        self.content = QVBoxLayout(); self.content.setSpacing(12)
        outer.addLayout(self.content, 1)


class IcpPage(ModulePage):
    def __init__(self, main_window):
        super().__init__("ICP OS", "Генерация отчетов ICP-OES · одиночный режим и серии через Excel")
        self.main = main_window
        self.common = CommonParams(show_operator=True, show_time=True, show_mode=True)
        self.content.addWidget(self.common)
        tabs = QTabWidget(); self.content.addWidget(tabs, 1)
        tabs.addTab(self.single_tab(), "Одиночная генерация")
        tabs.addTab(self.excel_tab(), "Массовая через Excel")
        tabs.addTab(self.actual_tab(), "Фактические значения")

    def single_tab(self):
        w = QWidget(); lay = QVBoxLayout(w); lay.setContentsMargins(0, 12, 0, 0); lay.setSpacing(12)
        c = Card("Параметры образца и элементы")
        form = QGridLayout(); form.setHorizontalSpacing(14); form.setVerticalSpacing(8); c.body.addLayout(form)
        self.single_sn = QLineEdit("ИТС-ПБ-26-000001")
        form.addWidget(QLabel("Шифр образца"), 0, 0); form.addWidget(self.single_sn, 1, 0, 1, 2)
        elements = list(getattr(icp, 'ELEMENT_ORDER', [])) or ["Pb","Cr","Ni","Co","Cu","As","Sn","Se","Sb","Ba","Al","Fe","Zn","Mn","Cd","Ag"]
        self.icp_rows = []
        table = QTableWidget(len(elements), 3)
        table.setHorizontalHeaderLabels(["✓", "Элемент", "Итоговая концентрация"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        for r, el in enumerate(elements):
            chk = QCheckBox(); chk.setStyleSheet("margin-left:8px")
            table.setCellWidget(r, 0, chk)
            table.setItem(r, 1, QTableWidgetItem(el))
            table.setItem(r, 2, QTableWidgetItem(""))
            self.icp_rows.append((el, chk))
        table.setMinimumHeight(290)
        c.body.addWidget(table)
        self.icp_table = table
        actions = QHBoxLayout(); actions.addStretch(1)
        btn = self.main.primary("Сформировать отчет", self.generate_icp_single)
        actions.addWidget(btn)
        c.body.addLayout(actions)
        lay.addWidget(c); return w

    def excel_tab(self):
        w = QWidget(); lay = QVBoxLayout(w); lay.setContentsMargins(0, 12, 0, 0); lay.setSpacing(12)
        c = Card("Файл серии")
        self.icp_excel = QLineEdit(); self.icp_excel.setPlaceholderText("Выберите Excel-файл серии")
        row = QHBoxLayout(); row.addWidget(self.icp_excel, 1); row.addWidget(self.main.secondary("Выбрать Excel", lambda: self.pick_file(self.icp_excel)))
        c.body.addLayout(row)
        row2 = QHBoxLayout(); row2.addWidget(self.main.secondary("Создать шаблон Excel", self.create_icp_template)); row2.addStretch(1); row2.addWidget(self.main.primary("Сформировать серию", self.generate_icp_excel))
        c.body.addLayout(row2)
        lay.addWidget(c); lay.addStretch(1); return w

    def actual_tab(self):
        w = QWidget(); lay = QVBoxLayout(w); lay.setContentsMargins(0, 12, 0, 0); lay.setSpacing(12)
        c = Card("Фактические значения conc_2 / conc_4")
        hint = QLabel("Excel: первый столбец — шифр образца, далее пары столбцов: Pb conc_2, Pb conc_4, Cr conc_2, Cr conc_4 ...")
        hint.setObjectName("Hint")
        c.body.addWidget(hint)
        self.icp_actual_excel = QLineEdit(); self.icp_actual_excel.setPlaceholderText("Выберите Excel-файл с фактическими значениями")
        row = QHBoxLayout(); row.addWidget(self.icp_actual_excel, 1); row.addWidget(self.main.secondary("Выбрать Excel", lambda: self.pick_file(self.icp_actual_excel)))
        c.body.addLayout(row)
        row2 = QHBoxLayout()
        row2.addWidget(self.main.secondary("Создать шаблон Excel", self.create_icp_actual_template))
        row2.addStretch(1)
        row2.addWidget(self.main.primary("Сформировать по фактическим", self.generate_icp_actual_excel))
        c.body.addLayout(row2)
        lay.addWidget(c); lay.addStretch(1); return w


    def pick_file(self, target):
        p, _ = QFileDialog.getOpenFileName(self, "Выберите Excel", str(APP_DIR), "Excel (*.xlsx)")
        if p: target.setText(p)

    def create_icp_template(self):
        p, _ = QFileDialog.getSaveFileName(self, "Сохранить шаблон", str(APP_DIR / "ICP_OS_template.xlsx"), "Excel (*.xlsx)")
        if p:
            try:
                icp.create_excel_template(Path(p))
                self.main.info("Шаблон Excel ICP OS сохранен")
            except Exception as e:
                self.main.error(str(e))

    def create_icp_actual_template(self):
        p, _ = QFileDialog.getSaveFileName(self, "Сохранить шаблон фактических значений", str(APP_DIR / "ICP_OS_actual_values_template.xlsx"), "Excel (*.xlsx)")
        if p:
            try:
                icp.create_actual_excel_template(Path(p))
                self.main.info("Шаблон Excel фактических значений ICP OS сохранен")
            except Exception as e:
                self.main.error(str(e))

    def generate_icp_actual_excel(self):
        try:
            if not self.icp_actual_excel.text().strip():
                raise ValueError("Выберите Excel-файл с фактическими значениями")
            start = parse_dt(self.common.date.text(), self.common.time.text())
            outs = icp.generate_from_actual_excel(Path(self.icp_actual_excel.text()), self.common.operator.currentText(), start, self.common.mode(), ICP_DIR / 'output')
            self.main.done("Генерация ICP OS по фактическим значениям завершена", len(outs), ICP_DIR / 'output')
        except Exception:
            self.main.error(traceback.format_exc())


    def generate_icp_excel(self):
        try:
            if not self.icp_excel.text().strip(): raise ValueError("Выберите Excel-файл")
            start = parse_dt(self.common.date.text(), self.common.time.text())
            outs = icp.generate_from_excel(Path(self.icp_excel.text()), self.common.operator.currentText(), start, self.common.mode(), ICP_DIR / 'output')
            self.main.done("Генерация ICP OS завершена", len(outs), ICP_DIR / 'output')
        except Exception:
            self.main.error(traceback.format_exc())

    def generate_icp_single(self):
        try:
            props=[]
            for r, (el, chk) in enumerate(self.icp_rows):
                if chk.isChecked():
                    val = self.icp_table.item(r, 2).text().strip()
                    if not val: raise ValueError(f"Введите концентрацию для {el}")
                    props.append(icp.make_item(el, parse_float(val), self.common.mode()))
            if not props: raise ValueError("Выберите хотя бы один элемент")
            start = parse_dt(self.common.date.text(), self.common.time.text())
            import random as _r
            p1 = _r.randint(1, 105); p2 = _r.randint(1, 105)
            while p2 == p1: p2 = _r.randint(1, 105)
            second = start + dt.timedelta(seconds=_r.randint(307, 350))
            sn = self.single_sn.text().strip()
            ctx = {'lab_employee': self.common.operator.currentText(), 'sn': sn, 'position': str(p1), 'position_1': str(p1), 'position_2': str(p2), 'action_t': start.strftime('%d.%m.%Y %H:%M:%S'), 'action_time': start.strftime('%d.%m.%Y %H:%M:%S'), 'test_var': second.strftime('%d.%m.%Y %H:%M:%S')}
            out_dir = ICP_DIR / 'output'; out_dir.mkdir(exist_ok=True)
            out = out_dir / f"ICP_OS_001_{safe_name(sn)}.docx"
            icp.fill_docx(icp.TEMPLATE_PATH, out, ctx, props)
            self.main.done("Отчет ICP OS сформирован", 1, out_dir)
        except Exception:
            self.main.error(traceback.format_exc())


class AasPage(ModulePage):
    def __init__(self, main_window):
        super().__init__("AAS", "Генерация отчетов атомно-абсорбционного анализа")
        self.main = main_window
        self.common = CommonParams(show_operator=False, show_time=True, show_mode=True, method_items=aas.method_profile_titles())
        self.content.addWidget(self.common)
        tabs = QTabWidget(); self.content.addWidget(tabs, 1)
        tabs.addTab(self.single_tab(), "Одиночная генерация")
        tabs.addTab(self.excel_tab(), "Массовая через Excel")
        self.common.method.currentIndexChanged.connect(self.update_aas_elements)

    def current_aas_profile(self):
        return self.common.method.currentData() or "GOST_31870"

    def update_aas_elements(self):
        if not hasattr(self, "aas_el"):
            return
        current = self.aas_el.currentText()
        elements = aas.elements_for_profile(self.current_aas_profile())
        self.aas_el.blockSignals(True)
        self.aas_el.clear()
        self.aas_el.addItems(elements)
        if current in elements:
            self.aas_el.setCurrentText(current)
        self.aas_el.blockSignals(False)

    def single_tab(self):
        w = QWidget(); lay = QVBoxLayout(w); lay.setContentsMargins(0, 12, 0, 0)
        c = Card("Параметры отчета")
        g = QGridLayout(); g.setHorizontalSpacing(14); g.setVerticalSpacing(10); c.body.addLayout(g)
        self.aas_el = AppComboBox(); self.aas_el.addItems(aas.elements_for_profile(self.current_aas_profile()))
        self.aas_sn = QLineEdit("ИТС-ПБ-26-000001")
        self.aas_c = QLineEdit("0.52978")
        self.aas_measurements = QSpinBox()
        self.aas_measurements.setRange(2, 5)
        self.aas_measurements.setValue(2)
        g.addWidget(QLabel("Элемент"),0,0); g.addWidget(self.aas_el,1,0)
        g.addWidget(QLabel("Шифр образца"),0,1); g.addWidget(self.aas_sn,1,1)
        g.addWidget(QLabel("Средняя концентрация"),0,2); g.addWidget(self.aas_c,1,2)
        g.addWidget(QLabel("Параллельные измерения"),0,3); g.addWidget(self.aas_measurements,1,3)
        actions=QHBoxLayout(); actions.addStretch(1); actions.addWidget(self.main.primary("Сформировать отчет", self.generate_aas_single)); c.body.addLayout(actions)
        lay.addWidget(c); lay.addStretch(1); return w

    def excel_tab(self):
        w=QWidget(); lay=QVBoxLayout(w); lay.setContentsMargins(0,12,0,0)
        c=Card("Файл серии")
        self.aas_excel=QLineEdit(); self.aas_excel.setPlaceholderText("Выберите Excel-файл серии")
        row=QHBoxLayout(); row.addWidget(self.aas_excel,1); row.addWidget(self.main.secondary("Выбрать Excel", lambda:self.pick_file(self.aas_excel))); c.body.addLayout(row)
        row2=QHBoxLayout(); row2.addWidget(self.main.secondary("Создать шаблон Excel", self.create_aas_template)); row2.addStretch(1); row2.addWidget(self.main.primary("Сформировать серию", self.generate_aas_excel)); c.body.addLayout(row2)
        lay.addWidget(c); lay.addStretch(1); return w

    def pick_file(self,target):
        p,_=QFileDialog.getOpenFileName(self,"Выберите Excel",str(APP_DIR),"Excel (*.xlsx)")
        if p: target.setText(p)

    def create_aas_template(self):
        p,_=QFileDialog.getSaveFileName(self,"Сохранить шаблон",str(APP_DIR/"AAS_template.xlsx"),"Excel (*.xlsx)")
        if p:
            elements = aas.elements_for_profile(self.current_aas_profile())
            rows=[["Шифр пробы","Дата",*elements],["ИТС-ПБ-26-000001",self.common.date.text(),"0.52978",*("" for _ in elements[1:])]]
            write_xlsx(Path(p), rows); self.main.info("Шаблон Excel ААС сохранен")

    def generate_aas_single(self):
        try:
            out=aas.generate_report(self.aas_el.currentText(), f'{self.common.date.text()} {self.common.time.text()}', self.aas_sn.text().strip(), parse_float(self.aas_c.text()), self.common.mode(), AAS_DIR/'output', self.current_aas_profile(), self.aas_measurements.value())
            self.main.done("Отчет ААС сформирован",1,AAS_DIR/'output')
        except Exception: self.main.error(traceback.format_exc())

    def generate_aas_excel(self):
        try:
            if not self.aas_excel.text().strip(): raise ValueError("Выберите Excel-файл")
            created,batch_dir=aas.generate_from_excel(Path(self.aas_excel.text()), f'{self.common.date.text()} {self.common.time.text()}', self.common.mode(), AAS_DIR/'output', self.current_aas_profile(), self.aas_measurements.value())
            self.main.done("Серия ААС сформирована",len(created),batch_dir)
        except Exception: self.main.error(traceback.format_exc())


class GcPage(ModulePage):
    def __init__(self, main_window):
        super().__init__("Газовая хроматография", "МУК 4.1.3166 · генерация двух хроматограмм с независимыми моделями ПИД-1/ПИД-2")
        self.main = main_window
        self.common = CommonParams(
            show_operator=False,
            show_time=True,
            show_mode=False,
            method_items=[("MUK_4_1_3166", "МУК 4.1.3166")],
        )
        self.content.addWidget(self.common)

        info = QLabel("Количество хроматограмм определяется методикой: 2")
        info.setObjectName("Hint")
        self.content.addWidget(info)

        tabs = QTabWidget()
        self.content.addWidget(tabs, 1)
        tabs.addTab(self._single_random_tab(), "Одиночная — рандом")
        tabs.addTab(self._single_actual_tab(), "Одиночная — фактические")
        tabs.addTab(self._excel_tab("random"), "Массовая — рандом")
        tabs.addTab(self._excel_tab("actual"), "Массовая — фактические")

    def _component_table(self, actual=False):
        columns = ["Компонент", "Базовая концентрация"] if not actual else ["Компонент", "Хроматограмма 1", "Хроматограмма 2"]
        table = QTableWidget(len(gc.COMPONENT_DEFAULTS), len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, len(columns)):
            table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeToContents)
        for row, (component, default) in enumerate(gc.COMPONENT_DEFAULTS):
            name_item = QTableWidgetItem(component)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            table.setItem(row, 0, name_item)
            table.setItem(row, 1, QTableWidgetItem(f"{default:.5f}".replace(".", ",")))
            if actual:
                table.setItem(row, 2, QTableWidgetItem(f"{default:.5f}".replace(".", ",")))
        table.setMinimumHeight(460)
        return table

    def _sample_card(self):
        card = Card("Параметры образца")
        grid = QGridLayout()
        self.gc_sample = QLineEdit("ИТС-ПБ-26-000001")
        grid.addWidget(QLabel("Шифр образца"), 0, 0)
        grid.addWidget(self.gc_sample, 1, 0)
        card.body.addLayout(grid)
        return card

    def _single_random_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.addWidget(self._sample_card())
        self.gc_random_table = self._component_table(False)
        layout.addWidget(self.gc_random_table, 1)
        row = QHBoxLayout()
        row.addWidget(self.main.secondary("Вернуть значения по умолчанию", lambda: self._reset_table(self.gc_random_table, False)))
        row.addStretch(1)
        row.addWidget(self.main.primary("Сформировать хроматограммы", self._run_single_random))
        layout.addLayout(row)
        return widget

    def _single_actual_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 10, 0, 0)
        card = Card("Параметры образца")
        self.gc_actual_sample = QLineEdit("ИТС-ПБ-26-000001")
        card.body.addWidget(QLabel("Шифр образца"))
        card.body.addWidget(self.gc_actual_sample)
        layout.addWidget(card)
        self.gc_actual_table = self._component_table(True)
        layout.addWidget(self.gc_actual_table, 1)
        row = QHBoxLayout()
        row.addWidget(self.main.secondary("Вернуть значения по умолчанию", lambda: self._reset_table(self.gc_actual_table, True)))
        row.addStretch(1)
        row.addWidget(self.main.primary("Сформировать хроматограммы", self._run_single_actual))
        layout.addLayout(row)
        return widget

    def _excel_tab(self, mode):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 10, 0, 0)
        card = Card("Файл массовой генерации")
        line = QLineEdit()
        choose = self.main.secondary("Выбрать Excel", lambda: self._pick_excel(line))
        template = self.main.secondary("Открыть шаблон", lambda: self._open_template(mode))
        row = QHBoxLayout()
        row.addWidget(line, 1)
        row.addWidget(choose)
        row.addWidget(template)
        card.body.addLayout(row)
        run = self.main.primary("Сформировать серию", lambda: self._run_excel(line, mode))
        card.body.addWidget(run, 0, Qt.AlignRight)
        layout.addWidget(card)
        layout.addStretch(1)
        return widget

    def _reset_table(self, table, actual):
        for row, (_, default) in enumerate(gc.COMPONENT_DEFAULTS):
            table.item(row, 1).setText(f"{default:.5f}".replace(".", ","))
            if actual:
                table.item(row, 2).setText(f"{default:.5f}".replace(".", ","))

    def _table_values(self, table, actual):
        values = {}
        for row in range(table.rowCount()):
            component = table.item(row, 0).text()
            if actual:
                values[component] = (
                    parse_float(table.item(row, 1).text()),
                    parse_float(table.item(row, 2).text()),
                )
            else:
                values[component] = parse_float(table.item(row, 1).text())
        return values

    def _run_single_random(self):
        try:
            out = gc.build_sample(
                self.gc_sample.text().strip(),
                self.common.date.text(),
                self.common.time.text(),
                "random",
                self._table_values(self.gc_random_table, False),
                GC_DIR / "output",
            )
            self.main.done("Хроматограммы сформированы", 4, out)
        except Exception as exc:
            self.main.error(traceback.format_exc())

    def _run_single_actual(self):
        try:
            out = gc.build_sample(
                self.gc_actual_sample.text().strip(),
                self.common.date.text(),
                self.common.time.text(),
                "actual",
                self._table_values(self.gc_actual_table, True),
                GC_DIR / "output",
            )
            self.main.done("Хроматограммы сформированы", 4, out)
        except Exception:
            self.main.error(traceback.format_exc())

    def _pick_excel(self, line):
        path, _ = QFileDialog.getOpenFileName(self, "Выберите Excel", "", "Excel (*.xlsx)")
        if path:
            line.setText(path)

    def _open_template(self, mode):
        path = gc.excel_template_path(mode)
        try:
            os.startfile(str(path))
        except Exception:
            open_folder(path.parent)

    def _run_excel(self, line, mode):
        try:
            path = Path(line.text().strip())
            if not path.exists():
                raise FileNotFoundError("Выберите Excel-файл")
            created, batch_dir = gc.generate_from_excel(path, mode, GC_DIR / "output")
            self.main.done("Серия хроматограмм сформирована", len(created) * 4, batch_dir)
        except Exception:
            self.main.error(traceback.format_exc())


class ToxicityPage(ModulePage):
    def __init__(self, main_window):
        super().__init__("Токсичность", "Генерация протоколов токсичности")
        self.main=main_window
        self.content.addWidget(self.single_card())
        self.content.addWidget(self.excel_card())
        self.content.addStretch(1)

    def single_card(self):
        c=Card("Одиночная генерация")
        g=QGridLayout(); g.setHorizontalSpacing(14); g.setVerticalSpacing(10); c.body.addLayout(g)
        self.tox_num=QLineEdit("1"); self.tox_date=QLineEdit(dt.datetime.now().strftime('%d.%m.%Y')); self.tox_sample=QLineEdit("ИТС-ПБ-26-000001"); self.tox_bull=QLineEdit("Кэнон-М"); self.tox_it=QLineEdit("104.8")
        fields=[("Номер",self.tox_num),("Дата",self.tox_date),("Шифр образца",self.tox_sample),("Бык",self.tox_bull),("It",self.tox_it)]
        for i,(lab,widget) in enumerate(fields): g.addWidget(QLabel(lab),0,i); g.addWidget(widget,1,i)
        actions=QHBoxLayout(); actions.addStretch(1); actions.addWidget(self.main.primary("Сформировать протокол", self.generate_tox_single)); c.body.addLayout(actions)
        return c

    def excel_card(self):
        c=Card("Массовая генерация через Excel")
        self.tox_excel=QLineEdit(); self.tox_excel.setPlaceholderText("Выберите Excel-файл серии")
        row=QHBoxLayout(); row.addWidget(self.tox_excel,1); row.addWidget(self.main.secondary("Выбрать Excel", lambda:self.pick_file(self.tox_excel))); c.body.addLayout(row)
        row2=QHBoxLayout(); row2.addWidget(self.main.secondary("Создать шаблон Excel", self.create_tox_template)); row2.addStretch(1); row2.addWidget(self.main.primary("Сформировать серию", self.generate_tox_excel)); c.body.addLayout(row2)
        return c

    def pick_file(self,target):
        p,_=QFileDialog.getOpenFileName(self,"Выберите Excel",str(APP_DIR),"Excel (*.xlsx)")
        if p: target.setText(p)

    def create_tox_template(self):
        p,_=QFileDialog.getSaveFileName(self,"Сохранить шаблон",str(APP_DIR/"Toxicity_template.xlsx"),"Excel (*.xlsx)")
        if p:
            rows=[["Номер","Дата","Шифр образца","Бык","It"],["1",dt.datetime.now().strftime('%d.%m.%Y'),"ИТС-ПБ-26-000001","Кэнон-М","104.8"]]
            write_xlsx(Path(p), rows); self.main.info("Шаблон Excel токсичности сохранен")

    def generate_tox_single(self):
        try:
            out=TOX_DIR/'output'; out.mkdir(exist_ok=True)
            tox.run_generate(self.tox_num.text(), self.tox_date.text(), self.tox_sample.text(), self.tox_bull.text(), parse_float(self.tox_it.text()), out)
            self.main.done("Протокол токсичности сформирован",1,out)
        except Exception: self.main.error(traceback.format_exc())

    def generate_tox_excel(self):
        try:
            if not self.tox_excel.text().strip(): raise ValueError("Выберите Excel-файл")
            # Простое чтение xlsx через ICP helper, так как формат строковый.
            rows = icp.read_xlsx(Path(self.tox_excel.text()))
            out=TOX_DIR/'output'; out.mkdir(exist_ok=True)
            cnt=0
            for row in rows:
                if not row: continue
                num=str(row.get('Номер') or row.get('num') or '').strip(); date=str(row.get('Дата') or row.get('date') or '').strip(); sample=str(row.get('Шифр образца') or row.get('sample') or row.get('sn') or '').strip(); bull=str(row.get('Бык') or row.get('bull') or 'Кэнон-М').strip(); it=str(row.get('It') or row.get('it') or '').strip()
                if not (num and date and sample and it): continue
                tox.run_generate(num,date,sample,bull,parse_float(it),out); cnt+=1
            if cnt==0: raise ValueError("В Excel не найдено строк для генерации")
            self.main.done("Серия токсичности сформирована",cnt,out)
        except Exception: self.main.error(traceback.format_exc())


class ServicePage(ModulePage):
    def __init__(self, main_window):
        super().__init__("Сервис", "Папки, шаблоны и служебные действия")
        self.main=main_window
        c=Card("Рабочие папки")
        for title,path in [("Output ICP OS", ICP_DIR/'output'), ("Output AAS", AAS_DIR/'output'), ("Output токсичность", TOX_DIR/'output'), ("Output GC", GC_DIR/'output'), ("Папка приложения", APP_DIR)]:
            row=QHBoxLayout(); row.addWidget(QLabel(title)); row.addStretch(1); row.addWidget(main_window.secondary("Открыть", lambda p=path: open_folder(p))); c.body.addLayout(row)
        self.content.addWidget(c); self.content.addStretch(1)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ITS-PB Lab Suite · Qt Edition")
        self.resize(1280, 780)
        self.setMinimumSize(1180, 720)
        self.setStyleSheet(qss())
        root=QWidget(); self.setCentralWidget(root)
        main=QHBoxLayout(root); main.setContentsMargins(0,0,0,0); main.setSpacing(0)
        sidebar=QFrame(); sidebar.setObjectName("Sidebar"); sidebar.setFixedWidth(250)
        side=QVBoxLayout(sidebar); side.setContentsMargins(22,24,22,22); side.setSpacing(8)
        if LOGO_PATH.exists():
            logo=QSvgWidget(str(LOGO_PATH)); logo.setFixedSize(76,46); side.addWidget(logo,0,Qt.AlignLeft)
        brand=QLabel("ITS-PB"); brand.setObjectName("BrandTitle"); side.addWidget(brand)
        sub=QLabel("Lab Suite · Qt Edition\nИЛ «ИТС-ПБ»"); sub.setObjectName("BrandSub"); side.addWidget(sub)
        side.addSpacing(24)
        self.buttons=[]
        self.stack=QStackedWidget()
        pages=[("ICP OS","Отчеты ICP-OES",IcpPage(self)),("AAS","Атомная абсорбция",AasPage(self)),("GC","Газовая хроматография",GcPage(self)),("Токсичность","Протоколы",ToxicityPage(self)),("Сервис","Папки и настройки",ServicePage(self))]
        for idx,(name,hint,page) in enumerate(pages):
            btn=QPushButton(f"{name}\n{hint}"); btn.setObjectName("SidebarButton"); btn.setCheckable(True); btn.clicked.connect(lambda checked=False, i=idx: self.select(i)); side.addWidget(btn); self.buttons.append(btn); self.stack.addWidget(page)
        side.addStretch(1)
        foot=QLabel("Профиль лаборатории\nИЛ «ИТС-ПБ»"); foot.setObjectName("BrandSub"); side.addWidget(foot)
        main.addWidget(sidebar)
        work=QFrame(); work.setObjectName("WorkArea"); lay=QVBoxLayout(work); lay.setContentsMargins(0,0,0,0)
        top=QFrame(); top.setObjectName("TopBar"); top.setFixedHeight(56)
        top_l=QHBoxLayout(top); top_l.setContentsMargins(26,0,26,0)
        top_l.addWidget(QLabel("Laboratory Reporting System")); top_l.addStretch(1); top_l.addWidget(QLabel("1920×1080 optimized"))
        lay.addWidget(top); lay.addWidget(self.stack,1)
        main.addWidget(work,1)
        self.select(0)

    def primary(self,text,cmd):
        b=QPushButton(text); b.setObjectName("Primary"); b.clicked.connect(cmd); return b
    def secondary(self,text,cmd):
        b=QPushButton(text); b.setObjectName("Secondary"); b.clicked.connect(cmd); return b
    def select(self,index):
        self.stack.setCurrentIndex(index)
        for i,b in enumerate(self.buttons): b.setChecked(i==index); b.setProperty("active", i==index); b.style().unpolish(b); b.style().polish(b)
    def info(self,msg):
        QMessageBox.information(self,"ITS-PB Lab Suite",msg)
    def error(self,msg):
        box=QMessageBox(self); box.setWindowTitle("Ошибка"); box.setIcon(QMessageBox.Critical); box.setText("Не удалось выполнить действие"); box.setDetailedText(str(msg)); box.exec()
    def done(self,title,count,out_dir):
        box=QMessageBox(self); box.setWindowTitle("Готово"); box.setIcon(QMessageBox.Information); box.setText(title); box.setInformativeText(f"Создано документов: {count}\n\nПапка:\n{out_dir}"); open_btn=box.addButton("Открыть папку", QMessageBox.ActionRole); box.addButton("Закрыть", QMessageBox.AcceptRole); box.exec();
        if box.clickedButton() == open_btn: open_folder(Path(out_dir))


def main():
    app=QApplication(sys.argv)
    app.setApplicationName("ITS-PB Lab Suite")
    app.setStyle("Fusion")
    win=MainWindow(); win.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
