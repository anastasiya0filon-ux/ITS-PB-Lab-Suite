
# -*- coding: utf-8 -*-
"""
Генератор протокола токсичности.
График строится ИМЕННО по данным сгенерированной таблицы:
- Контроль = средние значения по 5 столбцам Кн для каждого из 8 циклов;
- Опыт = средние значения по 4 столбцам Оп для каждого из 8 циклов.
DOCX формируется на базе tox_template.docx с сохранением исходной верстки.
"""
import os, sys, json, math, random, zipfile, datetime
from pathlib import Path
try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
except Exception:
    tk = None
try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:
    Image = ImageDraw = ImageFont = None

BASE_K = [604.0, 500.2, 404.0, 272.8, 58.4, 46.4, 13.2, 0.0]
BASE_OP = [538.5, 457.2, 385.8, 168.8, 91.5, 28.0, 8.5, 0.0]
BASE_KD = [50, 20, 30, 10, 20, 10, 5, 0]
BASE_OPD = [50, 30, 20, 20, 10, 10, 5, 0]

def app_dir():
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent

def ru_date(s):
    if not s: return datetime.date.today().strftime('%d.%m.%Y')
    s = str(s).strip()
    for fmt in ('%d.%m.%Y','%Y-%m-%d','%d/%m/%Y'):
        try: return datetime.datetime.strptime(s, fmt).strftime('%d.%m.%Y')
        except ValueError: pass
    return s

def avg(x): return sum(x)/len(x) if x else 0

def cv(x):
    m = avg(x)
    if not x or m == 0 or len(x) < 2: return 0.0
    sd = math.sqrt(sum((v-m)**2 for v in x)/(len(x)-1))
    return sd/m*100


def enforce_monotone(row):
    """Приводит ряд 1..8 циклов к правилу: значения не растут, 8-й цикл = 0."""
    row = [max(0, int(round(v))) for v in row]
    for i in range(1, len(row)):
        if row[i] > row[i-1]:
            row[i] = max(0, row[i-1] - random.randint(0, 3))
    row[-1] = 0
    return row

def make_monotone_replicates(mean_profile, n, seed, spread_profile=None, min_drop=0):
    """Генерирует n нестационарных рядов по циклам.

    Правила генерации:
    - каждая повторность моделирует затухание подвижности во времени;
    - внутри повторности значения от 1-го к 8-му циклу не увеличиваются;
    - 8-й цикл всегда равен 0;
    - разброс зависит от цикла: в начале выше, в хвосте ниже;
    - после генерации средние по циклам подгоняются к заданному профилю без нарушения монотонности.
    """
    rng = random.Random(seed)
    if spread_profile is None:
        spread_profile = [35, 24, 24, 18, 12, 8, 4, 0]
    rows=[]
    for r in range(n):
        vals=[]
        prev=None
        row_shift = rng.uniform(-10, 10)
        for i, mu in enumerate(mean_profile):
            if i == len(mean_profile)-1:
                v = 0
            else:
                sd = spread_profile[i]
                v = mu + row_shift + rng.gauss(0, sd)
                # нестационарность: в зоне резкого падения допускаем больше индивидуального сдвига
                if i in (3,4):
                    v += rng.uniform(-10, 10)
                v = max(0, int(round(v)))
                if prev is not None and v > prev - min_drop:
                    v = max(0, prev - rng.randint(min_drop, min_drop+4))
            vals.append(v)
            prev = v
        rows.append(vals)
    # Мягкая подгонка средних по циклам к профилю, сохраняя убывание по строкам.
    for _ in range(80):
        changed=False
        avgs=[avg([row[c] for row in rows]) for c in range(8)]
        for c in range(7):
            diff=int(round((mean_profile[c]-avgs[c])*n))
            attempts=0
            while diff != 0 and attempts < 200:
                attempts += 1
                idx = rng.randrange(n)
                step = 1 if diff > 0 else -1
                newv = rows[idx][c] + step
                left_ok = (c == 0 or rows[idx][c-1] >= newv)
                right_ok = (c == 6 or newv >= rows[idx][c+1])
                if newv >= 0 and left_ok and right_ok:
                    rows[idx][c] = newv
                    diff -= step
                    changed=True
                else:
                    break
        if not changed:
            break
    for row in rows:
        row[-1] = 0
    return rows

def gen_series_with_avg(n, target, spread, seed):
    rng = random.Random(seed)
    vals=[]
    for _ in range(n):
        vals.append(round(rng.uniform(target-spread, target+spread), 1))
    # центрируем к нужному среднему, затем корректируем последнее значение
    delta = target - avg(vals)
    vals=[round(v+delta,1) for v in vals]
    vals[-1]=round(target*n - sum(vals[:-1]),1)
    return vals

def integral_s(row):
    """S рассчитывается из фактической строки таблицы.

    По реальным протоколам S соответствует 0,75 от суммы значений по 8 циклам.
    Пример из протокола: 568+509+388+264+56+45+14+0 = 1844; 1844*0,75 = 1383.
    """
    return int(round(sum(row) * 0.75))


def _make_control_profile(rng):
    """Создает новую контрольную кривую для каждого протокола.

    Контроль не является стационарной фиксированной линией. Здесь используется
    статистическая модель по присланным реальным протоколам: меняются стартовое
    значение, темп падения в циклах 2-4, глубина провала в циклах 5-7.
    """
    start = rng.uniform(560, 635)
    c2 = start * rng.uniform(0.80, 0.89)
    c3 = c2 * rng.uniform(0.73, 0.84)
    c4 = c3 * rng.uniform(0.63, 0.74)

    # Хвост кривой специально генерируется отдельно: в реальных данных после 4-го
    # цикла происходит резкое падение, но его глубина меняется от протокола к протоколу.
    c5 = rng.uniform(45, 76)
    c6 = rng.uniform(30, min(55, c5 - 2)) if c5 > 34 else rng.uniform(18, 30)
    c7 = rng.uniform(8, min(22, c6 - 2)) if c6 > 12 else rng.uniform(3, 8)
    prof = [start, c2, c3, c4, c5, c6, c7, 0]
    for i in range(1, 7):
        if prof[i] >= prof[i-1]:
            prof[i] = max(0, prof[i-1] - rng.uniform(3, 15))
    prof[-1] = 0
    return prof


def _make_experience_profile(rng, k_profile):
    """Опыт строится от конкретного контроля, а не от постоянного шаблона."""
    # В начале опыт обычно близок к контролю или ниже/выше в пределах разумного.
    # В области 4-6 циклов допускается более выраженное отличие.
    ratios = [
        rng.uniform(0.82, 1.08),
        rng.uniform(0.84, 1.05),
        rng.uniform(0.86, 1.10),
        rng.uniform(0.55, 0.82),
        rng.uniform(1.15, 1.95),
        rng.uniform(0.45, 0.95),
        rng.uniform(0.35, 1.10),
        0,
    ]
    op = [k_profile[i] * ratios[i] for i in range(8)]
    # Опыт тоже не должен расти от цикла к циклу. Если после коэффициентов появляется
    # рост, мягко ограничиваем следующую точку.
    for i in range(1, 7):
        if op[i] >= op[i-1]:
            op[i] = max(0, op[i-1] - rng.uniform(4, 22))
    op[-1] = 0
    return op


def make_data(num, date, sample, bull, target_it, reg_number='', thaw_volume='1,0'):
    target_it = float(target_it)
    # Стабильный seed: одинаковые входные данные дают одинаковый протокол, но
    # разные номера/шифры/даты дают новые контрольные кривые.
    import hashlib
    seed_src = f'{num}|{date}|{sample}|{bull}|{target_it}'.encode('utf-8')
    seed = int(hashlib.sha256(seed_src).hexdigest()[:8], 16)
    rng = random.Random(seed)

    # Контроль каждый раз генерируется заново по статистической модели.
    k_profile = _make_control_profile(rng)
    op_profile = _make_experience_profile(rng, k_profile)

    kn = make_monotone_replicates(k_profile, 5, seed + 101, [28,22,22,16,8,6,3,0])
    op = make_monotone_replicates(op_profile, 4, seed + 202, [30,24,22,16,9,6,3,0])

    k_avg = [round(avg([r[i] for r in kn]),1) for i in range(8)]
    op_avg = [round(avg([r[i] for r in op]),1) for i in range(8)]

    # It соответствует отношению T опыта к T контроля. При заведомо экстремальном It
    # программа сохраняет введенное значение, но в JSON добавляет предупреждение.
    k_t_avg = round(rng.uniform(14.2, 15.8), 1)
    op_t_avg = round(k_t_avg * target_it / 100.0, 1)
    kn_t = gen_series_with_avg(5, k_t_avg, rng.uniform(0.6, 1.4), seed + 303)
    op_spread = rng.uniform(0.5, 1.3) if 80 <= target_it <= 130 else max(0.3, op_t_avg * 0.015)
    op_t = gen_series_with_avg(4, op_t_avg, op_spread, seed + 404)

    kn_s = [integral_s(r) for r in kn]
    op_s = [integral_s(r) for r in op]
    k_s_avg = round(avg(kn_s),1)
    op_s_avg = round(avg(op_s),1)
    is_ = round(op_s_avg / k_s_avg * 100, 1) if k_s_avg else 0

    rules_check = {
        'kn_rows_monotone': all(all(row[i] >= row[i+1] for i in range(7)) and row[7] == 0 for row in kn),
        'op_rows_monotone': all(all(row[i] >= row[i+1] for i in range(7)) and row[7] == 0 for row in op),
        'control_profile_is_generated_each_protocol': True,
        'control_profile_values': [round(v, 1) for v in k_profile],
        'experience_profile_values': [round(v, 1) for v in op_profile],
        's_formula': 'S = round(0.75 * sum(cycles 1..8))',
        's_from_table': True,
        'plot_from_table_averages': True,
        'it_from_t_average': round(op_t_avg / k_t_avg * 100, 1) if k_t_avg else 0,
    }
    if not (80 <= target_it <= 130):
        rules_check['warning'] = 'Введенный It вне типового диапазона реальных примеров; T опыта будет математически согласован, но может выглядеть нетипично.'

    return {
        'num': num, 'action_date': ru_date(date), 'sn': sample, 'registration_number': reg_number,
        'bull': bull, 'thaw_volume': thaw_volume, 'kn': kn, 'op': op,
        'kn_t': kn_t, 'kn_s': kn_s, 'op_t': op_t, 'op_s': op_s,
        'k_avg': k_avg, 'op_avg': op_avg,
        'k_t_avg': k_t_avg, 'op_t_avg': op_t_avg, 'k_s_avg': k_s_avg, 'op_s_avg': op_s_avg,
        'k_t_var': round(cv(kn_t),1), 'op_t_var': round(cv(op_t),1),
        'k_s_var': round(cv(kn_s),1), 'op_s_var': round(cv(op_s),1),
        'op_nums': [10,11,12,13], 'it': round(target_it, 1), 'is': is_,
        'generation_rules': rules_check,
        'plot_source': 'График построен из k_avg/op_avg, рассчитанных по сгенерированной таблице kn/op.'
    }

def _font(size, bold=False):
    if ImageFont is None:
        return None
    candidates = []
    if os.name == 'nt':
        candidates += [r'C:\Windows\Fonts\timesbd.ttf' if bold else r'C:\Windows\Fonts\times.ttf',
                       r'C:\Windows\Fonts\arialbd.ttf' if bold else r'C:\Windows\Fonts\arial.ttf']
    candidates += ['/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf',
                   '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']
    for c in candidates:
        try:
            if c and Path(c).exists(): return ImageFont.truetype(c, size)
        except Exception:
            pass
    return ImageFont.load_default()

def _smooth_points(points, steps=18):
    # Catmull-Rom сглаживание, чтобы график выглядел как в исходнике
    if len(points) < 3: return points
    out=[]
    for i in range(len(points)-1):
        p0 = points[max(i-1,0)]; p1=points[i]; p2=points[i+1]; p3=points[min(i+2,len(points)-1)]
        for s in range(steps):
            t=s/steps; t2=t*t; t3=t2*t
            x=0.5*((2*p1[0])+(-p0[0]+p2[0])*t+(2*p0[0]-5*p1[0]+4*p2[0]-p3[0])*t2+(-p0[0]+3*p1[0]-3*p2[0]+p3[0])*t3)
            y=0.5*((2*p1[1])+(-p0[1]+p2[1])*t+(2*p0[1]-5*p1[1]+4*p2[1]-p3[1])*t2+(-p0[1]+3*p1[1]-3*p2[1]+p3[1])*t3)
            out.append((x,y))
    out.append(points[-1])
    return out

def _draw_antialias_line(base_img, points, fill, width=5):
    # Рисуем линии на увеличенном холсте для сглаживания.
    scale = 3
    layer = Image.new('RGBA', (base_img.size[0]*scale, base_img.size[1]*scale), (255,255,255,0))
    d = ImageDraw.Draw(layer)
    pts = [(int(x*scale), int(y*scale)) for x,y in points]
    if len(pts) >= 2:
        d.line(pts, fill=fill+(255,), width=width*scale, joint='curve')
    layer = layer.resize(base_img.size, Image.Resampling.LANCZOS)
    base_img.paste(Image.alpha_composite(base_img.convert('RGBA'), layer).convert('RGB'))


def _draw_dashed_polyline(base_img, points, fill, width=5, dash=28, gap=16):
    """Непрерывный пунктир по всей кривой, без сброса рисунка на каждом маленьком отрезке."""
    scale = 3
    layer = Image.new('RGBA', (base_img.size[0]*scale, base_img.size[1]*scale), (255,255,255,0))
    d = ImageDraw.Draw(layer)
    on = True
    remaining = dash
    if len(points) < 2:
        return
    for p0, p1 in zip(points, points[1:]):
        x0,y0 = p0; x1,y1 = p1
        seg_len = math.hypot(x1-x0, y1-y0)
        if seg_len <= 0:
            continue
        pos = 0.0
        while pos < seg_len:
            step = min(remaining, seg_len-pos)
            a = pos/seg_len
            b = (pos+step)/seg_len
            xa = x0 + (x1-x0)*a; ya = y0 + (y1-y0)*a
            xb = x0 + (x1-x0)*b; yb = y0 + (y1-y0)*b
            if on:
                d.line([(int(xa*scale), int(ya*scale)), (int(xb*scale), int(yb*scale))], fill=fill+(255,), width=width*scale)
            pos += step
            remaining -= step
            if remaining <= 1e-6:
                on = not on
                remaining = dash if on else gap
    layer = layer.resize(base_img.size, Image.Resampling.LANCZOS)
    base_img.paste(Image.alpha_composite(base_img.convert('RGBA'), layer).convert('RGB'))


def _draw_line(draw, points, fill, width=2):
    """Резервная обычная ломаная линия."""
    if len(points) >= 2:
        draw.line([(round(x), round(y)) for x, y in points], fill=fill, width=width, joint='curve')


def _draw_dashed_line(draw, points, fill, width=2, dash=7, gap=5):
    """Резервный пунктир с постоянной длиной штрихов по всей ломаной."""
    if len(points) < 2:
        return
    on = True
    remain = dash
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        seg = math.hypot(x1 - x0, y1 - y0)
        if seg <= 0:
            continue
        pos = 0.0
        while pos < seg:
            step = min(remain, seg - pos)
            a = pos / seg
            b = (pos + step) / seg
            xa = x0 + (x1 - x0) * a
            ya = y0 + (y1 - y0) * a
            xb = x0 + (x1 - x0) * b
            yb = y0 + (y1 - y0) * b
            if on:
                draw.line([(round(xa), round(ya)), (round(xb), round(yb))], fill=fill, width=width)
            pos += step
            remain -= step
            if remain <= 1e-9:
                on = not on
                remain = dash if on else gap


def _draw_polyline_aa(img, points, fill, width=2, dash=None, gap=None):
    """Антиалиасная ломаная без сглаживания данных.

    Важно: точки не интерполируются и не сглаживаются. Линия проходит строго через
    координаты, рассчитанные из средних значений таблицы. Высокое разрешение нужно
    только для визуального совпадения толщины/краев линии с исходным графиком.
    """
    if len(points) < 2:
        return
    scale = 4
    layer = Image.new('RGBA', (img.size[0]*scale, img.size[1]*scale), (255,255,255,0))
    d = ImageDraw.Draw(layer)
    col = fill + (255,)
    w = int(round(width*scale))

    def draw_segment(a, b):
        d.line([(int(round(a[0]*scale)), int(round(a[1]*scale))),
                (int(round(b[0]*scale)), int(round(b[1]*scale)))], fill=col, width=w)

    if dash is None:
        for a,b in zip(points, points[1:]):
            draw_segment(a,b)
    else:
        on = True
        remain = float(dash)
        for (x0,y0),(x1,y1) in zip(points, points[1:]):
            seg = math.hypot(x1-x0, y1-y0)
            if seg <= 0:
                continue
            pos = 0.0
            while pos < seg:
                step = min(remain, seg-pos)
                a = pos/seg
                b = (pos+step)/seg
                p0 = (x0+(x1-x0)*a, y0+(y1-y0)*a)
                p1 = (x0+(x1-x0)*b, y0+(y1-y0)*b)
                if on:
                    draw_segment(p0,p1)
                pos += step
                remain -= step
                if remain <= 1e-9:
                    on = not on
                    remain = float(dash if on else gap)
    layer = layer.resize(img.size, Image.Resampling.LANCZOS)
    img.alpha_composite(layer)


def make_plot_png(path, k_avg, op_avg):
    """Строит график строго в масштабе и оформлении оригинального embedded PNG 640x480.

    Основа графика (оси, стрелки, подписи, сетка, легенда) взята из исходного реального протокола
    и сохранена как plot_background.png. Поверх нее наносятся только новые линии, рассчитанные из
    сгенерированной таблицы Кн/Оп.
    """
    if Image is None:
        raise RuntimeError('Не установлен Pillow. Для сборки EXE запустите СОБРАТЬ_EXE_ОДИН_РАЗ.bat — он установит зависимости.')

    bg_path = app_dir() / 'plot_background.png'
    if bg_path.exists():
        img = Image.open(bg_path).convert('RGB')
    else:
        # Резервный режим: если фон не найден, создаем его программно.
        W, H = 640, 480
        img = Image.new('RGB', (W, H), 'white')
        dr0 = ImageDraw.Draw(img)
        f_axis = _font(20, True)
        f_tick = _font(15, False)
        f_leg = _font(15, False)
        dr0.text((16, 16), 'm, у.е.', fill=(0, 0, 0), font=f_axis)
        dr0.text((562, 421), 't, цикл', fill=(0, 0, 0), font=f_axis)
        left0, right0, ytop0, ybottom0, y600_0 = 60, 545, 49, 414, 115
        yscale0 = (ybottom0 - y600_0) / 600.0
        for val in [600, 450, 300, 150, 0]:
            y = ybottom0 - val * yscale0
            _draw_dashed_line(dr0, [(left0, y), (right0, y)], (130, 130, 130), width=1, dash=3, gap=3)
            dr0.text((24, y - 9), str(val), fill=(0, 0, 0), font=f_tick)
        _draw_dashed_line(dr0, [(left0, ytop0), (right0, ytop0)], (130, 130, 130), width=1, dash=3, gap=3)
        for xv in range(1, 13):
            x = left0 + (right0 - left0) * (xv - 1) / 11.0
            _draw_dashed_line(dr0, [(x, ytop0), (x, ybottom0)], (130, 130, 130), width=1, dash=3, gap=3)
            dr0.text((x - 5, ybottom0 + 7), str(xv), fill=(0, 0, 0), font=f_tick)
        dr0.line([(left0, ybottom0), (right0, ybottom0)], fill=(0, 0, 0), width=1)
        dr0.line([(left0, ybottom0), (left0, ytop0)], fill=(0, 0, 0), width=1)
        dr0.polygon([(right0 + 1, ybottom0 - 8), (right0 + 1, ybottom0 + 8), (right0 + 14, ybottom0)], fill=(0, 0, 0))
        dr0.polygon([(left0 - 8, ytop0 + 14), (left0 + 8, ytop0 + 14), (left0, ytop0 + 1)], fill=(0, 0, 0))
        dr0.text((235, 444), 'Контроль', fill=(0, 0, 0), font=f_leg)
        dr0.text((371, 444), 'Опыт', fill=(0, 0, 0), font=f_leg)

    img = img.convert('RGBA')
    dr = ImageDraw.Draw(img)

    # Координаты/масштаб точно соответствуют исходному графику 640x480:
    # X = циклы 1..12, фактические точки 1..8; Y: 0 на 414 px, 600 на 115 px.
    left, right = 60, 545
    y_bottom, y600 = 414, 115
    y_scale = (y_bottom - y600) / 600.0

    blue = (74, 126, 190)
    orange = (226, 139, 62)

    def x_from_cycle(cycle):
        return left + (right - left) * (cycle - 1) / 11.0

    def y_from_value(v):
        return y_bottom - float(v) * y_scale

    kpts = [(x_from_cycle(i + 1), y_from_value(v)) for i, v in enumerate(k_avg)]
    opts = [(x_from_cycle(i + 1), y_from_value(v)) for i, v in enumerate(op_avg)]

    # Начертание как в оригинале реального протокола:
    # Контроль — тонкий синий пунктир, Опыт — тонкая оранжевая сплошная линия.
    # Линии проходят строго через 8 точек средних значений таблицы (без сглаживания данных).
    _draw_polyline_aa(img, kpts, blue, width=2, dash=6, gap=5)
    _draw_polyline_aa(img, opts, orange, width=2, dash=None, gap=None)

    # Легенда: сохраняем текст с фона, перерисовываем только образцы линий с теми же параметрами.
    _draw_polyline_aa(img, [(195, 453), (225, 453)], blue, width=2, dash=6, gap=5)
    _draw_polyline_aa(img, [(330, 453), (360, 453)], orange, width=2, dash=None, gap=None)

    img.convert('RGB').save(path)
    return {
        'x_cycle_1': left, 'x_cycle_12': right,
        'y_value_0': y_bottom, 'y_value_600': y600,
        'control_points_px': [[round(x, 2), round(y, 2)] for x, y in kpts],
        'experience_points_px': [[round(x, 2), round(y, 2)] for x, y in opts],
        'control_values': [round(float(v), 1) for v in k_avg],
        'experience_values': [round(float(v), 1) for v in op_avg],
        'line_style': {
            'control': 'blue dashed, width 2 px, dash 6 px, gap 5 px',
            'experience': 'orange solid, width 2 px'
        }
    }

def replace_visible_text_in_xml(xml_bytes, replacements):
    import xml.etree.ElementTree as ET
    ns = {'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    for prefix, uri in [('w',ns['w']),('r','http://schemas.openxmlformats.org/officeDocument/2006/relationships'),('wp','http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'),('a','http://schemas.openxmlformats.org/drawingml/2006/main'),('pic','http://schemas.openxmlformats.org/drawingml/2006/picture')]:
        ET.register_namespace(prefix, uri)
    root = ET.fromstring(xml_bytes)
    texts = list(root.iter('{%s}t' % ns['w']))
    full = ''; mapping=[]
    for idx, el in enumerate(texts):
        txt = el.text or ''
        for off, ch in enumerate(txt): mapping.append((idx, off))
        full += txt
    occurrences=[]
    # добавляем варианты без пробелов, т.к. Word часто разбивает плейсхолдеры
    rep = dict(replacements)
    for k,v in list(replacements.items()):
        rep[k.replace(' ', '')] = v
    for key, val in rep.items():
        pos=0
        while True:
            pos = full.find(key, pos)
            if pos < 0: break
            occurrences.append((pos, pos+len(key), str(val)))
            pos += len(key)
    occurrences.sort(reverse=True)
    for start,end,repl in occurrences:
        if start >= len(mapping) or end-1 >= len(mapping): continue
        first_i, first_off = mapping[start]; last_i, last_off = mapping[end-1]
        if first_i == last_i:
            t = texts[first_i].text or ''
            texts[first_i].text = t[:first_off] + repl + t[last_off+1:]
        else:
            t = texts[first_i].text or ''
            texts[first_i].text = t[:first_off] + repl
            for i in range(first_i+1, last_i): texts[i].text = ''
            t = texts[last_i].text or ''
            texts[last_i].text = t[last_off+1:]
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)

def create_docx(outdocx, d, png_path, template_path=None):
    template_path = template_path or (app_dir() / 'tox_template.docx')
    replacements = {
        '{{ num }}': d['num'], '{{ action_date }}': d['action_date'], '{{ sn }}': d['sn'], '{{ bull }}': d['bull'],
        '{{ it }}': d['it'], '{{ is }}': d['is'], '{{ k_t_avg }}': d['k_t_avg'], '{{ op_t_avg }}': d['op_t_avg'],
        '{{ k_s_avg }}': d['k_s_avg'], '{{ op_s_avg }}': d['op_s_avg'], '{{ k_t_var }}': d['k_t_var'],
        '{{ op_t_var }}': d['op_t_var'], '{{ k_s_var }}': d['k_s_var'], '{{ op_s_var }}': d['op_s_var'],
    }
    # op_nums в исходном шаблоне есть 4 или 5 мест — заполняем оба варианта
    for i, v in enumerate([10,11,12,13,14]): replacements['{{ op_nums[%d] }}' % i] = v
    for r in range(5):
        for c in range(8): replacements['{{kn[%d][%d]}}' % (r,c)] = d['kn'][r][c]
    for r in range(4):
        for c in range(8): replacements['{{op[%d][%d]}}' % (r,c)] = d['op'][r][c]
    for i, v in enumerate(d['kn_t']): replacements['{{kn_t[%d]}}' % i] = v
    for i, v in enumerate(d['op_t']): replacements['{{op_t[%d]}}' % i] = v
    for i, v in enumerate(d['kn_s']): replacements['{{kn_s[%d]}}' % i] = v
    for i, v in enumerate(d['op_s']): replacements['{{op_s[%d]}}' % i] = v

    with zipfile.ZipFile(template_path, 'r') as zin, zipfile.ZipFile(outdocx, 'w', zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == 'word/document.xml':
                data = replace_visible_text_in_xml(data, replacements)
            # заменяем исходную картинку графика на график, построенный по сгенерированной таблице
            if item.filename.startswith('word/media/') and item.filename.lower().endswith(('.png','.jpg','.jpeg')):
                with open(png_path, 'rb') as f: data = f.read()
            zout.writestr(item, data)

def run_generate(num, date, sample, bull, target_it, outdir):
    outdir = Path(outdir); outdir.mkdir(parents=True, exist_ok=True)
    d = make_data(num, date, sample, bull, target_it)
    safe = ''.join(ch if ch.isalnum() or ch in ('_','-') else '_' for ch in str(sample))[:50]
    png = outdir / f'График_токсичность_{num}_{safe}.png'
    docx = outdir / f'Протокол_токсичность_{num}_{safe}.docx'
    js = outdir / f'Расчеты_токсичность_{num}_{safe}.json'
    plot_check = make_plot_png(png, d['k_avg'], d['op_avg'])
    d['plot_check'] = plot_check
    create_docx(docx, d, png, app_dir() / 'tox_template.docx')
    with open(js,'w',encoding='utf-8') as f: json.dump(d, f, ensure_ascii=False, indent=2)
    # Отдельный контрольный CSV: каждая точка графика соответствует средним из таблицы.
    csv_path = outdir / f'Проверка_графика_{num}_{safe}.csv'
    with open(csv_path, 'w', encoding='utf-8') as f:
        f.write('cycle;k_avg;op_avg;k_x;k_y;op_x;op_y\n')
        for i in range(8):
            kp = plot_check['control_points_px'][i]
            op = plot_check['experience_points_px'][i]
            f.write(f"{i+1};{d['k_avg'][i]};{d['op_avg'][i]};{kp[0]};{kp[1]};{op[0]};{op[1]}\n")
    return docx, js, png

def gui():
    root=tk.Tk(); root.title('Генератор протокола токсичности'); root.geometry('560x390')
    vals={}
    defaults={'num':'1','date':datetime.date.today().strftime('%d.%m.%Y'),'sample':'ТСЛ-26-000001','bull':'Кэнон-М','it':'103.4'}
    row=0
    for key,label in [('num','Номер протокола'),('date','Дата испытания'),('sample','Шифр образца'),('bull','Кличка быка'),('it','Индекс токсичности It, %')]:
        ttk.Label(root,text=label).grid(row=row,column=0,sticky='w',padx=12,pady=8)
        e=ttk.Entry(root,width=38); e.insert(0,defaults[key]); e.grid(row=row,column=1,padx=12,pady=8); vals[key]=e; row+=1
    outvar=tk.StringVar(value=str(Path.cwd()/'output'))
    ttk.Label(root,text='Папка вывода').grid(row=row,column=0,sticky='w',padx=12,pady=8)
    ttk.Entry(root,textvariable=outvar,width=38).grid(row=row,column=1,padx=12,pady=8); row+=1
    def choose():
        d=filedialog.askdirectory()
        if d: outvar.set(d)
    ttk.Button(root,text='Выбрать папку',command=choose).grid(row=row,column=1,sticky='w',padx=12,pady=4); row+=1
    ttk.Label(root,text='График строится по средним значениям из сгенерированной таблицы Кн/Оп.', foreground='gray').grid(row=row,column=0,columnspan=2,pady=4); row+=1
    def go():
        try:
            docx, js, png = run_generate(vals['num'].get(), vals['date'].get(), vals['sample'].get(), vals['bull'].get(), float(vals['it'].get().replace(',','.')), outvar.get())
            messagebox.showinfo('Готово', f'Созданы файлы:\n{docx}\n{png}\n{js}')
            try: os.startfile(Path(docx).parent)
            except Exception: pass
        except Exception as e:
            messagebox.showerror('Ошибка', str(e))
    ttk.Button(root,text='Сформировать Word-протокол',command=go).grid(row=row,column=0,columnspan=2,pady=18)
    root.mainloop()

if __name__ == '__main__':
    if len(sys.argv) >= 6:
        out = sys.argv[6] if len(sys.argv)>6 else 'output'
        docx, js, png = run_generate(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], float(sys.argv[5].replace(',','.')), out)
        print('Создано:', docx)
        print('График:', png)
    else:
        if tk is None:
            print('Не найден tkinter. Запуск: python toxicity_generator.py NUM DATE SAMPLE BULL IT [OUTDIR]')
        else:
            gui()
