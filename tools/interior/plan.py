r"""План комнаты сверху + проверка правил дизайна (без Blender, за секунду).

Запуск:  python tools/interior/plan.py tools/interior/layouts/living.json [картинка.png]
Печатает нарушения, рисует план: предметы по паспортам (library.json), стрелка — куда смотрит перёд,
красным — нарушения. Правила — из «База — дизайн гостиной» (D:\pol-ai\vault).
"""
import json, math, sys
from pathlib import Path

import cv2
import numpy as np

LIB = json.loads(Path(__file__).with_name('library.json').read_text(encoding='utf-8'))
SEATS = {'sofa', 'armchair', 'chair'}


def rect(it):
    """Углы предмета на плане (x, y), перёд — сторона, куда смотрит facing."""
    sx, sy = LIB[it['key']]['size'][:2]                    # в паспорте перёд смотрит в -Y: ширина sx, глубина sy
    if LIB[it['key']]['cat'] == 'plant': sx = sy = min(sx, sy) * 0.35   # у растения на полу только горшок, листья над мебелью — можно
    a = math.radians(it['facing'] + 90)                    # поворот от «перёд в -Y» к facing
    c, s = math.cos(a), math.sin(a)
    return [(it['x'] + c * px - s * py, it['y'] + s * px + c * py) for px, py in
            ((-sx / 2, -sy / 2), (sx / 2, -sy / 2), (sx / 2, sy / 2), (-sx / 2, sy / 2))]


def fdir(it):
    a = math.radians(it['facing']); return math.cos(a), math.sin(a)


def gap(a, b):
    """Наименьшее расстояние между двумя прямоугольниками (0 — касаются/пересекаются)."""
    pa, pb = np.array(rect(a)), np.array(rect(b))
    def inside(p, poly):
        return cv2.pointPolygonTest(poly.astype(np.float32).reshape(-1, 1, 2), (float(p[0]), float(p[1])), False) >= 0
    if any(inside(p, pb) for p in pa) or any(inside(p, pa) for p in pb): return 0.0
    def seg(p, a_, b_):
        ab = b_ - a_; t = np.clip(np.dot(p - a_, ab) / max(np.dot(ab, ab), 1e-9), 0, 1); return np.linalg.norm(p - (a_ + t * ab))
    return min(min(seg(p, pb[i], pb[(i + 1) % 4]) for p in pa for i in range(4)),
               min(seg(p, pa[i], pa[(i + 1) % 4]) for p in pb for i in range(4)))


def wall_gap(it, room):
    xs, ys = zip(*rect(it)); return {'left': min(xs), 'right': room['w'] - max(xs), 'front': min(ys), 'back': room['d'] - max(ys)}


def check(L):
    room, items, bad = L['room'], L['items'], []
    by = lambda cat: [i for i in items if LIB[i['key']]['cat'] == cat]
    for it in items:                                       # в комнате
        wg = wall_gap(it, room)
        if min(wg.values()) < -0.01: bad.append((it, f"{it['key']}: вылезает за стену ({min(wg, key=wg.get)})"))
    for i, a in enumerate(items):                          # не пересекаются
        for b in items[i + 1:]:
            if gap(a, b) == 0: bad.append((a, f"{a['key']} и {b['key']} пересекаются"))
    for s in by('sofa'):
        wg = wall_gap(s, room); back = {(-90): 'back', 90: 'front', 0: 'left', 180: 'right'}.get(round(s['facing']) % 360 - (360 if round(s['facing']) % 360 > 180 else 0))
        if back and wg[back] > 0.12: bad.append((s, f"диван отстоит от стены на {wg[back]*100:.0f} см (норма до 10)"))
        for t in by('coffee_table'):
            g = gap(s, t)
            if not 0.35 <= g <= 0.46: bad.append((t, f"столик от дивана {g*100:.0f} см (норма 35–46)"))
            if abs(t['x'] - s['x']) > 0.1 and abs(round(s['facing']) % 180) == 90: bad.append((t, f"столик не по центру дивана ({(t['x']-s['x'])*100:+.0f} см)"))
            th = LIB[t['key']].get('top_h'); sh = LIB[s['key']].get('seat_h')
            if th and sh and th < sh - 0.12: bad.append((t, f"столик низкий: {th*100:.0f} см при сиденье {sh*100:.0f} (норма: сиденье −2…5 см)"))
        for l in by('floor_lamp'):
            if gap(s, l) > 0.30: bad.append((l, f"торшер далеко от дивана: {gap(s, l)*100:.0f} см (норма 15–30)"))
    tables = by('coffee_table')
    for c in by('armchair'):
        if tables:
            t = min(tables, key=lambda t: math.dist((c['x'], c['y']), (t['x'], t['y'])))
            want = math.degrees(math.atan2(t['y'] - c['y'], t['x'] - c['x'])); d = (c['facing'] - want + 180) % 360 - 180
            if abs(d) > 35: bad.append((c, f"кресло смотрит мимо столика на {abs(d):.0f}° (норма до 30)"))
            g = gap(c, t)
            if g > 0.6: bad.append((c, f"кресло далеко от столика: {g*100:.0f} см"))
    for w in L.get('windows', []):                         # высокое у окна не закрывает свет
        for it in items:
            if LIB[it['key']]['size'][2] > w['sill'] + 0.3 and w['wall'] == 'left' and wall_gap(it, room)['left'] < 0.4:
                ys = [p[1] for p in rect(it)]
                if max(ys) > w['from'] + 0.1 and min(ys) < w['to'] - 0.1: bad.append((it, f"{it['key']} закрывает окно"))
    cam = L.get('camera')                                  # проход: от камеры/двери до зоны — 90 см
    zone = [i for i in items if LIB[i['key']]['cat'] in SEATS | {'coffee_table'}]
    if cam and zone:
        g = min(math.dist((cam['x'], cam['y']), p) for z in zone for p in rect(z))
        if g < 0.9: bad.append((zone[0], f"мало места у входа/камеры: {g*100:.0f} см"))
    return bad


def draw(L, bad, out):
    room = L['room']; S = 120; m = 40
    W, H = int(room['w'] * S) + 2 * m, int(room['d'] * S) + 2 * m
    img = np.full((H, W, 3), 255, np.uint8)
    P = lambda x, y: (int(m + x * S), int(H - m - y * S))   # y вверх = к дальней стене
    cv2.rectangle(img, P(0, 0), P(room['w'], room['d']), (60, 60, 60), 3)
    for w in L.get('windows', []):
        if w['wall'] == 'left': cv2.line(img, P(0, w['from']), P(0, w['to']), (230, 160, 60), 7)
    for dr in L.get('doors', []):
        if dr['wall'] == 'right': cv2.line(img, P(room['w'], dr['from']), P(room['w'], dr['to']), (90, 140, 200), 7)
    if L.get('camera'): cv2.circle(img, P(L['camera']['x'], L['camera']['y']), 8, (0, 0, 0), -1)
    badset = {id(b[0]) for b in bad}
    for it in L['items']:
        pts = np.array([P(*p) for p in rect(it)], np.int32)
        col = (60, 60, 220) if id(it) in badset else (90, 90, 90)
        cv2.fillPoly(img, [pts], (235, 235, 235)); cv2.polylines(img, [pts], True, col, 2)
        fx, fy = fdir(it); c = P(it['x'], it['y'])
        if LIB[it['key']]['cat'] in SEATS | {'tv_stand', 'ottoman'}:
            tip = P(it['x'] + fx * 0.35, it['y'] + fy * 0.35)
            cv2.arrowedLine(img, c, tip, col, 2, tipLength=0.3)
        cv2.putText(img, it['key'], (c[0] - 40, c[1] - 6), 0, 0.4, (0, 0, 0), 1)
    cv2.imencode('.png', img)[1].tofile(out)


if __name__ == '__main__':
    L = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    bad = check(L)
    for k, (_, msg) in enumerate(bad):
        print(f'{k + 1}. {msg}')
    print('нарушений:', len(bad))
    draw(L, bad, sys.argv[2] if len(sys.argv) > 2 else str(Path(sys.argv[1]).with_suffix('.png')))
