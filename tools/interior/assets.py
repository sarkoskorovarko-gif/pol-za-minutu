"""Загрузка мебели по паспорту (library.json) — общая для passport.py и расстановщика.

put(key, x, y, facing) ставит предмет так, что его ПЕРЁД смотрит в сторону facing (радианы, 0 = +X, π/2 = +Y),
низ — на полу (или на высоте z), центр — в (x, y).
"""
import json, math, re
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

LIB_PATH = Path(__file__).with_name('library.json')
BK_DIR = Path('D:/pol-ai/bk_assets')
LIB = json.loads(LIB_PATH.read_text(encoding='utf-8'))


def load(key, coll=None):
    """Загрузить предмет, вернуть пустышку-родителя; модель приведена: центр (0,0), низ z=0, перёд → -Y (если паспорт знает front)."""
    p = LIB[key]; sc = bpy.context.scene
    with bpy.data.libraries.load(str(BK_DIR / f"{p['file']}.blend")) as (src, dst):
        names = list(src.objects); dst.objects = list(names)
    objs = [o for o in dst.objects if o and o.type not in ('CAMERA', 'LIGHT')]
    src_name = {o: n for o, n in zip(dst.objects, names) if o}   # имя в файле (в сцене может стать .001)
    keep = set()
    for o in objs:                                        # нужные части (по точному имени в файле) + всё, что к ним прицеплено
        if not p.get('parts') or src_name[o] in p['parts']:
            keep.add(o); keep.update(c for c in o.children_recursive if c.type not in ('CAMERA', 'LIGHT'))
    keep = [o for o in keep if src_name.get(o, o.name) not in p.get('hide', [])]
    coll = coll or sc.collection
    for o in keep:
        coll.objects.link(o)
        if src_name.get(o) in p.get('paint', {}) and o.type == 'MESH':
            col = p['paint'][src_name[o]]
            for i, ms in enumerate(o.material_slots):
                m = ms.material.copy(); ms.material = m
                b = next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
                if b:
                    for l in list(b.inputs['Base Color'].links): m.node_tree.links.remove(l)
                    b.inputs['Base Color'].default_value = (*col, 1)
    bpy.context.view_layer.update()
    mws = {o: o.matrix_world.copy() for o in keep}
    bpy.ops.object.empty_add(location=(0, 0, 0)); e = bpy.context.object; e.name = key
    roots = [o for o in keep if o.parent not in keep]     # вложенность не трогаем: только верхние детали — к пустышке
    for o in roots:
        o.parent = e; o.matrix_parent_inverse.identity(); o.matrix_world = mws[o]
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for o in keep if o.type == 'MESH' for c in o.bound_box]
    mn = Vector([min(q[i] for q in pts) for i in range(3)]); mx = Vector([max(q[i] for q in pts) for i in range(3)])
    off = Vector(((mn.x + mx.x) / 2, (mn.y + mx.y) / 2, mn.z))
    for o in roots:
        o.matrix_world.translation -= off
    if p.get('raise_top'):                                # столешница на нужную высоту: тянем главную часть, вещи на ней — вверх
        main = [o for o in roots if src_name.get(o) == p['parts'][0]]
        top = max((o.matrix_world @ Vector(c)).z for o in main for c in o.bound_box)
        for o in roots:
            if o in main: o.matrix_world = Matrix.Diagonal((1, 1, p['raise_top'] / top, 1)) @ o.matrix_world
            else: o.matrix_world.translation.z += p['raise_top'] - top
    # повернуть так, чтобы перёд смотрел в -Y (front — куда смотрит перёд в исходной модели, радианы)
    if 'front' in p:
        rot = -math.pi / 2 - p['front']
        for o in roots:
            o.matrix_world = Matrix.Rotation(rot, 4, 'Z') @ o.matrix_world
    if p.get('scale'):
        e.scale = [p['scale']] * 3
    return e, keep


def put(key, x, y, facing=-math.pi / 2, z=0.0, coll=None):
    e, _ = load(key, coll)
    e.location = (x, y, z); e.rotation_euler = (0, 0, facing + math.pi / 2)
    return e
