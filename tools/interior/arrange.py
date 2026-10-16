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


def arrange(R):
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
    lx = sx - side * (sw / 2 + LAMP_GAP + lw / 2)
    items.append({'key': S['floor_lamp'], 'x': round(lx, 3), 'y': round(D - lw / 2 - 0.1, 3), 'facing': -90})
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


if __name__ == '__main__':
    R = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    L = arrange(R)
    Path(sys.argv[2]).write_text(json.dumps(L, ensure_ascii=False, indent=1), encoding='utf-8')
    bad = plan.check(L)
    for k, (_, msg) in enumerate(bad):
        print(f'{k + 1}. {msg}')
    print('нарушений:', len(bad))
    plan.draw(L, bad, str(Path(sys.argv[2]).with_suffix('.png')))
