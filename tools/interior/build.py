r"""Любая комната по файлу расстановки → сцена Blender и рендер (общий построитель вместо «вшитой» гостиной).

Запуск:  D:\pol-ai\blender\blender.exe -b -P tools/interior/build.py -- <layout.json> <папка вывода> [samples] [cpu] [fast]
layout.json: room {w,d,h}, windows/doors [{wall: left|right|back|front, from, to, sill, top}], camera {x,y,z,look:[x,y,z],lens},
items [{key,x,y,facing,z}] (модели — по паспортам library.json), style {wall:[r,g,b]}.
fast — Eevee за секунды (черновик для проверки), иначе Cycles.
На выходе: room.png, floor_mask0001.png, depth0001.png, room.blend, room.json (перспектива пола для сайта).
"""
import json, math, sys
from pathlib import Path

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); import assets

argv = sys.argv[sys.argv.index('--') + 1:]
L = json.loads(Path(argv[0]).read_text(encoding='utf-8'))
OUT = Path(argv[1]); OUT.mkdir(parents=True, exist_ok=True)
SAMPLES = int(argv[2]) if len(argv) > 2 and argv[2].isdigit() else 128
CPU, FAST = 'cpu' in argv, 'fast' in argv
ASSETS = Path(r'D:\pol-ai\assets')
W, D, H = L['room']['w'], L['room']['d'], L['room'].get('h', 2.7)
RES = tuple(L.get('res', (1600, 1067)))
T = 0.12                                                   # толщина стен

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene


def mat(name, color, rough=0.6, metal=0.0, sheen=0.0, transmission=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (*color, 1); b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    if sheen: b.inputs['Sheen Weight'].default_value = sheen
    if transmission: b.inputs['Transmission Weight'].default_value = transmission
    return m


def paint(name, color):
    """Крашеная стена: лёгкая фактура валика (шум в рельефе) — без тяжёлых текстур."""
    m = mat(name, color, 0.9); nt = m.node_tree; b = nt.nodes['Principled BSDF']
    tx = nt.nodes.new('ShaderNodeTexNoise'); tx.inputs['Scale'].default_value = 90; tx.inputs['Detail'].default_value = 12
    bm = nt.nodes.new('ShaderNodeBump'); bm.inputs['Strength'].default_value = 0.04
    nt.links.new(tx.outputs['Fac'], bm.inputs['Height']); nt.links.new(bm.outputs['Normal'], b.inputs['Normal'])
    return m


M = {'wall': paint('стена', tuple(L.get('style', {}).get('wall', (0.84, 0.82, 0.78)))),
     'ceil': mat('потолок', (0.9, 0.9, 0.89), 0.95), 'floor': mat('пол белый', (0.8, 0.8, 0.8), 0.55),
     'white': mat('белая краска', (0.9, 0.9, 0.89), 0.35), 'glass': mat('стекло', (1, 1, 1), 0.0, transmission=1.0)}


WALL_OBJS = []


def box(name, size, loc, material):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.object; o.name = name; o.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    o.data.materials.append(material)
    if material is M['wall']: WALL_OBJS.append(o)
    return o


# стены: длина, как перевести (вдоль, высота, отступ наружу) в координаты, нормаль внутрь
WALLS = {'back': (W, lambda a, n: (a, D + n)), 'front': (W, lambda a, n: (a, -n)),
         'left': (D, lambda a, n: (-n, a)), 'right': (D, lambda a, n: (W + n, a))}
INWARD = {'back': (0, -1), 'front': (0, 1), 'left': (1, 0), 'right': (-1, 0)}
openings = {w: [] for w in WALLS}
for o in L.get('windows', []): openings[o['wall']].append((o['from'], o['to'], o.get('sill', 0.85), o.get('top', 2.4), 'win'))
for o in L.get('doors', []): openings[o['wall']].append((o['from'], o['to'], 0.0, o.get('top', 2.1), 'door'))


def piece(wall, a0, a1, z0, z1):
    if a1 - a0 < 1e-3 or z1 - z0 < 1e-3: return
    ln, f = WALLS[wall]; x, y = f((a0 + a1) / 2, T / 2)
    along_x = wall in ('back', 'front')
    box(f'стена {wall}', ((a1 - a0) + (2 * T if along_x and a0 == 0 and a1 == ln else 0) if along_x else T,
                          T if along_x else (a1 - a0), z1 - z0), (x, y, (z0 + z1) / 2), M['wall'])


for wall, (ln, f) in WALLS.items():
    ops = sorted(openings[wall]); a = 0.0
    for a0, a1, z0, z1, kind in ops:
        piece(wall, a, a0, 0, H); piece(wall, a0, a1, 0, z0); piece(wall, a0, a1, z1, H); a = a1
        gx, gy = f((a0 + a1) / 2, T * 0.5); along_x = wall in ('back', 'front')
        g = box('стекло', ((a1 - a0) if along_x else 0.01, 0.01 if along_x else (a1 - a0), z1 - z0), (gx, gy, (z0 + z1) / 2), M['glass'])
        g.visible_shadow = False
        for zz in (z0 + 0.03, z1 - 0.03):                  # рама: низ/верх
            box('рама', ((a1 - a0) if along_x else 0.07, 0.07 if along_x else (a1 - a0), 0.06), (gx, gy, zz), M['white'])
        for aa in (a0 + 0.03, (a0 + a1) / 2, a1 - 0.03):   # рама: стойки
            px, py = f(aa, T * 0.5)
            box('рама', (0.06 if along_x else 0.07, 0.07 if along_x else 0.06, z1 - z0), (px, py, (z0 + z1) / 2), M['white'])
        if kind == 'win':                                  # подоконник
            sx, sy = f((a0 + a1) / 2, -0.05)
            box('подоконник', ((a1 - a0) + 0.1 if along_x else 0.3, 0.3 if along_x else (a1 - a0) + 0.1, 0.03), (sx, sy, z0 - 0.015), M['white'])
    piece(wall, a, ln, 0, H)
    # плинтус (кроме дверей)
    a = 0.0
    for a0, a1, z0, *_ in sorted(openings[wall]) + [(ln, ln, 1, 0, 0)]:
        if z0 > 0.01: continue
        px, py = f((a + a0) / 2, -0.008)
        if a0 - a > 0.01: box('плинтус', ((a0 - a) if wall in ('back', 'front') else 0.016, 0.016 if wall in ('back', 'front') else (a0 - a), 0.08), (px, py, 0.04), M['white'])
        a = a1
    if a < ln:
        px, py = f((a + ln) / 2, -0.008)
        box('плинтус', ((ln - a) if wall in ('back', 'front') else 0.016, 0.016 if wall in ('back', 'front') else (ln - a), 0.08), (px, py, 0.04), M['white'])
floor = box('ПОЛ', (W, D, 0.02), (W / 2, D / 2, -0.01), M['floor']); floor.pass_index = 1
box('потолок', (W + 2 * T, D + 2 * T, 0.02), (W / 2, D / 2, H + 0.01), M['ceil'])

# ---------- отделка (урок: без неё «коробка», а не комната) ----------
FIN = assets.LIB.get('_finishes', {})
fin = FIN.get(L.get('style', {}).get('walls', 'paint'))          # 'paint' — крашеная стена (цвет — style.wall)
if fin:                                                    # обои/штукатурка в реальном масштабе
    with bpy.data.libraries.load(str(assets.BK_DIR / f"{fin['file']}.blend")) as (src, dst):
        dst.materials = [fin['mat']]
    wm = dst.materials[0]
    if fin.get('value'):                                   # светлее/темнее фон отделки: HSV перед Base Color
        nt_ = wm.node_tree; b_ = next(n for n in nt_.nodes if n.type == 'BSDF_PRINCIPLED')
        for l in list(b_.inputs['Base Color'].links):
            hv = nt_.nodes.new('ShaderNodeHueSaturation'); hv.inputs['Value'].default_value = fin['value']
            nt_.links.new(l.from_socket, hv.inputs['Color']); nt_.links.new(hv.outputs['Color'], b_.inputs['Base Color'])
    for o in WALL_OBJS:
        o.data.materials[0] = wm
        bpy.context.view_layer.objects.active = o; o.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.cube_project(cube_size=fin['tile'], scale_to_bounds=False, correct_aspect=False)
        bpy.ops.object.mode_set(mode='OBJECT'); o.select_set(False)
for wall, (ln, f) in WALLS.items():                       # карниз под потолком
    x, y = f(ln / 2, -0.03); ax = wall in ('back', 'front')
    box('карниз', (ln if ax else 0.06, 0.06 if ax else ln, 0.07), (x, y, H - 0.035), M['white'])
used = {w: [(a0, a1) for a0, a1, *_ in openings[w]] for w in WALLS}
def free_at(wall, a, half=0.1):
    return all(not (a0 - half < a < a1 + half) for a0, a1 in used[wall])
for wall, (ln, f) in WALLS.items():                       # розетки над плинтусом — у углов, где свободно
    for a in (0.45, ln - 0.45):
        if free_at(wall, a):
            x, y = f(a, -0.006); ax = wall in ('back', 'front')
            box('розетка', (0.08 if ax else 0.012, 0.012 if ax else 0.08, 0.08), (x, y, 0.3), M['white'])
for d in L.get('doors', []):                               # выключатель у двери
    if d.get('top', 2.1) <= 2.2 and d['wall'] in WALLS:
        a = d['to'] + 0.15 if d['to'] + 0.15 < WALLS[d['wall']][0] else d['from'] - 0.15
        x, y = WALLS[d['wall']][1](a, -0.006); ax = d['wall'] in ('back', 'front')
        box('выключатель', (0.08 if ax else 0.012, 0.012 if ax else 0.08, 0.08), (x, y, 0.9), M['white'])
for w in L.get('windows', []):                             # батарея под окном + шторы
    ln, f = WALLS[w['wall']]; ax = w['wall'] in ('back', 'front')
    n = int((w['to'] - w['from'] - 0.3) / 0.062)
    for i in range(n):
        a = w['from'] + 0.15 + i * 0.062; x, y = f(a, -0.07)
        box('ребро батареи', (0.035 if ax else 0.06, 0.06 if ax else 0.035, 0.5), (x, y, max(0.42, w.get('sill', 0.85) - 0.35)), M['white'])
    if 'curtains' in assets.LIB:
        x, y = f((w['from'] + w['to']) / 2, -0.12)
        ix, iy = INWARD[w['wall']]
        e = assets.put('curtains', x, y, math.atan2(iy, ix))
        k = (H - 0.08) / assets.LIB['curtains']['size'][2]
        e.scale = (min(k, (w['to'] - w['from'] + 0.8) / assets.LIB['curtains']['size'][0]), k, k)
# светильник по центру потолка
bpy.ops.mesh.primitive_cylinder_add(radius=0.004, depth=0.45, location=(W / 2, D / 2, H - 0.225)); bpy.context.object.data.materials.append(mat('провод', (0.03, 0.03, 0.03), 0.4))
bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=0.22, depth=0.06, location=(W / 2, D / 2, H - 0.48)); bpy.context.object.data.materials.append(mat('плафон', (0.93, 0.9, 0.84), 0.8, transmission=0.3))

# мебель по расстановке
lamp_pos = []
for it in L['items']:
    assets.put(it['key'], it['x'], it['y'], math.radians(it['facing']), it.get('z', 0.0))
    if assets.LIB[it['key']]['cat'] == 'floor_lamp': lamp_pos.append((it['x'], it['y']))
sofa = next((i for i in L['items'] if assets.LIB[i['key']]['cat'] == 'sofa'), None)
if sofa:                                                   # картина: центр на 1,5 м, ширина ~2/3 дивана (до 1,2 м)
    sw = assets.LIB[sofa['key']]['size'][0]; aw = min(1.2, sw * 0.66) * 0.75 + 0.25; ah = aw * 0.7
    fx, fy = math.cos(math.radians(sofa['facing'])), math.sin(math.radians(sofa['facing']))
    sd = assets.LIB[sofa['key']]['size'][1]
    wx, wy = sofa['x'] - fx * (sd / 2 + 0.05 - 0.015), sofa['y'] - fy * (sd / 2 + 0.05 - 0.015)
    ax = abs(fy) > abs(fx)
    akey = L.get('style', {}).get('art')
    if akey in assets.LIB:                                 # настоящая картина из библиотеки (урок: пустая рамка выдаёт рендер)
        asz = assets.LIB[akey]['size']; k = min(1.4, max(aw, 0.9) / asz[0])
        e = assets.put(akey, wx + fx * 0.02, wy + fy * 0.02, math.radians(sofa['facing']), 1.55 - asz[2] * k / 2)
        e.scale = (k, k, k)
    else:
        box('рама картины', (aw if ax else 0.03, 0.03 if ax else aw, ah), (wx, wy, 1.5), mat('рама', (0.03, 0.03, 0.03), 0.5))
        art = mat('картина', (0.8, 0.7, 0.6), 0.85); nt_ = art.node_tree; b_ = nt_.nodes['Principled BSDF']
        nz_ = nt_.nodes.new('ShaderNodeTexNoise'); nz_.inputs['Scale'].default_value = 2.2; nz_.inputs['Distortion'].default_value = 1.5
        cr = nt_.nodes.new('ShaderNodeValToRGB'); el = cr.color_ramp.elements
        el[0].position = 0.35; el[0].color = (0.82, 0.74, 0.62, 1); el[1].position = 0.7; el[1].color = (0.36, 0.22, 0.14, 1)
        nt_.links.new(nz_.outputs['Fac'], cr.inputs['Fac']); nt_.links.new(cr.outputs['Color'], b_.inputs['Base Color'])
        box('картина', (aw - 0.12 if ax else 0.035, 0.035 if ax else aw - 0.12, ah - 0.12), (wx, wy, 1.5), art)
# ---------- жизнь (стайлинг по базе): плед свисает с подлокотника, мелочи там, где их кладут в жизни ----------
def throw_on_arm(it):
    """Плед на подлокотнике, который ЛЕЖИТ на диване (урок: «плед в воздухе»): форма задаётся в координатах дивана,
    затем каждая точка опускается лучом сверху на сиденье/подлокотник, а свисающая часть прижимается лучом сбоку
    к боковине. Так плед повторяет форму любого дивана."""
    sw, sd, sh = assets.LIB[it['key']]['size']
    bpy.context.view_layer.update(); dg = bpy.context.evaluated_depsgraph_get()
    a = math.radians(it['facing'] + 90); ca, sa = math.cos(a), math.sin(a)
    to_w = lambda lx, ly: (it['x'] + lx * ca - ly * sa, it['y'] + lx * sa + ly * ca)
    side = Vector((ca, sa, 0))                                  # +x дивана в мире (к правому подлокотнику)
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=70, y_subdivisions=24, size=1); pl = bpy.context.object; pl.name = 'плед'
    x0, x_edge = sw / 2 - 0.62, sw / 2
    seat = assets.LIB[it['key']].get('seat_h') or 0.4
    last = {}                                               # последняя «хорошая» высота по каждой полосе пледа
    for v in sorted(pl.data.vertices, key=lambda v: v.co.x):
        t, w = v.co.x + 0.5, v.co.y * 0.5                       # t: вдоль пледа 0..1 (1 м), w: поперёк (0,5 м)
        ly = -sd * 0.36 + w * 0.45 + 0.015 * math.sin(t * 15)   # у переднего края сиденья: иначе плед проходит сквозь подушки («рванина»)
        L_on = 0.66                                             # 66 см лежит сверху (сиденье + подлокотник), остальное свисает
        if t < L_on:
            lx = x0 + t * (x_edge - x0) / L_on
            x, y = to_w(lx, ly)
            hit, loc, *_ = sc.ray_cast(dg, Vector((x, y, sh + 0.5)), Vector((0, 0, -1)))
            key_ = round(w, 3)
            zz = loc.z if hit and loc.z > seat * 0.8 else last.get(key_, seat)   # луч мимо дивана (в пол) — не падаем
            last[key_] = zz
            z = zz + 0.012 + 0.006 * math.sin(w * 23 + t * 7)
            v.co = (x, y, z)
        else:
            drop = (t - L_on) * 0.95                            # вниз от верха подлокотника
            x, y = to_w(x_edge + 0.3, ly)
            top = v.co.z
            hit0, l0, *_ = sc.ray_cast(dg, Vector((*to_w(x_edge - 0.05, ly), sh + 0.5)), Vector((0, 0, -1)))
            ztop = (l0.z if hit0 else 0.55)
            z = max(ztop - drop, 0.08)
            hit, loc, *_ = sc.ray_cast(dg, Vector((x, y, z)), -side, distance=0.35)   # прижать к боковине (не дальше 35 см!)
            p_ = (loc + side * 0.012) if hit else Vector((*to_w(x_edge + 0.02, ly), z))
            v.co = (p_.x, p_.y, z)
    pl.modifiers.new('толщина', 'SOLIDIFY').thickness = 0.008; pl.modifiers.new('гладко', 'SUBSURF').levels = 1
    pl.pass_index = 3                                       # мелочь — нейросеть трогает слабо (иначе «съедает» плед)
    bpy.ops.object.shade_smooth(); pl.data.materials.append(mat('шерсть пледа', tuple(L.get('style', {}).get('throw', (0.42, 0.27, 0.18))), 0.9, sheen=0.25))


if sofa and 'нет пледа' not in L.get('style', {}).get('skip', []):
    throw_on_arm(sofa)
for w in L.get('windows', [])[:1]:                         # подсвечники — на подоконник (не на пол!)
    if 'candles_brass' in assets.LIB:
        x, y = WALLS[w['wall']][1]((w['from'] + w['to']) / 2 + 0.4, -0.1); ix, iy = INWARD[w['wall']]
        e = assets.put('candles_brass', x, y, math.atan2(iy, ix), w.get('sill', 0.85))
        e.scale = [0.45 / assets.LIB['candles_brass']['size'][2]] * 3
if sofa and 'basket_wicker' in assets.LIB:                 # корзина — на полу у торца дивана, не посреди комнаты
    a = math.radians(sofa['facing'] + 90); sw = assets.LIB[sofa['key']]['size'][0]
    lx, ly = -(sw / 2 + 0.22), 0.15
    bx, by = sofa['x'] + lx * math.cos(a) - ly * math.sin(a), sofa['y'] + lx * math.sin(a) + ly * math.cos(a)
    if 0.2 < bx < W - 0.2 and 0.2 < by < D - 0.2: assets.put('basket_wicker', bx, by, a)
for it in L['items']:                                      # столик: группа из 3 разной высоты (книги, ваза, поднос)
    if assets.LIB[it['key']]['cat'] == 'coffee_table':
        th = assets.LIB[it['key']].get('top_h') or assets.LIB[it['key']]['size'][2]
        tw_, td_ = assets.LIB[it['key']]['size'][:2]; a = math.radians(it['facing'] + 90)
        def on_table(key, lx, ly, rot=0.0):
            if key not in assets.LIB: return
            x_ = it['x'] + lx * math.cos(a) - ly * math.sin(a); y_ = it['y'] + lx * math.sin(a) + ly * math.cos(a)
            e_ = assets.put(key, x_, y_, a + rot, th)
            ksz = assets.LIB[key]['size']                   # правило: вещь ≤ 1/3 длины стола и ≤ 60 % глубины
            k_ = min(1.0, 0.3 * tw_ / max(ksz[0], ksz[1]), 0.6 * td_ / min(ksz[0], ksz[1]))
            e_.scale = (k_, k_, k_)
        on_table('books_real', -tw_ * 0.22, 0.02, 0.3)
        on_table('vase_white', tw_ * 0.18, 0.05)
        on_table('tray_magazine', tw_ * 0.05, -td_ * 0.12, -0.2)
for it in L['items']:                                      # сложенный плед на пуф
    if assets.LIB[it['key']]['cat'] == 'ottoman' and 'books_stack' in assets.LIB:
        e = assets.put('books_stack', it['x'] + 0.05, it['y'], math.radians(it['facing'] + 15), assets.LIB[it['key']]['size'][2] - 0.02)
        e.scale = (0.9, 0.9, 0.6)
for x, y in lamp_pos:
    bpy.ops.object.light_add(type='POINT', location=(x, y, 1.3)); lt = bpy.context.object.data
    lt.energy = 8; lt.shadow_soft_size = 0.12; lt.color = (1, 0.82, 0.6)

# свет: небо (HDRI) + солнце через первое окно
world = bpy.data.worlds.new('мир'); sc.world = world; world.use_nodes = True; nt = world.node_tree
env = nt.nodes.new('ShaderNodeTexEnvironment'); env.image = bpy.data.images.load(str(ASSETS / 'ballawley_park_2k.hdr'))
nt.links.new(env.outputs['Color'], nt.nodes['Background'].inputs['Color']); nt.nodes['Background'].inputs['Strength'].default_value = L.get('sky', 3.0)   # второй слой света — мягкий дневной
win = (L.get('windows') or L.get('doors') or [{'wall': 'left'}])[0]
ix, iy = INWARD[win['wall']]
bpy.ops.object.light_add(type='SUN', location=(0, 0, 5)); sun = bpy.context.object
sun.data.energy = L.get('sun', 2.0)   # 5,5 пересвечивало белый пол — цвет пола не подогнать
sun.data.angle = math.radians(8)              # мягкий край пятна, без пересвета
sun.data.color = (1, 0.96, 0.92)                   # нейтральнее: замер — R/B 1,5, стены коричневые
sdir = Vector((ix + 0.35 * iy, iy - 0.35 * ix, -0.75)).normalized()        # из окна внутрь и вниз, чуть вбок
sun.rotation_euler = (-sdir).to_track_quat('Z', 'Y').to_euler()

# камера
c = L.get('camera', {}); bpy.ops.object.camera_add(location=(c.get('x', W - 0.4), c.get('y', 0.35), c.get('z', 1.2)))      # 1,1–1,2 м — высота фотографа интерьеров
cam = bpy.context.object; sc.camera = cam; cam.data.lens = c.get('lens', 26)              # 24–28 мм: без «рыбьего глаза»
cam.data.sensor_width = 36
look = Vector(c.get('look', (W / 2, D * 0.75, 0.9)))
cam.rotation_euler = (look - cam.location).to_track_quat('-Z', 'Y').to_euler()

# рендер
sc.render.resolution_x, sc.render.resolution_y = RES
sc.view_settings.view_transform = 'AgX'; sc.view_settings.look = 'AgX - Base Contrast'      # как у камеры: без «пережатых» теней
sc.view_settings.exposure = L.get('exposure', 1.2)
if FAST:
    sc.render.engine = 'BLENDER_EEVEE_NEXT'
    sc.eevee.taa_render_samples = 32; sc.eevee.use_raytracing = True
else:
    sc.render.engine = 'CYCLES'
    if not CPU:
        pr = bpy.context.preferences.addons['cycles'].preferences
        pr.compute_device_type = 'OPTIX'; pr.get_devices()
        for d in pr.devices: d.use = d.type == 'OPTIX'
    sc.cycles.device = 'CPU' if CPU else 'GPU'
    sc.cycles.samples = SAMPLES
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 8
    sc.cycles.texture_limit_render = '2048'
vl = sc.view_layers[0]; vl.use_pass_object_index = True; vl.use_pass_z = True
sc.use_nodes = True; nt = sc.node_tree; nt.nodes.clear()
rl = nt.nodes.new('CompositorNodeRLayers'); comp = nt.nodes.new('CompositorNodeComposite')
nt.links.new(rl.outputs['Image'], comp.inputs['Image'])
if not FAST:
    idm = nt.nodes.new('CompositorNodeIDMask'); idm.index = 1; idm.use_antialiasing = True
    nt.links.new(rl.outputs['IndexOB'], idm.inputs['ID value'])
    fo = nt.nodes.new('CompositorNodeOutputFile'); fo.base_path = str(OUT)
    fo.format.file_format = 'PNG'; fo.format.color_mode = 'BW'; fo.file_slots[0].path = 'floor_mask'
    nt.links.new(idm.outputs['Alpha'], fo.inputs[0])
    nz = nt.nodes.new('CompositorNodeNormalize'); inv = nt.nodes.new('CompositorNodeInvert')
    nt.links.new(rl.outputs['Depth'], nz.inputs[0]); nt.links.new(nz.outputs[0], inv.inputs['Color'])
    fo.file_slots.new('depth'); nt.links.new(inv.outputs['Color'], fo.inputs[1])
    for i, (idx, name) in enumerate(((2, 'art_mask'), (3, 'decor_mask'))):   # где картина и мелочи — для нейросети
        im = nt.nodes.new('CompositorNodeIDMask'); im.index = idx; im.use_antialiasing = True
        nt.links.new(rl.outputs['IndexOB'], im.inputs['ID value'])
        fo.file_slots.new(name); nt.links.new(im.outputs['Alpha'], fo.inputs[2 + i])
(OUT / 'layout.json').write_text(json.dumps(L, ensure_ascii=False), encoding='utf-8')   # для подсказки нейросети
sc.render.filepath = str(OUT / 'room.png'); sc.render.image_settings.file_format = 'PNG'
bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT.resolve() / 'room.blend'))
if not FAST:
    fo.mute = True                                          # второй кадр — для нейросети: пол из дуба
    m = bpy.data.materials.new('дуб пола'); m.use_nodes = True; nt2 = m.node_tree
    tx = nt2.nodes.new('ShaderNodeTexImage'); tx.image = bpy.data.images.load(str(ASSETS / 'tex' / 'oak_veneer_01_diff.jpg'))
    tx.projection = 'BOX'; co = nt2.nodes.new('ShaderNodeTexCoord'); mp = nt2.nodes.new('ShaderNodeMapping')
    mp.inputs['Scale'].default_value = (0.35, 0.35, 0.35)
    nt2.links.new(co.outputs['Object'], mp.inputs['Vector']); nt2.links.new(mp.outputs['Vector'], tx.inputs['Vector'])
    nt2.links.new(tx.outputs['Color'], nt2.nodes['Principled BSDF'].inputs['Base Color'])
    floor.data.materials[0] = m
    sc.render.filepath = str(OUT / 'room_ai.png'); bpy.ops.render.render(write_still=True)
print('ГОТОВО', OUT)
