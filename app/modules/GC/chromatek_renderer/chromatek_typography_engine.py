from __future__ import annotations
import base64, io, json
from functools import lru_cache
from pathlib import Path
from PIL import Image



def _record_missing(detector, component, reason):
    import json
    key = f"{detector}|{component}"
    try:
        if _MISSING_PATH.exists():
            data = json.loads(_MISSING_PATH.read_text(encoding="utf-8"))
        else:
            data = {
                "id": "CHROMATEK_TYPOGRAPHY_ENGINE_HOTFIX_02B",
                "policy": "missing approved element -> omit only this label; no system-font fallback",
                "elements": {},
            }
        row = data["elements"].setdefault(
            key,
            {
                "detector": detector,
                "component": component,
                "occurrences": 0,
                "reason": reason,
            },
        )
        row["occurrences"] += 1
        row["reason"] = reason
        _MISSING_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception:
        pass


HERE=Path(__file__).resolve().parent
_MISSING_PATH = HERE / "chromatek_typography_missing_elements.json"
# CHROMATEK_TYPOGRAPHY_FIXES_01_03
PASSPORT=HERE/'chromatek_typography_passport.json'
@lru_cache(maxsize=1)
def _data(): return json.loads(PASSPORT.read_text(encoding='utf-8'))
@lru_cache(maxsize=512)
def _image(kind,key):
    row=_data()[kind][key]
    return Image.open(io.BytesIO(base64.b64decode(row['png']))).convert('L')
def _number(text,detector):
    parts=[]
    for ch in text:
        key=f'{detector}|{ch}'
        if key not in _data()['glyphs']: raise KeyError(f'Нет утверждённого глифа Хроматэк: {detector} {ch!r}')
        parts.append(_image('glyphs',key))
    gap=int(_data().get('glyph_gap_px',1)); h=max(p.height for p in parts); w=sum(p.width for p in parts)+gap*(len(parts)-1)
    out=Image.new('L',(w,h),0); x=0
    for part in parts:
        out.paste(part,(x,h-part.height),part); x+=part.width+gap
    return out
def _component(component, detector):
    components = _data()['components']

    direct_key = f'{detector}|{component}'
    if direct_key in components:
        return _image('components', direct_key)

    other_detector = 'ПИД-2' if detector == 'ПИД-1' else 'ПИД-1'
    alternate_key = f'{other_detector}|{component}'
    if alternate_key in components:
        return _image('components', alternate_key)

    raise KeyError(
        f'Нет утверждённого типографического элемента Хроматэк: '
        f'{detector} {component!r}'
    )
def draw_chromatek_label(image,*,retention_time,component,area,detector,x,bottom_y,color,min_y,min_x,max_x):
    try:
        left = _number(f"{float(retention_time):.3f}", detector)
        middle = _component(component, detector)
        right = _number(f"{float(area):.3f}", detector)
    except KeyError as exc:
        _record_missing(detector, component, str(exc))
        return False
    gap=int(_data().get('word_gap_px',3)); h=max(left.height,middle.height,right.height); w=left.width+gap+middle.width+gap+right.width
    horizontal=Image.new('L',(w,h),0); cur=0
    for part in (left,middle,right): horizontal.paste(part,(cur,h-part.height),part); cur+=part.width+gap
    vertical=horizontal.transpose(Image.Transpose.ROTATE_90); py=int(round(bottom_y))-vertical.height
    if py<min_y:
        cut=min(vertical.height-1,min_y-py); vertical=vertical.crop((0,cut,vertical.width,vertical.height)); py=min_y
    px=int(round(x-vertical.width/2)); px=max(min_x,min(px,max_x-vertical.width+1))
    layer = Image.new("RGBA", vertical.size, tuple(color) + (255,))
    layer.putalpha(vertical)
    image.alpha_composite(layer, (px, py))
    return True
