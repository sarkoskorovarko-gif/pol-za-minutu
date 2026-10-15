"""Пробная комната для сайта, целиком в Blender: гостиная 5,0 × 4,2 м, окно слева, дневной свет.

Пол — белый матовый: по его яркости сайт узнаёт свет и тени и кладёт любой декор.
Запуск:  D:\\pol-ai\\blender\\blender.exe -b -P tools/blender/room_living.py -- <папка вывода> [samples]
На выходе: room.png (картинка), floor_mask.png (где пол, сглаженный край), room.json (перспектива пола).
"""
import json, math, sys
from pathlib import Path

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUT = Path(argv[0] if argv else 'render_out'); OUT.mkdir(parents=True, exist_ok=True)
SAMPLES = int(argv[1]) if len(argv) > 1 else 256
W, D, H = 5.0, 4.2, 2.7          # комната: ширина (x), глубина (y), высота
RES = (1600, 1067)

# ---------- сцена с нуля ----------
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.unit_settings.system = 'METRIC'


def mat(name, color, rough=0.6, metal=0.0, sheen=0.0, bump=None, transmission=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (*color, 1)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    if sheen: b.inputs['Sheen Weight'].default_value = sheen
    if transmission: b.inputs['Transmission Weight'].default_value = transmission
    if bump:                                   # мелкий рельеф (ткань, штукатурка, дерево)
        nt = m.node_tree
        tex = nt.nodes.new('ShaderNodeTexNoise'); tex.inputs['Scale'].default_value = bump[0]
        tex.inputs['Detail'].default_value = 8
        bm = nt.nodes.new('ShaderNodeBump'); bm.inputs['Strength'].default_value = bump[1]
        nt.links.new(tex.outputs['Fac'], bm.inputs['Height']); nt.links.new(bm.outputs['Normal'], b.inputs['Normal'])
    return m


def wood(name, base, dark, scale=(2, 40, 2)):
    """Дерево: полосы волокон (волновая текстура вдоль x)."""
    m = mat(name, base, 0.45, bump=(300, 0.05))
    nt = m.node_tree; b = nt.nodes['Principled BSDF']
    co = nt.nodes.new('ShaderNodeTexCoord'); mp = nt.nodes.new('ShaderNodeMapping')
    mp.inputs['Scale'].default_value = scale
    wv = nt.nodes.new('ShaderNodeTexWave'); wv.wave_type = 'BANDS'; wv.bands_direction = 'X'
    wv.inputs['Scale'].default_value = 2; wv.inputs['Distortion'].default_value = 6; wv.inputs['Detail'].default_value = 4
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].color = (*dark, 1); ramp.color_ramp.elements[1].color = (*base, 1)
    nt.links.new(co.outputs['Object'], mp.inputs['Vector']); nt.links.new(mp.outputs['Vector'], wv.inputs['Vector'])
    nt.links.new(wv.outputs['Fac'], ramp.inputs['Fac']); nt.links.new(ramp.outputs['Color'], b.inputs['Base Color'])
    return m


M = {
    'wall': mat('стена', (0.86, 0.84, 0.80), 0.9, bump=(80, 0.02)),
    'ceil': mat('потолок', (0.92, 0.92, 0.91), 0.95),
    'floor': mat('пол белый', (0.8, 0.8, 0.8), 0.55),        # белый пол — носитель света для сайта
    'skirt': mat('плинтус', (0.93, 0.93, 0.92), 0.4),
    'frame': mat('рама окна', (0.95, 0.95, 0.95), 0.35),
    'glass': mat('стекло', (1, 1, 1), 0.0, transmission=1.0),
    'sofa': mat('ткань дивана', (0.42, 0.40, 0.37), 0.95, sheen=0.4, bump=(250, 0.15)),
    'cushion': mat('ткань подушек', (0.62, 0.55, 0.45), 0.95, sheen=0.4, bump=(250, 0.15)),
    'oak': wood('дуб', (0.62, 0.45, 0.28), (0.45, 0.30, 0.17)),
    'walnut': wood('орех', (0.30, 0.19, 0.12), (0.18, 0.11, 0.07)),
    'black': mat('чёрный металл', (0.03, 0.03, 0.03), 0.35, metal=1.0),
    'linen': mat('штора', (0.95, 0.94, 0.90), 0.9, sheen=0.3, transmission=0.35),
    'shade': mat('абажур', (0.93, 0.90, 0.84), 0.8, transmission=0.15),
    'pot': mat('горшок', (0.88, 0.87, 0.84), 0.5),
    'leaf': mat('листья', (0.12, 0.28, 0.10), 0.5, sheen=0.2),
    'art': mat('картина', (0.75, 0.62, 0.48), 0.8, bump=(30, 0.1)),
}


def box(name, size, loc, material, bevel=0.0, seg=3, sub=0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.object; o.name = name; o.scale = size
    bpy.ops.object.transform_apply(scale=True)
    if bevel:
        bv = o.modifiers.new('фаска', 'BEVEL'); bv.width = bevel; bv.segments = seg; bv.limit_method = 'NONE'
    if sub:
        o.modifiers.new('сглаж', 'SUBSURF').levels = sub
        bpy.ops.object.shade_smooth()
    o.data.materials.append(material)
    return o


def cyl(name, r, h, loc, material, verts=48, bevel=0.0):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=h, vertices=verts, location=loc)
    o = bpy.context.object; o.name = name
    if bevel:
        bv = o.modifiers.new('фаска', 'BEVEL'); bv.width = bevel; bv.segments = 3
    bpy.ops.object.shade_smooth(); o.data.materials.append(material)
    return o


# ---------- комната ----------
floor = box('ПОЛ', (W, D, 0.02), (W / 2, D / 2, -0.01), M['floor'])
floor.pass_index = 1                                      # маска пола
box('потолок', (W, D, 0.02), (W / 2, D / 2, H + 0.01), M['ceil'])
box('стена задняя', (W + 0.4, 0.1, H), (W / 2, D + 0.05, H / 2), M['wall'])
box('стена правая', (0.1, D, H), (W + 0.05, D / 2, H / 2), M['wall'])
box('стена у камеры', (W + 0.4, 0.1, H), (W / 2, -0.05, H / 2), M['wall'])
# левая стена с окном: окно 1,8 × 1,6 м, подоконник на 0,8 м
wy0, wy1, wz0, wz1 = 1.1, 2.9, 0.8, 2.4
box('стена левая низ', (0.1, D, wz0), (-0.05, D / 2, wz0 / 2), M['wall'])
box('стена левая верх', (0.1, D, H - wz1), (-0.05, D / 2, (H + wz1) / 2), M['wall'])
box('стена левая перед', (0.1, wy0, wz1 - wz0), (-0.05, wy0 / 2, (wz0 + wz1) / 2), M['wall'])
box('стена левая зад', (0.1, D - wy1, wz1 - wz0), (-0.05, (D + wy1) / 2, (wz0 + wz1) / 2), M['wall'])
for y in (wy0, (wy0 + wy1) / 2, wy1): box('рама', (0.12, 0.06, wz1 - wz0), (-0.05, y, (wz0 + wz1) / 2), M['frame'])
for z in (wz0, wz1): box('рама', (0.12, wy1 - wy0, 0.06), (-0.05, (wy0 + wy1) / 2, z), M['frame'])
box('подоконник', (0.25, wy1 - wy0 + 0.1, 0.03), (0.06, (wy0 + wy1) / 2, wz0), M['frame'])
box('стекло', (0.01, wy1 - wy0, wz1 - wz0), (-0.05, (wy0 + wy1) / 2, (wz0 + wz1) / 2), M['glass']).visible_shadow = False  # солнце проходит
# плинтусы 7 см
for (sx, sy, x, y) in [(W, 0.015, W / 2, D - 0.0075), (0.015, D, W - 0.0075, D / 2), (0.015, D, 0.0075, D / 2)]:
    box('плинтус', (sx, sy, 0.07), (x, y, 0.035), M['skirt'], bevel=0.004)

# занавески по краям окна: волнистое полотно
for y0 in (wy0 - 0.15, wy1 - 0.25):
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=60, y_subdivisions=4, size=1, location=(0.12, y0 + 0.2, 1.3))
    c = bpy.context.object; c.name = 'штора'
    c.rotation_euler = (math.pi / 2, 0, math.pi / 2); c.scale = (0.4, 2.55, 1)
    bpy.ops.object.transform_apply(rotation=True, scale=True)
    for v in c.data.vertices: v.co.x += 0.035 * math.sin(v.co.y * 55)
    c.modifiers.new('толщина', 'SOLIDIFY').thickness = 0.004
    bpy.ops.object.shade_smooth(); c.data.materials.append(M['linen'])

# ---------- мебель ----------
# диван 2,2 м у задней стены
sx, sy = 2.4, D - 0.55
for dx in (-1.0, 1.0):
    for dy in (-0.3, 0.3): cyl('ножка', 0.02, 0.1, (sx + dx, sy + dy, 0.05), M['walnut'], 16)
box('диван основание', (2.2, 0.92, 0.22), (sx, sy, 0.21), M['sofa'], bevel=0.03)
for dx in (-0.52, 0.52): box('сиденье', (1.0, 0.72, 0.16), (sx + dx, sy - 0.07, 0.40), M['sofa'], bevel=0.05, seg=4, sub=1)
for dx in (-1.02, 1.02): box('подлокотник', (0.18, 0.92, 0.36), (sx + dx, sy, 0.38), M['sofa'], bevel=0.06, seg=4, sub=1)
box('спинка', (1.86, 0.24, 0.46), (sx, sy + 0.32, 0.62), M['sofa'], bevel=0.07, seg=4, sub=1)
# журнальный столик: дуб, чёрные ножки
tx, ty = 2.4, D - 1.65
cyl('столешница', 0.45, 0.035, (tx, ty, 0.42), M['oak'], 96, bevel=0.008)
for a in range(3):
    ang = a * 2 * math.pi / 3
    l = cyl('ножка стола', 0.012, 0.42, (tx + 0.28 * math.cos(ang), ty + 0.28 * math.sin(ang), 0.2), M['black'], 12)
# торшер справа от дивана
lx, ly = 3.85, D - 0.4
cyl('основание торшера', 0.15, 0.02, (lx, ly, 0.01), M['black'])
cyl('стойка торшера', 0.012, 1.5, (lx, ly, 0.76), M['black'], 12)
sh = cyl('абажур', 0.22, 0.32, (lx, ly, 1.55), M['shade'], 64)
# растение в углу
px, py = 0.55, D - 0.45
cyl('горшок', 0.2, 0.42, (px, py, 0.21), M['pot'], 64, bevel=0.01)
for i in range(14):                                  # листья — вытянутые сплюснутые сферы
    ang = i * 2.4; r = 0.12 + 0.03 * (i % 3)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.2, location=(px + r * math.cos(ang), py + r * math.sin(ang), 0.75 + 0.05 * (i % 5)))
    lf = bpy.context.object; lf.scale = (1.6, 0.45, 0.05)
    lf.rotation_euler = (math.radians(30 + 8 * (i % 4)), 0, ang)
    bpy.ops.object.shade_smooth(); lf.data.materials.append(M['leaf'])
# картина над диваном
box('рама картины', (1.0, 0.03, 0.7), (sx, D - 0.02, 1.55), M['walnut'], bevel=0.005)
box('холст', (0.92, 0.01, 0.62), (sx, D - 0.04, 1.55), M['art'])

# ---------- свет: небо с солнцем через окно ----------
world = bpy.data.worlds.new('небо'); sc.world = world; world.use_nodes = True
sky = world.node_tree.nodes.new('ShaderNodeTexSky'); sky.sky_type = 'NISHITA'
sky.sun_disc = False; sky.sun_elevation = math.radians(30)            # небо — рассеянный свет из окна
world.node_tree.links.new(sky.outputs['Color'], world.node_tree.nodes['Background'].inputs['Color'])
world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.9
# солнце: через окно слева, пятно ложится на пол
bpy.ops.object.light_add(type='SUN', location=(0, 0, 5)); sun = bpy.context.object
sun.data.energy = 4.0; sun.data.angle = math.radians(1.5); sun.data.color = (1, 0.95, 0.88)
sun.rotation_euler = Vector((1.0, 0.25, -0.62)).to_track_quat('-Z', 'Y').to_euler()
# мягкий свет от абажура (вечером станет заметнее)
bpy.ops.object.light_add(type='POINT', location=(lx, ly, 1.5)); bpy.context.object.data.energy = 6
bpy.context.object.data.shadow_soft_size = 0.15; bpy.context.object.data.color = (1, 0.85, 0.65)

# ---------- камера: как фото интерьера, 1,35 м, широкий угол ----------
bpy.ops.object.camera_add(location=(W - 0.35, 0.3, 1.35))
cam = bpy.context.object; sc.camera = cam
cam.data.lens = 18; cam.data.sensor_width = 36
target = Vector((1.8, D, 0.9))
cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()

# ---------- рендер ----------
sc.render.engine = 'CYCLES'
prefs = bpy.context.preferences.addons['cycles'].preferences
prefs.compute_device_type = 'OPTIX'; prefs.get_devices()
for d in prefs.devices: d.use = d.type == 'OPTIX'
sc.cycles.device = 'GPU'
sc.cycles.samples = SAMPLES; sc.cycles.use_denoising = True
sc.view_settings.view_transform = 'AgX'; sc.view_settings.look = 'AgX - Base Contrast'
sc.view_settings.exposure = 1.1
sc.render.resolution_x, sc.render.resolution_y = RES
sc.render.film_transparent = False
sc.view_layers[0].use_pass_object_index = True

# маска пола через композитор: ID Mask со сглаживанием
sc.use_nodes = True
nt = sc.node_tree; nt.nodes.clear()
rl = nt.nodes.new('CompositorNodeRLayers')
comp = nt.nodes.new('CompositorNodeComposite'); nt.links.new(rl.outputs['Image'], comp.inputs['Image'])
idm = nt.nodes.new('CompositorNodeIDMask'); idm.index = 1; idm.use_antialiasing = True
nt.links.new(rl.outputs['IndexOB'], idm.inputs['ID value'])
fo = nt.nodes.new('CompositorNodeOutputFile'); fo.base_path = str(OUT)
fo.format.file_format = 'PNG'; fo.format.color_mode = 'BW'
fo.file_slots[0].path = 'floor_mask'
nt.links.new(idm.outputs['Alpha'], fo.inputs[0])

sc.render.filepath = str(OUT / 'room.png')
sc.render.image_settings.file_format = 'PNG'
bpy.ops.render.render(write_still=True)

# ---------- перспектива пола для сайта: углы пола на картинке ----------
from bpy_extras.object_utils import world_to_camera_view
q = []
Y0 = 1.2                                                   # ближний край — в кадре (угол у стены за камерой)
for p in [(0, D, 0), (W, D, 0), (W, Y0, 0), (0, Y0, 0)]:   # дальний левый, дальний правый, ближний правый, ближний левый
    v = world_to_camera_view(sc, cam, Vector(p))
    q.append([round(v.x * RES[0], 2), round((1 - v.y) * RES[1], 2)])
json.dump({'img': list(RES), 'quad': q, 'size': [W, round(D - Y0, 3)], 'cam_h': 1.35}, open(OUT / 'room.json', 'w'), indent=1)
print('ГОТОВО', OUT)
