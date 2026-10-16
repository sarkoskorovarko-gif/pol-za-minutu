r"""Пол конкретного декора, нарисованный в Blender (настоящий свет, отражения, фаска).

Берёт room.blend (из room_living.py) и floor_<id>.png (из floor_tex.py), рендерит room_<id>.png.
Запуск: D:\pol-ai\blender\blender.exe -b <папка>/room.blend -P tools/blender/floor_render.py -- <папка полов> <samples> <id> [id ...]
"""
import sys
from pathlib import Path

import bpy

argv = sys.argv[sys.argv.index('--') + 1:]
FL, SAMPLES, IDS = Path(argv[0]), int(argv[1]), argv[2:]
sc = bpy.context.scene
sc.cycles.samples = SAMPLES
prefs = bpy.context.preferences.addons['cycles'].preferences   # видеокарта: в .blend не сохраняется
prefs.compute_device_type = 'OPTIX'; prefs.get_devices()
for d in prefs.devices: d.use = d.type == 'OPTIX'
sc.cycles.device = 'GPU'
for n in sc.node_tree.nodes:
    if n.type == 'OUTPUT_FILE': n.mute = True
floor = bpy.data.objects['ПОЛ']
W, D = floor.dimensions.x, floor.dimensions.y
for did in IDS:
    m = bpy.data.materials.new(f'пол {did}'); m.use_nodes = True
    nt = m.node_tree; bsdf = nt.nodes['Principled BSDF']
    co = nt.nodes.new('ShaderNodeTexCoord'); mp = nt.nodes.new('ShaderNodeMapping')
    mp.inputs['Location'].default_value = (0.5, 0.5, 0); mp.inputs['Scale'].default_value = (1 / W, 1 / D, 1)
    # Mapping: сначала масштаб, потом сдвиг — переводим метры от центра пола в 0..1
    mp.vector_type = 'POINT'
    nt.links.new(co.outputs['Object'], mp.inputs['Vector'])
    tex = nt.nodes.new('ShaderNodeTexImage'); tex.image = bpy.data.images.load(str(FL / f'floor_{did}.png'))
    tex.extension = 'EXTEND'; nt.links.new(mp.outputs['Vector'], tex.inputs['Vector'])
    nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    jt = nt.nodes.new('ShaderNodeTexImage'); jt.image = bpy.data.images.load(str(FL / f'floor_{did}_joint.png'))
    jt.image.colorspace_settings.name = 'Non-Color'; jt.extension = 'EXTEND'
    nt.links.new(mp.outputs['Vector'], jt.inputs['Vector'])
    bump = nt.nodes.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = 0.35; bump.inputs['Distance'].default_value = 0.002
    nt.links.new(jt.outputs['Color'], bump.inputs['Height'])
    # поры: рельеф по рисунку декора (тёмные волокна — углубления), блеск тоже чуть разный
    pores = nt.nodes.new('ShaderNodeBump'); pores.inputs['Strength'].default_value = 0.12; pores.inputs['Distance'].default_value = 0.0005
    nt.links.new(tex.outputs['Color'], pores.inputs['Height']); nt.links.new(bump.outputs['Normal'], pores.inputs['Normal'])
    nt.links.new(pores.outputs['Normal'], bsdf.inputs['Normal'])
    rr = nt.nodes.new('ShaderNodeMapRange'); rr.inputs['To Min'].default_value = 0.30; rr.inputs['To Max'].default_value = 0.20
    nt.links.new(tex.outputs['Color'], rr.inputs['Value']); nt.links.new(rr.outputs['Result'], bsdf.inputs['Roughness'])
    bsdf.inputs['Specular IOR Level'].default_value = 0.5
    floor.data.materials[0] = m
    sc.render.filepath = str(FL / f'room_{did}.png')
    bpy.ops.render.render(write_still=True)
    print('ПОЛ', did, flush=True)
