r"""Расстановщик гостиной по правилам (База — дизайн гостиной): комната + окна/двери/камера → layout.json.

Запуск:  python tools/interior/arrange.py <комната.json> <выход.json> [--set ключ=значение ...]
комната.json: room, windows, doors, camera (как в layouts/living.json, без items) и необязательно "set" —
какие модели брать: {"sofa": "sofa_beige", "coffee_table": "coffee_glass", ...}.
После расстановки сразу запускает проверку plan.py.
"""
import json, math, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import plan

LIB = plan.LIB
DEFAULT_SET = {'sofa': 'sofa_beige', 'coffee_table': 'coffee_glass', 'armchair': 'armchair_cognac',
               'floor_lamp': 'lamp_oslo', 'plant_big': 'plant_big', 'plant_small': 'plant_small'}
# правила (см. «База — дизайн гостиной»)
SOFA_WALL_GAP = 0.05      # диван у стены вплотную / 5 см
TABLE_GAP = 0.40          # столик — диван: 35–46 см
CHAIR_TABLE_GAP = 0.35    # кресло — столик
LAMP_GAP = 0.20           # торшер у подлокотника: 15–30 см
CORNER_GAP = 0.08


def size(key):
    return LIB[key]['size']


def aim_camera(R):
    """Урок ref3: камера смотрит вдоль комнаты на дальнюю стену (окно), почти по центру — задаём ДО расстановки."""
    W, D = R['room']['w'], R['room']['d']
    cam = dict(R.get('camera') or {'x': W - 0.4, 'y': 0.35})
    cam.setdefault('look', [W * 0.55, D * 0.95, 0.75])
    return {**R, 'camera': cam}


def arrange(R):
    R = aim_camera(R) if R.get('scheme') == 'side_tv' else R
    if R.get('scheme') == 'side_tv': return arrange_side_tv(R)
    room, S = R['room'], {**DEFAULT_SET, **R.get('set', {})}
    W, D = room['w'], room['d']
    cam = R.get('camera', {'x': W / 2, 'y': 0})
    win = R.get('windows', [])
    items = []
    # 1. диван — к стене напротив камеры (дальняя стена y = D), спинкой к стене, перёд к камере
    sw, sd = size(S['sofa'])[:2]
    win_left = any(w['wall'] == 'left' for w in win)
    # по центру стены, но не вплотную к окну: сдвиг от окна на 10% ширины, если окно на соседней стене
    sx = W / 2 + (0.1 * W if win_left else 0)
    sx = min(max(sx, sw / 2 + 0.6), W - sw / 2 - 0.6)       # место по бокам: торшер/растение — 60 см
    sy = D - SOFA_WALL_GAP - sd / 2
    items.append({'key': S['sofa'], 'x': round(sx, 3), 'y': round(sy, 3), 'facing': -90})
    # 2. столик — по центру дивана, 40 см перед ним
    tw, td = size(S['coffee_table'])[:2]
    ty = sy - sd / 2 - TABLE_GAP - td / 2
    items.append({'key': S['coffee_table'], 'x': round(sx, 3), 'y': round(ty, 3), 'facing': -90})
    # 3. кресло — сбоку от столика со стороны окна (свет на читающего), развёрнуто к столику
    cw, cd = size(S['armchair'])[:2]
    side = -1 if win_left else 1
    cx = sx + side * (tw / 2 + CHAIR_TABLE_GAP + cd / 2)
    cy = ty - 0.15                                          # чуть ближе к камере — видно лицом
    cx = min(max(cx, cw / 2 + 0.15), W - cw / 2 - 0.15)
    face = math.degrees(math.atan2(ty - cy, sx - cx))       # на столик; разворот к дивану даёт сдвиг cy к камере
    items.append({'key': S['armchair'], 'x': round(cx, 3), 'y': round(cy, 3), 'facing': round(face, 1)})
    # 4. торшер — у подлокотника с другой стороны от кресла
    lw = size(S['floor_lamp'])[0]
    # сначала с другой стороны от кресла; если там обрезан кадром или мешает — у второго подлокотника (урок прогона 4)
    for sd_ in (-side, side):
        lx = sx + sd_ * (sw / 2 + LAMP_GAP + lw / 2)
        lamp = {'key': S['floor_lamp'], 'x': round(lx, 3), 'y': round(D - lw / 2 - 0.1, 3), 'facing': -90}
        trial = {k: v for k, v in R.items() if k != 'set'} | {'items': items + [lamp]}
        if not any(o is lamp for o, _ in plan.check(trial)): break
    items.append(lamp)
    # 5. растения — в углы у дальней стены: большое ближе к окну, маленькое — с другой стороны (если есть место)
    for key, near_win in ((S.get('plant_big'), True), (S.get('plant_small'), False)):
        if not key: continue
        pw = min(size(key)[:2]) * 0.35
        left = near_win == win_left
        px = pw / 2 + CORNER_GAP + 0.15 if left else W - pw / 2 - CORNER_GAP - 0.15
        it = {'key': key, 'x': round(px, 3), 'y': round(D - pw / 2 - CORNER_GAP - 0.15, 3), 'facing': -90}
        if all(plan.gap(it, o) > 0.05 for o in items):       # нет места — не ставим, а не впихиваем
            items.append(it)
    return {k: v for k, v in R.items() if k != 'set'} | {'items': items}


def best_spot(key, items, R, target, xs, ys, extra=None):
    """Перебор мест: предмет смотрит на target (x, y); берём место без нарушений плана, ближе всего к target
    (зазор ~CHAIR_TABLE_GAP). Если чисто нигде — с наименьшим числом нарушений."""
    best = None
    for x in xs:
        for y in ys:
            it = {'key': key, 'x': round(x, 3), 'y': round(y, 3),
                  'facing': round(math.degrees(math.atan2(target[1] - y, target[0] - x)), 1), **(extra or {})}
            L = {k: v for k, v in R.items() if k != 'set'} | {'items': items + [it]}
            nbad = len(plan.check(L))                       # любое нарушение с этим местом — плохое место
            t = next((o for o in items if LIB[o['key']]['cat'] == 'coffee_table'), None)
            score = (nbad, abs(plan.gap(it, t) - CHAIR_TABLE_GAP) if t else 0)
            if best is None or score < best[0]: best = (score, it)
    return best[1] if best and best[0][0] == 0 else None    # чистого места нет — не ставим (урок ref3)


def frange(a, b, n):
    return [a + (b - a) * i / (n - 1) for i in range(n)]


def arrange_side_tv(R):
    """Схема 2 (эталон ref3): диван вдоль боковой стены лицом к ТВ на противоположной, столик между ними,
    кресло — на переднем плане у камеры под ~45° к столику (глубина кадра), растение — в светлом углу у окна."""
    room, S = R['room'], {**DEFAULT_SET, 'tv_stand': 'tv_walnut', 'tv': 'tv_42', **R.get('set', {})}
    W, D = room['w'], room['d']
    win_walls = {w['wall'] for w in R.get('windows', []) + R.get('doors', [])}
    sofa_wall = 'right' if 'right' not in win_walls else 'left'
    sg = 1 if sofa_wall == 'right' else -1                  # +1: диван справа, ТВ слева
    items = []
    sw, sd = size(S['sofa'])[:2]
    sy = min(D * 0.55, D - sw / 2 - 0.45)                   # ближе к окну, но место для торшера
    sx = (W - SOFA_WALL_GAP - sd / 2) if sg > 0 else (SOFA_WALL_GAP + sd / 2)
    items.append({'key': S['sofa'], 'x': round(sx, 3), 'y': round(sy, 3), 'facing': 180 if sg > 0 else 0, 'edge_ok': True})
    vw, vd = size(S['tv_stand'])[:2]
    vx = (0.03 + vd / 2) if sg > 0 else (W - 0.03 - vd / 2)
    items.append({'key': S['tv_stand'], 'x': round(vx, 3), 'y': round(sy, 3), 'facing': 0 if sg > 0 else 180, 'edge_ok': True})
    items.append({'key': S['tv'], 'x': round(vx, 3), 'y': round(sy, 3), 'facing': 0 if sg > 0 else 180,
                  'z': LIB[S['tv_stand']].get('top_h', 0.6)})
    tw, td = size(S['coffee_table'])[:2]
    tx = sx - sg * (sd / 2 + TABLE_GAP + tw / 2)
    items.append({'key': S['coffee_table'], 'x': round(tx, 3), 'y': round(sy, 3), 'facing': -90})
    cw, cd = size(S['armchair'])[:2]                          # кресло — передний план: между столиком и камерой
    # кресло — к столику, со стороны ТВ, но не перед камерой (перебор мест)
    ch = best_spot(S['armchair'], items, R, (tx, sy), frange(0.4, W - 0.4, 12), frange(sy - 1.6, sy - 0.3, 10))
    if ch: items.append(ch)
    # передний план (урок ref3): НИЗКИЙ предмет (пуф/табурет ≤ 0,5 м) у края кадра со стороны камеры — глубина кадра
    cam = R.get('camera', {'x': W / 2, 'y': 0.3})
    fg = S.get('foreground', 'ottoman_cognac')
    if fg:
        fx = cam['x'] + (0.55 if cam['x'] < W / 2 else -0.55); fy = cam['y'] + 0.75
        it = {'key': fg, 'x': round(fx, 3), 'y': round(fy, 3), 'facing': 60, 'foreground': True}
        if all(plan.gap(it, o) > 0.05 for o in items): items.append(it)
    lw = size(S['floor_lamp'])[0]                             # торшер — у подлокотника со стороны окна
    items.append({'key': S['floor_lamp'], 'x': round(sx, 3), 'y': round(sy + sw / 2 + LAMP_GAP + lw / 2, 3), 'facing': -90})
    key = S.get('plant_big')                                  # растение — в угол у окна со стороны ТВ
    if key:
        pw = min(size(key)[:2]) * 0.35
        px = (pw / 2 + 0.25) if sg > 0 else (W - pw / 2 - 0.25)
        it = {'key': key, 'x': round(px, 3), 'y': round(D - pw / 2 - 0.25, 3), 'facing': -90}
        if all(plan.gap(it, o) > 0.05 for o in items): items.append(it)
    return {k: v for k, v in R.items() if k != 'set'} | {'items': items}


if __name__ == '__main__':
    R = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    L = arrange(R)
    Path(sys.argv[2]).write_text(json.dumps(L, ensure_ascii=False, indent=1), encoding='utf-8')
    bad = plan.check(L)
    for k, (_, msg) in enumerate(bad):
        print(f'{k + 1}. {msg}')
    print('нарушений:', len(bad))
    plan.draw(L, bad, str(Path(sys.argv[2]).with_suffix('.png')))
