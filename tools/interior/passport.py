r"""Паспорта мебели: размер, где перёд, высота сиденья/столешницы + миниатюры для проверки глазами.

Запуск: D:\pol-ai\blender\blender.exe -b -P tools/interior/passport.py -- <папка миниатюр> [ключ ...]
Дописывает size/front/seat_h/top_h в library.json (front, заданный вручную, не трогает: "front_manual": true).
Миниатюры: <ключ>_front.png (вид спереди — перёд должен смотреть на нас) и <ключ>_top.png.
"""
import json, math, sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).parent))
import assets

argv = sys.argv[sys.argv.index('--') + 1:]
OUT = Path(argv[0]); OUT.mkdir(parents=True, exist_ok=True)
KEYS = argv[1:] or [k for k in assets.LIB if k != '_']
SEATS = {'sofa', 'armchair', 'chair'}


def bbox(objs):
    pts = [o.matrix_world @ Vector(c) for o in objs if o.type == 'MESH' for c in o.bound_box]
    return Vector([min(q[i] for q in pts) for i in range(3)]), Vector([max(q[i] for q in pts) for i in range(3)])


def auto_front(objs, mn, mx):
    """Спинка — сторона, где модель выше. Перёд — напротив. Возвращает угол, куда смотрит перёд."""
    vs = [o.matrix_world @ v.co for o in objs if o.type == 'MESH' for v in o.data.vertices]
    best = None
    sides = ((0, 0, 1), (math.pi, 0, -1), (math.pi / 2, 1, 1), (-math.pi / 2, 1, -1))
    w, d = mx.x - mn.x, mx.y - mn.y
    if w > 1.3 * d: sides = sides[2:]                         # длинный диван: спинка — на длинной стороне, не на торце
    elif d > 1.3 * w: sides = sides[:2]
    for ang, axis, sgn in sides:
        lo, hi = mn[axis], mx[axis]; band = (hi - lo) * 0.25
        zs = [v.z for v in vs if (v[axis] > hi - band if sgn > 0 else v[axis] < lo + band)]
        h = sorted(zs)[int(len(zs) * 0.95)] if zs else 0
        if best is None or h > best[0]: best = (h, ang)
    return best[1] + math.pi                                   # перёд — противоположно спинке


def seat_h(objs, mn, mx):
    """Высота сиденья: верх подушки в узком столбике по центру, на 1/4 глубины от переднего края."""
    y0 = mn.y + (mx.y - mn.y) * 0.25
    zs = [(o.matrix_world @ v.co).z for o in objs if o.type == 'MESH' for v in o.data.vertices
          if abs((o.matrix_world @ v.co).x) < 0.12 and abs((o.matrix_world @ v.co).y - y0) < 0.06]
    return round(max(zs), 3) if zs else None


def top_h(objs, first):
    """Высота столешницы: верх главной части (первая в parts), без предметов на ней."""
    main = [o for o in objs if o.type == 'MESH' and (not first or o.name.split('.')[0] == first.split('.')[0])] or objs
    return round(max((o.matrix_world @ Vector(c)).z for o in main if o.type == 'MESH' for c in o.bound_box), 3)


sc = bpy.context.scene
sc.render.engine = 'BLENDER_WORKBENCH'; sc.display.shading.light = 'STUDIO'; sc.display.shading.color_type = 'TEXTURE'
sc.render.resolution_x = sc.render.resolution_y = 360; sc.render.film_transparent = False
for o in list(bpy.data.objects): bpy.data.objects.remove(o)   # стартовая сцена: куб, свет, камера — убрать
bpy.ops.object.camera_add(); cam = bpy.context.object; sc.camera = cam; cam.data.type = 'ORTHO'
lib = json.loads(assets.LIB_PATH.read_text(encoding='utf-8'))
for key in KEYS:
    for o in list(sc.objects):
        if o != cam: bpy.data.objects.remove(o)
    p = lib[key]
    if not p.get('front_manual'): p.pop('front', None)
    assets.LIB[key] = p
    e, objs = assets.load(key)
    bpy.context.view_layer.update()
    mn, mx = bbox(objs)
    if p['cat'] in SEATS and not p.get('front_manual'):
        p['front'] = round(auto_front(objs, mn, mx), 4)
        for o in list(sc.objects):                  # перезагрузить уже повёрнутой
            if o != cam: bpy.data.objects.remove(o)
        assets.LIB[key] = p; e, objs = assets.load(key); bpy.context.view_layer.update(); mn, mx = bbox(objs)
    p['size'] = [round(v, 3) for v in (mx - mn)]
    if p['cat'] in SEATS: p['seat_h'] = seat_h(objs, mn, mx)
    if p['cat'] in ('coffee_table', 'side_table', 'tv_stand'): p['top_h'] = top_h(objs, (p.get('parts') or [None])[0])
    big = max(p['size']) * 1.15
    cam.data.ortho_scale = big
    cam.location = (0, -10, p['size'][2] / 2); cam.rotation_euler = (math.pi / 2, 0, 0)
    sc.render.filepath = str(OUT / f'{key}_front.png'); bpy.ops.render.render(write_still=True)
    cam.location = (0, 0, 10); cam.rotation_euler = (0, 0, 0)
    sc.render.filepath = str(OUT / f'{key}_top.png'); bpy.ops.render.render(write_still=True)
    print('PASS', key, p['size'], p.get('front'), p.get('seat_h'), p.get('top_h'), flush=True)
assets.LIB_PATH.write_text(json.dumps(lib, ensure_ascii=False, indent=1), encoding='utf-8')
