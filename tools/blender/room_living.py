"""Комната для сайта, целиком в Blender: гостиная 5,0 × 4,2 м, окно слева, дневной свет.

Пол — белый матовый: по его яркости сайт узнаёт свет и тени и кладёт любой декор.
Материалы и модели (Poly Haven, CC0) лежат вне проекта: D:\\pol-ai\\assets.
Запуск:  D:\\pol-ai\\blender\\blender.exe -b -P tools/blender/room_living.py -- <папка вывода> [samples]
С мебелью BlenderKit: ... -- <папка> 256 bk
На выходе: room.png (картинка), floor_mask0001.png (где пол), room.json (перспектива пола).
"""
import json, math, sys
from pathlib import Path

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUT = Path(argv[0] if argv else 'render_out'); OUT.mkdir(parents=True, exist_ok=True)
SAMPLES = int(argv[1]) if len(argv) > 1 else 256
BK = 'bk' in argv[2:]            # мебель из BlenderKit (скачана tools/blender/bk_download.py)
BK_DIR = Path('D:/pol-ai/bk_assets')
ASSETS = Path(r'D:\pol-ai\assets')
W, D, H = 5.0, 4.2, 2.7          # комната: ширина (x), глубина (y), высота
RES = (1600, 1067)

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene


# ---------- материалы ----------
def mat(name, color, rough=0.6, metal=0.0, sheen=0.0, transmission=0.0, bump=None, emit=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (*color, 1)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    if sheen: b.inputs['Sheen Weight'].default_value = sheen
    if transmission: b.inputs['Transmission Weight'].default_value = transmission
    if emit:
        b.inputs['Emission Color'].default_value = (1, 0.82, 0.6, 1); b.inputs['Emission Strength'].default_value = emit
    if bump:
        nt = m.node_tree
        tx = nt.nodes.new('ShaderNodeTexNoise'); tx.inputs['Scale'].default_value = bump[0]; tx.inputs['Detail'].default_value = 10
        bm = nt.nodes.new('ShaderNodeBump'); bm.inputs['Strength'].default_value = bump[1]
        nt.links.new(tx.outputs['Fac'], bm.inputs['Height']); nt.links.new(bm.outputs['Normal'], b.inputs['Normal'])
    return m


def tmat(name, tex, tint=(1, 1, 1), scale=1.0, sat=1.0, sheen=0.0, nstr=1.0):
    """Материал с настоящей текстурой (цвет, рельеф, шероховатость); sat=0 — убрать цвет текстуры, оставить фактуру."""
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; b = nt.nodes['Principled BSDF']
    co = nt.nodes.new('ShaderNodeTexCoord'); mp = nt.nodes.new('ShaderNodeMapping')
    mp.inputs['Scale'].default_value = (scale, scale, scale)
    nt.links.new(co.outputs['Object'], mp.inputs['Vector'])

    def img(kind, color):
        n = nt.nodes.new('ShaderNodeTexImage'); n.projection = 'BOX'; n.projection_blend = 0.3
        n.image = bpy.data.images.load(str(ASSETS / 'tex' / f'{tex}_{kind}.jpg'))
        n.image.colorspace_settings.name = 'sRGB' if color else 'Non-Color'
        nt.links.new(mp.outputs['Vector'], n.inputs['Vector'])
        return n
    dif = img('diff', True)
    hs = nt.nodes.new('ShaderNodeHueSaturation'); hs.inputs['Saturation'].default_value = sat
    mix = nt.nodes.new('ShaderNodeMix'); mix.data_type = 'RGBA'; mix.blend_type = 'MULTIPLY'
    mix.inputs['Factor'].default_value = 1.0; mix.inputs[7].default_value = (*tint, 1)
    nt.links.new(dif.outputs['Color'], hs.inputs['Color']); nt.links.new(hs.outputs['Color'], mix.inputs[6])
    nt.links.new(mix.outputs[2], b.inputs['Base Color'])
    rg = img('rough', False); nt.links.new(rg.outputs['Color'], b.inputs['Roughness'])
    nm = nt.nodes.new('ShaderNodeNormalMap'); nm.inputs['Strength'].default_value = nstr
    nt.links.new(img('nor', False).outputs['Color'], nm.inputs['Color']); nt.links.new(nm.outputs['Normal'], b.inputs['Normal'])
    if sheen: b.inputs['Sheen Weight'].default_value = sheen
    return m


def art():
    """Абстрактная картина: тёплые пятна (шум + градиент)."""
    m = mat('картина', (0.8, 0.7, 0.6), 0.85); nt = m.node_tree; b = nt.nodes['Principled BSDF']
    n = nt.nodes.new('ShaderNodeTexNoise'); n.inputs['Scale'].default_value = 2.2; n.inputs['Detail'].default_value = 3
    n.inputs['Distortion'].default_value = 1.5
    r = nt.nodes.new('ShaderNodeValToRGB'); el = r.color_ramp.elements
    el[0].position = 0.35; el[0].color = (0.82, 0.74, 0.62, 1); el[1].position = 0.7; el[1].color = (0.36, 0.22, 0.14, 1)
    e = el.new(0.52); e.color = (0.62, 0.42, 0.30, 1)
    nt.links.new(n.outputs['Fac'], r.inputs['Fac']); nt.links.new(r.outputs['Color'], b.inputs['Base Color'])
    return m


M = {
    'wall': mat('стена', (0.84, 0.82, 0.78), 0.92, bump=(60, 0.03)),
    'ceil': mat('потолок', (0.9, 0.9, 0.89), 0.95),
    'floor': mat('пол белый', (0.8, 0.8, 0.8), 0.55),      # белый пол — носитель света для сайта
    'white': mat('белая краска', (0.9, 0.9, 0.89), 0.35),
    'glass': mat('стекло', (1, 1, 1), 0.0, transmission=1.0),
    'sofa': tmat('лён дивана', 'rough_linen', (0.62, 0.59, 0.55), 3, sat=0, sheen=0.5),
    'pillow1': tmat('лён подушки', 'rough_linen', (0.78, 0.66, 0.50), 4, sat=0, sheen=0.5),
    'pillow2': tmat('лён подушки 2', 'rough_linen', (0.45, 0.47, 0.42), 4, sat=0, sheen=0.5),
    'throw': tmat('шерстяной плед', 'poly_wool_herringbone', (1, 1, 1), 3, sat=0.3, sheen=0.4),
    'oak': tmat('дуб', 'oak_veneer_01', (1, 1, 1), 1.2),
    'walnut': tmat('орех', 'walnut_veneer', (1, 1, 1), 1.5),
    'black': mat('чёрный металл', (0.03, 0.03, 0.03), 0.4, metal=1.0),
    'brass': mat('латунь', (0.8, 0.6, 0.35), 0.3, metal=1.0),
    'linen': mat('тюль', (0.95, 0.94, 0.90), 0.9, sheen=0.3, transmission=0.6),
    'shade': mat('абажур', (0.93, 0.90, 0.84), 0.8, transmission=0.3),
    'art': art(),
}


def box(name, size, loc, material, bevel=0.0, seg=3):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.object; o.name = name; o.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)   # только размер: поворот — вокруг самого предмета
    if bevel:
        bv = o.modifiers.new('фаска', 'BEVEL'); bv.width = bevel; bv.segments = seg; bv.limit_method = 'NONE'
        bpy.ops.object.shade_smooth()
    o.data.materials.append(material)
    return o


def soft(name, size, loc, material, r=0.05):
    """Мягкий предмет (подушка, сиденье): скруглённый блок с плавными гранями."""
    o = box(name, size, loc, material, bevel=r, seg=6)
    sub = o.modifiers.new('сетка', 'SUBSURF'); sub.subdivision_type = 'SIMPLE'; sub.levels = sub.render_levels = 3
    tx = bpy.data.textures.new(name + ' складки', 'CLOUDS'); tx.noise_scale = 0.12
    dp = o.modifiers.new('складки', 'DISPLACE'); dp.texture = tx; dp.strength = 0.012; dp.mid_level = 0.5
    o.modifiers.new('плавно', 'WEIGHTED_NORMAL')
    return o


def cyl(name, r, h, loc, material, verts=48, bevel=0.0):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=h, vertices=verts, location=loc)
    o = bpy.context.object; o.name = name
    if bevel:
        bv = o.modifiers.new('фаска', 'BEVEL'); bv.width = bevel; bv.segments = 3
    bpy.ops.object.shade_smooth(); o.data.materials.append(material)
    return o


def gltf(name, loc, height=None, rot=0.0):
    bpy.ops.import_scene.gltf(filepath=str(ASSETS / 'models' / name / f'{name}.gltf'))
    objs = bpy.context.selected_objects
    root = [o for o in objs if o.parent is None]
    bpy.ops.object.empty_add(location=(0, 0, 0)); e = bpy.context.object; e.name = name
    for o in root: o.parent = e
    bpy.context.view_layer.update()
    zs = [(o.matrix_world @ Vector(c)).z for o in objs if o.type == 'MESH' for c in o.bound_box]
    if height: e.scale = [height / (max(zs) - min(zs))] * 3
    e.location = loc; e.rotation_euler = (0, 0, rot)
    return e


def bk(aid, loc, rot=0.0, height=None, skip=(), hide=()):
    """Модель BlenderKit: ставим низом на пол, центром в loc."""
    with bpy.data.libraries.load(str(BK_DIR / f'{aid}.blend')) as (src, dst):
        dst.objects = [n for n in src.objects if not any(k in n for k in skip)]
    objs = [o for o in dst.objects if o and o.type not in ('CAMERA', 'LIGHT')]
    for o in objs:
        sc.collection.objects.link(o)
        if o.name in hide: o.hide_render = True
    bpy.ops.object.empty_add(location=(0, 0, 0)); e = bpy.context.object; e.name = aid[:8]
    for o in objs:
        if o.parent is None or o.parent not in objs: o.parent = e
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for o in objs if o.type == 'MESH' for c in o.bound_box]
    mn = Vector([min(p[i] for p in pts) for i in range(3)]); mx = Vector([max(p[i] for p in pts) for i in range(3)])
    k = height / (mx.z - mn.z) if height else 1.0
    for o in objs:
        if o.parent == e: o.location -= Vector(((mn.x + mx.x) / 2, (mn.y + mx.y) / 2, mn.z))
    e.scale = (k, k, k); e.location = loc; e.rotation_euler = (0, 0, rot)
    return e


# ---------- комната ----------
floor = box('ПОЛ', (W, D, 0.02), (W / 2, D / 2, -0.01), M['floor']); floor.pass_index = 1
box('потолок', (W, D, 0.02), (W / 2, D / 2, H + 0.01), M['ceil'])
box('стена задняя', (W + 0.4, 0.1, H), (W / 2, D + 0.05, H / 2), M['wall'])
box('стена правая', (0.1, D, H), (W + 0.05, D / 2, H / 2), M['wall'])
box('стена у камеры', (W + 0.4, 0.1, H), (W / 2, -0.05, H / 2), M['wall'])
wy0, wy1, wz0, wz1 = 1.0, 3.0, 0.85, 2.45             # окно 2,0 × 1,6 м
box('стена левая низ', (0.25, D, wz0), (-0.125, D / 2, wz0 / 2), M['wall'])
box('стена левая верх', (0.25, D, H - wz1), (-0.125, D / 2, (H + wz1) / 2), M['wall'])
box('стена левая перед', (0.25, wy0, wz1 - wz0), (-0.125, wy0 / 2, (wz0 + wz1) / 2), M['wall'])
box('стена левая зад', (0.25, D - wy1, wz1 - wz0), (-0.125, (D + wy1) / 2, (wz0 + wz1) / 2), M['wall'])
for y in (wy0 + 0.03, (wy0 + wy1) / 2, wy1 - 0.03): box('рама', (0.08, 0.06, wz1 - wz0), (-0.15, y, (wz0 + wz1) / 2), M['white'], 0.005)
for z in (wz0 + 0.03, wz1 - 0.03): box('рама', (0.08, wy1 - wy0, 0.06), (-0.15, (wy0 + wy1) / 2, z), M['white'], 0.005)
box('подоконник', (0.32, wy1 - wy0 + 0.12, 0.03), (0.0, (wy0 + wy1) / 2, wz0 - 0.015), M['white'], 0.004)
box('стекло', (0.01, wy1 - wy0, wz1 - wz0), (-0.15, (wy0 + wy1) / 2, (wz0 + wz1) / 2), M['glass']).visible_shadow = False
for (sx, sy, x, y) in [(W, 0.016, W / 2, D - 0.008), (0.016, D, W - 0.008, D / 2), (0.016, D, 0.008, D / 2)]:
    box('плинтус', (sx, sy, 0.08), (x, y, 0.04), M['white'], 0.003)
# батарея под окном: ряды рёбер
for i in range(24):
    box('ребро батареи', (0.06, 0.035, 0.5), (0.06, wy0 + 0.25 + i * 0.062, 0.42), M['white'], 0.008)
# дверь на правой стене (у камеры)
dy0 = 0.35
box('наличник', (0.03, 0.98, 2.15), (W - 0.015, dy0 + 0.45, 1.075), M['white'], 0.004)
box('дверь', (0.04, 0.84, 2.04), (W - 0.03, dy0 + 0.45, 1.02), M['white'], 0.006)
cyl('ручка', 0.012, 0.13, (W - 0.07, dy0 + 0.12, 1.0), M['brass'], 16).rotation_euler = (math.pi / 2, 0, 0)
# розетки
for x in (1.3, 3.9): box('розетка', (0.08, 0.012, 0.08), (x, D - 0.006, 0.3), M['white'], 0.006)
if BK: bk('8f38fc13-71f5-40f9-9778-cf27f38a85b0', (0.25, (wy0 + wy1) / 2, 0), math.pi / 2, height=wz1 + 0.2)
# тюль: волнистое полотно по краям окна + карниз
box('карниз', (0.03, wy1 - wy0 + 0.6, 0.03), (0.12, (wy0 + wy1) / 2, wz1 + 0.15), M['black'])
for y0, w in () if BK else ((wy0 - 0.3, 0.75), (wy1 - 0.45, 0.75)):
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=90, y_subdivisions=6, size=1, location=(0.14, y0 + w / 2, (wz1 + 0.15) / 2))
    c = bpy.context.object; c.name = 'штора'
    c.rotation_euler = (math.pi / 2, 0, math.pi / 2); c.scale = (w, wz1 + 0.15, 1)
    bpy.ops.object.transform_apply(rotation=True, scale=True)
    for v in c.data.vertices: v.co.x += 0.03 * math.sin(v.co.y * 48) * (0.7 + 0.3 * math.sin(v.co.z * 3))
    c.modifiers.new('толщина', 'SOLIDIFY').thickness = 0.003
    bpy.ops.object.shade_smooth(); c.data.materials.append(M['linen'])
# люстра: подвес и плоский плафон
cyl('подвес', 0.004, 0.5, (2.5, 2.2, H - 0.25), M['black'], 8)
cyl('плафон', 0.22, 0.06, (2.5, 2.2, H - 0.52), M['shade'], 64, 0.01)

# ---------- мебель ----------
if BK:
    sx = 2.25                                         # центр нового дивана (для картины)
    bk('01d39e9e-a6a5-40e5-bec3-56a908c62b8f', (2.45, D - 1.05, 0), 0.0,   # диван, столик, пуф, растения
       hide=('Living Room Sofa and Table Set 002', 'pouff', 'pouff_cushion'))                       # ковёр прячем: пол должен быть виден
    bk('07267ccb-c51f-4c9a-9afb-56ebb6f8ad1a', (0.95, 1.75, 0), -0.15)         # кресло с пуфом
    bk('0318ccab-565c-4169-ad40-0001f537aba2', (4.55, D - 0.35, 0))          # торшер
    bpy.ops.object.light_add(type='POINT', location=(4.55, D - 0.35, 1.3)); L = bpy.context.object.data
    L.energy = 8; L.shadow_soft_size = 0.12; L.color = (1, 0.82, 0.6)
if not BK:
    sx, sy = 2.55, D - 0.52                               # диван 2,2 м у задней стены
    for dx in (-1.0, 1.0):
        for dy in (-0.32, 0.32): cyl('ножка', 0.018, 0.12, (sx + dx, sy + dy, 0.06), M['walnut'], 16)
    soft('основание', (2.24, 0.94, 0.22), (sx, sy, 0.23), M['sofa'], 0.035)
    for dx in (-0.535, 0.535): soft('сиденье', (1.04, 0.74, 0.17), (sx + dx, sy - 0.08, 0.425), M['sofa'], 0.07)
    for dx in (-1.03, 1.03): soft('подлокотник', (0.18, 0.94, 0.38), (sx + dx, sy, 0.53), M['sofa'], 0.07)
    soft('спинка', (1.88, 0.26, 0.46), (sx, sy + 0.33, 0.57), M['sofa'], 0.09)
    for dx, m_, rz in ((-0.62, 'pillow1', 0.15), (-0.2, 'pillow2', -0.05), (0.7, 'pillow1', -0.12)):
        p = soft('подушка', (0.44, 0.2, 0.42), (sx + dx, sy + 0.04, 0.74), M[m_], 0.06)
        p.rotation_euler = (math.radians(-14), 0, rz)
    # журнальный столик: дуб, чёрные ножки, ваза
    tx, ty = 2.5, D - 1.7
    cyl('столешница', 0.46, 0.035, (tx, ty, 0.42), M['oak'], 128, 0.008)
    for a in range(3):
        ang = a * 2 * math.pi / 3 + 0.4
        cyl('ножка стола', 0.013, 0.405, (tx + 0.3 * math.cos(ang), ty + 0.3 * math.sin(ang), 0.2), M['black'], 12)
    gltf('ceramic_vase_01', (tx + 0.12, ty + 0.05, 0.44), height=0.24)
    # торшер у правого края дивана
    lx, ly = 4.1, D - 0.45
    cyl('основание торшера', 0.15, 0.02, (lx, ly, 0.01), M['black'])
    cyl('стойка торшера', 0.011, 1.5, (lx, ly, 0.76), M['black'], 12)
    cyl('абажур', 0.22, 0.32, (lx, ly, 1.55), M['shade'], 64)
    bpy.ops.object.light_add(type='POINT', location=(lx, ly, 1.52)); L = bpy.context.object.data
    L.energy = 8; L.shadow_soft_size = 0.12; L.color = (1, 0.82, 0.6)
    # растение в углу и картина над диваном
    gltf('potted_plant_02', (0.55, D - 0.5, 0), height=1.25, rot=0.6)
box('рама картины', (1.1, 0.03, 0.75), (sx, D - 0.02, 1.58), M['black'], 0.004)
box('паспарту', (1.04, 0.012, 0.69), (sx, D - 0.036, 1.58), M['white'])
box('картина', (0.86, 0.008, 0.52), (sx, D - 0.044, 1.58), M['art'])

# ---------- свет: панорама парка за окном + солнце ----------
world = bpy.data.worlds.new('мир'); sc.world = world; world.use_nodes = True
nt = world.node_tree
env = nt.nodes.new('ShaderNodeTexEnvironment'); env.image = bpy.data.images.load(str(ASSETS / 'ballawley_park_2k.hdr'))
mp = nt.nodes.new('ShaderNodeMapping'); mp.inputs['Rotation'].default_value = (0, 0, math.radians(90))
co = nt.nodes.new('ShaderNodeTexCoord')
nt.links.new(co.outputs['Generated'], mp.inputs['Vector']); nt.links.new(mp.outputs['Vector'], env.inputs['Vector'])
nt.links.new(env.outputs['Color'], nt.nodes['Background'].inputs['Color'])
nt.nodes['Background'].inputs['Strength'].default_value = 1.4
bpy.ops.object.light_add(type='SUN', location=(0, 0, 5)); sun = bpy.context.object
sun.data.energy = 5.5; sun.data.angle = math.radians(1.0); sun.data.color = (1, 0.93, 0.84)
sun.rotation_euler = Vector((1.0, 0.3, -0.6)).to_track_quat('-Z', 'Y').to_euler()

# ---------- камера: 1,3 м, объектив 22 мм ----------
bpy.ops.object.camera_add(location=(W - 0.4, 0.35, 1.3))
cam = bpy.context.object; sc.camera = cam
cam.data.lens = 22; cam.data.sensor_width = 36
cam.rotation_euler = (Vector((1.9, D, 0.95)) - cam.location).to_track_quat('-Z', 'Y').to_euler()

# ---------- рендер ----------
sc.render.engine = 'CYCLES'
prefs = bpy.context.preferences.addons['cycles'].preferences
prefs.compute_device_type = 'OPTIX'; prefs.get_devices()
for d in prefs.devices: d.use = d.type == 'OPTIX'
sc.cycles.device = 'GPU'; sc.cycles.samples = SAMPLES; sc.cycles.use_denoising = True
sc.cycles.max_bounces = 8
sc.view_settings.view_transform = 'AgX'; sc.view_settings.look = 'AgX - Medium High Contrast'
sc.view_settings.exposure = 0.9
sc.render.resolution_x, sc.render.resolution_y = RES
sc.view_layers[0].use_pass_object_index = True
sc.view_layers[0].use_pass_z = True
sc.use_nodes = True
nt = sc.node_tree; nt.nodes.clear()
rl = nt.nodes.new('CompositorNodeRLayers')
comp = nt.nodes.new('CompositorNodeComposite')
# «как фотоаппарат»: свечение вокруг ярких мест, лёгкие цветные края, затемнение по углам
gl = nt.nodes.new('CompositorNodeGlare'); gl.glare_type = 'FOG_GLOW'; gl.quality = 'HIGH'
gl.threshold = 0.9; gl.mix = -0.85; gl.size = 8
ld = nt.nodes.new('CompositorNodeLensdist'); ld.inputs['Dispersion'].default_value = 0.004
el = nt.nodes.new('CompositorNodeEllipseMask'); el.width = 1.25; el.height = 1.25
bl = nt.nodes.new('CompositorNodeBlur'); bl.size_x = bl.size_y = 300; bl.use_relative = False
vm = nt.nodes.new('CompositorNodeMixRGB'); vm.blend_type = 'MULTIPLY'; vm.inputs['Fac'].default_value = 0.25
nt.links.new(rl.outputs['Image'], gl.inputs['Image']); nt.links.new(gl.outputs['Image'], ld.inputs['Image'])
nt.links.new(el.outputs['Mask'], bl.inputs['Image'])
nt.links.new(ld.outputs['Image'], vm.inputs[1]); nt.links.new(bl.outputs['Image'], vm.inputs[2])
nt.links.new(vm.outputs['Image'], comp.inputs['Image'])
idm = nt.nodes.new('CompositorNodeIDMask'); idm.index = 1; idm.use_antialiasing = True
nt.links.new(rl.outputs['IndexOB'], idm.inputs['ID value'])
fo = nt.nodes.new('CompositorNodeOutputFile'); fo.base_path = str(OUT)
fo.format.file_format = 'PNG'; fo.format.color_mode = 'BW'; fo.file_slots[0].path = 'floor_mask'
nt.links.new(idm.outputs['Alpha'], fo.inputs[0])
# карта глубины для нейросети (ближе — светлее)
nz = nt.nodes.new('CompositorNodeNormalize'); inv = nt.nodes.new('CompositorNodeInvert')
nt.links.new(rl.outputs['Depth'], nz.inputs[0]); nt.links.new(nz.outputs[0], inv.inputs['Color'])
fo.file_slots.new('depth'); nt.links.new(inv.outputs['Color'], fo.inputs[1])
sc.render.filepath = str(OUT / 'room.png'); sc.render.image_settings.file_format = 'PNG'
bpy.ops.render.render(write_still=True)

# второй кадр — отражения в полу: пол чёрный глянцевый, в нём видно только отражение комнаты
fo.mute = True
floor.data.materials[0] = mat('пол глянец', (0, 0, 0), 0.18)
sc.render.filepath = str(OUT / 'room_refl.png')
bpy.ops.render.render(write_still=True)

# третий кадр — для нейросети: пол деревянный (белый пол сбивает её)
fl = tmat('дуб пола', 'oak_veneer_01', (0.95, 0.9, 0.85), 0.35)
floor.data.materials[0] = fl
sc.render.filepath = str(OUT / 'room_ai.png')
bpy.ops.render.render(write_still=True)

# ---------- перспектива пола для сайта ----------
from bpy_extras.object_utils import world_to_camera_view
Y0 = 1.3                                              # ближний край пола — в кадре
q = []
for p in [(0, D, 0), (W, D, 0), (W, Y0, 0), (0, Y0, 0)]:
    v = world_to_camera_view(sc, cam, Vector(p))
    q.append([round(v.x * RES[0], 2), round((1 - v.y) * RES[1], 2)])
json.dump({'img': list(RES), 'quad': q, 'size': [W, round(D - Y0, 3)], 'cam_h': 1.3}, open(OUT / 'room.json', 'w'), indent=1)
print('ГОТОВО', OUT)
