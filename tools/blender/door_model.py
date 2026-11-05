"""Дверь в 3D по фото каталога (полотно, коробка/наличник, стекло с блеском, ручка).

Запуск: blender -b -P door_model.py -- spec=<door.json> out=<png>      (отдельный рендер для сверки с фото)
Из другого скрипта: build_door(spec, cx, y_wall, scale_h) — ставит дверь на стену (лицо к -Y).
spec: размеры в пикселях фото (так их проще мерить): w,h — весь наличник; casing — ширина наличника;
stile, rail_top, rail_bot — бруски полотна; glass — [[y0,y1],...] полосы стекла между брусками;
grooves — [y,...] тонкие канавки; leaf/glass_rgb — цвет sRGB 0..255; handle_y — высота ручки (px от верха).
"""
import json
import math
import sys

import bpy


def lin(c):
    c = c / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def mat(name, rgb, rough, coat=0.0, metal=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (*[lin(v) for v in rgb], 1)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    b.inputs['Coat Weight'].default_value = coat
    return m


def grain(m, rgb):
    """Рисунок дерева экошпона: вытянутый по высоте шум, тёмные волокна чуть темнее основы."""
    nt = m.node_tree; n = nt.nodes
    tc = n.new('ShaderNodeTexCoord'); mp = n.new('ShaderNodeMapping'); mp.inputs['Scale'].default_value = (25, 25, 2)
    nz = n.new('ShaderNodeTexNoise'); nz.inputs['Detail'].default_value = 8; nz.inputs['Scale'].default_value = 4
    cr = n.new('ShaderNodeValToRGB'); cr.color_ramp.elements[0].position = 0.4; cr.color_ramp.elements[1].position = 0.65
    base = [lin(v) for v in rgb]
    cr.color_ramp.elements[0].color = (*[v * 0.92 for v in base], 1); cr.color_ramp.elements[1].color = (*base, 1)
    nt.links.new(tc.outputs['Object'], mp.inputs['Vector']); nt.links.new(mp.outputs['Vector'], nz.inputs['Vector'])
    nt.links.new(nz.outputs['Fac'], cr.inputs['Fac']); nt.links.new(cr.outputs['Color'], n['Principled BSDF'].inputs['Base Color'])


def box(name, x0, x1, z0, z1, y0, y1, m, idx):
    bpy.ops.mesh.primitive_cube_add(size=1)
    o = bpy.context.object; o.name = name
    o.scale = (x1 - x0, y1 - y0, z1 - z0); o.location = ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.ops.object.modifier_add(type='BEVEL'); o.modifiers[-1].width = 0.002; o.modifiers[-1].segments = 2
    o.data.materials.append(m); o.pass_index = idx
    return o


def build_door(s, cx, y_wall, height=2.07, idx=4):
    """Дверь целиком; низ на полу, лицо полотна к камере (-Y). Возвращает список объектов."""
    f = height / s['h']
    X = lambda px: cx + (px - s['w'] / 2) * f
    Z = lambda py: (s['h'] - py) * f
    leaf = mat('полотно', s['leaf_rgb'], 0.42); grain(leaf, s['leaf_rgb'])
    dark = mat('канавка', [v * s.get('groove_dark', 0.78) for v in s['leaf_rgb']], 0.6)
    gr = s.get('glass_rough', 0.08)
    glass = (mat('зеркало', (215, 215, 215), 0.03, metal=1.0) if s.get('mirror')
             else mat('стекло', s['glass_rgb'], gr, coat=0.5 if gr < 0.2 else 0.0))
    steel = mat('ручка', (150, 150, 152), 0.25, metal=1.0)
    c, W, H = s['casing'], s['w'], s['h']
    yf = y_wall                       # лицо стены
    o = []
    # наличник (чуть выступает над стеной) и полотно (утоплено в коробку на 1 см)
    o += [box('наличник', X(0), X(c), 0, Z(0), yf - 0.012, yf, leaf, idx),
          box('наличник', X(W - c), X(W), 0, Z(0), yf - 0.012, yf, leaf, idx),
          box('наличник', X(c), X(W - c), Z(c), Z(0), yf - 0.012, yf, leaf, idx)]
    l0, l1 = c, W - c
    gap = mat('щель', [v * 0.6 for v in s['leaf_rgb']], 0.7)       # тонкая щель между наличником и полотном — на фото видна
    o += [box('щель', X(c), X(c) + 0.003, 0, Z(c), yf - 0.0125, yf - 0.012, gap, idx),
          box('щель', X(W - c) - 0.003, X(W - c), 0, Z(c), yf - 0.0125, yf - 0.012, gap, idx),
          box('щель', X(c), X(W - c), Z(c) - 0.003, Z(c), yf - 0.0125, yf - 0.012, gap, idx)]
    o.append(box('полотно', X(l0), X(l1), 0, Z(c), yf - 0.002, yf + 0.03, leaf, idx))
    st = s['stile']; li, ri = l0 + s.get('stile_l', st), l1 - s.get('stile_r', st)   # поля полотна бывают разные
    gx0, gx1 = s.get('glass_x', [li, ri])                                           # вертикальная вставка — своя ширина
    for g in s['glass']:              # стекло — тонкая вставка заподлицо (лак, матовое или зеркало)
        o.append(box('стекло', X(gx0), X(gx1), Z(g[1]), Z(g[0]), yf - 0.004, yf - 0.001, glass, idx))
    for r in s.get('glass_rect', []):   # любые прямоугольные вставки стекла [x0,y0,x1,y1] (вертикальные полоски)
        o.append(box('стекло', X(r[0]), X(r[2]), Z(r[3]), Z(r[1]), yf - 0.004, yf - 0.001, glass, idx))
    for k_, r in enumerate(s.get('panels', [])):   # филёнки другого тона [x0,y0,x1,y1,[r,g,b]] (светлая вертикальная полоса у 17X)
        pm = mat(f'филёнка {k_}', r[4], 0.42); grain(pm, r[4])
        o.append(box('филёнка', X(r[0]), X(r[2]), Z(r[3]), Z(r[1]), yf - 0.0025, yf - 0.0015, pm, idx))
    for gx in s.get('seams_x', []):   # дополнительные вертикальные стыки филёнок
        o.append(box('канавка', X(gx) - 0.002, X(gx) + 0.002, Z(s['h'] - s['rail_bot']), Z(s['rail_top']), yf - 0.0035, yf - 0.002, dark, idx))
    for gy in s.get('glass_div', []):  # светлые молдинги между секциями стекла
        o.append(box('молдинг', X(gx0), X(gx1), Z(gy + 1.5), Z(gy - 1.5), yf - 0.005, yf - 0.002, leaf, idx))
    for gy in s.get('grooves', []):  # канавки между филёнками
        o.append(box('канавка', X(li), X(ri), Z(gy + 1.5), Z(gy - 1.5), yf - 0.0035, yf - 0.002, dark, idx))
    for gx in (li, ri):    # вертикальные стыки брусков
        o.append(box('канавка', X(gx) - 0.002, X(gx) + 0.002, Z(s['h'] - s['rail_bot']), Z(s['rail_top']), yf - 0.0035, yf - 0.002, dark, idx))
    hx, hz = X(l0 + s.get('stile_l', st) * 0.55), Z(s['handle_y'])
    # ручка как на фото Atum: квадратная розетка графит, тонкий прямой рычаг к центру двери, ниже — фиксатор
    graph = mat('ручка', s.get('handle_rgb', (128, 128, 131)), s.get('handle_rough', 0.4), metal=1.0)
    o.append(box('розетка', hx - 0.025, hx + 0.025, hz - 0.025, hz + 0.025, yf - 0.009, yf - 0.002, graph, idx))
    o.append(box('ручка', hx - 0.005, hx + 0.005, hz - 0.005, hz + 0.005, yf - 0.055, yf - 0.009, graph, idx))
    o.append(box('ручка', hx - 0.006, hx + 0.1, hz - 0.006, hz + 0.006, yf - 0.062, yf - 0.05, graph, idx))
    o.append(box('фиксатор', hx - 0.004, hx + 0.004, hz - 0.016, hz - 0.008, yf - 0.012, yf - 0.009, dark, idx))
    for z in (0.25, height - 0.3):   # петли с другой стороны
        o.append(box('петля', X(l1) - 0.004, X(l1) + 0.004, z - 0.05, z + 0.05, yf - 0.006, yf, steel, idx))
    return o


def build_door_photo(s, img, cx, y_wall, height=2.07, idx=4):
    """Дверь по фото (×4, door_upscale.py): плита с фото во всю дверь с наличником — форма, цвет и ручка точно как в каталоге;
    стекло (s['glass'] / glass_x / glass_rect) — с настоящим блеском, зеркало (s['mirror']) — настоящее зеркало."""
    import numpy as np
    f = height / s['h']; W, H = s['w'] * f, height
    bpy.ops.mesh.primitive_plane_add(size=1); o = bpy.context.object; o.name = 'ДВЕРЬ'
    o.scale = (W, H, 1); o.rotation_euler = (math.pi / 2, 0, 0); o.location = (cx, y_wall - 0.004, H / 2)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    bpy.ops.object.modifier_add(type='SOLIDIFY'); o.modifiers[-1].thickness = 0.02
    o.pass_index = idx
    m = bpy.data.materials.new('дверь по фото'); m.use_nodes = True; nt = m.node_tree; n = nt.nodes; b = n['Principled BSDF']
    ph = bpy.data.images.load(img); ti = n.new('ShaderNodeTexImage'); ti.image = ph
    iw, ih = ph.size
    # маска стекла: 1 — стекло, по описанию двери в пикселях фото (y от верха → строки снизу в Blender)
    mk = np.zeros((ih, iw), np.float32); sx, sy = iw / s['w'], ih / s['h']
    li = s['casing'] + s.get('stile_l', s['stile']); ri = s['w'] - s['casing'] - s.get('stile_r', s['stile'])
    gx0, gx1 = s.get('glass_x', [li, ri])
    for g in s['glass']: mk[int(g[0] * sy):int(g[1] * sy), int(gx0 * sx):int(gx1 * sx)] = 1
    for r in s.get('glass_rect', []): mk[int(r[1] * sy):int(r[3] * sy), int(r[0] * sx):int(r[2] * sx)] = 1
    mi = bpy.data.images.new('маска стекла', iw, ih, alpha=False); mi.colorspace_settings.name = 'Non-Color'
    px = np.ones((ih, iw, 4), np.float32); px[..., :3] = mk[::-1, :, None]; mi.pixels.foreach_set(px.ravel())
    tm = n.new('ShaderNodeTexImage'); tm.image = mi
    gr = s.get('glass_rough', 0.05)
    rough = n.new('ShaderNodeMapRange'); rough.inputs['To Min'].default_value = 0.45; rough.inputs['To Max'].default_value = gr
    nt.links.new(tm.outputs['Color'], rough.inputs['Value']); nt.links.new(rough.outputs['Result'], b.inputs['Roughness'])
    if s.get('mirror'):     # зеркало: металл и светлый цвет вместо снимка отражения на фото
        mx = n.new('ShaderNodeMix'); mx.data_type = 'RGBA'; mx.inputs['B'].default_value = (0.8, 0.8, 0.8, 1)
        nt.links.new(tm.outputs['Color'], mx.inputs['Factor']); nt.links.new(ti.outputs['Color'], mx.inputs['A'])
        nt.links.new(mx.outputs['Result'], b.inputs['Base Color']); nt.links.new(tm.outputs['Color'], b.inputs['Metallic'])
    else:
        nt.links.new(ti.outputs['Color'], b.inputs['Base Color'])
        if gr < 0.2:        # лаковое стекло — блестит
            cw = n.new('ShaderNodeMath'); cw.operation = 'MULTIPLY'; cw.inputs[1].default_value = 0.6
            nt.links.new(tm.outputs['Color'], cw.inputs[0]); nt.links.new(cw.outputs['Value'], b.inputs['Coat Weight'])
    o.data.materials.append(m)
    return [o]


if __name__ == '__main__':
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    a = dict(x.split('=', 1) for x in argv)
    s = json.load(open(a['spec'], encoding='utf-8'))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene; sc.render.engine = 'CYCLES'; sc.cycles.samples = 128
    sc.cycles.device = 'GPU'
    try:
        p = bpy.context.preferences.addons['cycles'].preferences; p.compute_device_type = 'CUDA'; p.get_devices()
        for d in p.devices: d.use = True
    except Exception: pass
    sc.view_settings.view_transform = 'Standard'; sc.view_settings.exposure = -0.55
    if a.get('photo'): build_door_photo(s, a['photo'], 0, 0)
    else: build_door(s, 0, 0)
    if a.get('alpha') == '1':           # для door_check: стена/пол есть (свет и тени), но в кадре прозрачные
        sc.render.film_transparent = True; sc.render.image_settings.color_mode = 'RGBA'
    for o in (box('стена', -1, 1, 0, 2.6, 0.03, 0.1, mat('стена', (235, 232, 228), 0.9), 0),
              box('пол', -1, 1, -0.01, 0, -1.5, 0, mat('пол', (200, 190, 175), 0.6), 0)):
        o.is_holdout = a.get('alpha') == '1'
    w = bpy.data.worlds.new('w'); sc.world = w; w.use_nodes = True
    w.node_tree.nodes['Background'].inputs[1].default_value = 0.6
    box('отражение', -2, 2, 0, 3, -4.2, -4.0, mat('светлая стена позади', (235, 232, 228), 0.9), 0)   # металлу и зеркалу есть что отражать
    bpy.ops.object.light_add(type='AREA', location=(1.5, -2.5, 1.2)); L = bpy.context.object
    L.data.energy = 150; L.data.size = 2; L.rotation_euler = (math.radians(65), 0, math.radians(15))
    bpy.ops.object.camera_add(location=(0, -3.2, 1.05), rotation=(math.pi / 2, 0, 0)); cam = bpy.context.object
    cam.data.type = 'ORTHO'; cam.data.ortho_scale = 2.3; sc.camera = cam
    sc.render.resolution_x, sc.render.resolution_y = 600, 1300
    sc.render.filepath = a['out']; bpy.ops.render.render(write_still=True)
