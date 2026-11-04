"""Слой двери для сайта: та же комната (room.blend), видна только дверь, остальное прозрачно, но даёт свет и тени.

Запуск:  blender -b <папка>/room.blend -P tools/blender/door_layer.py -- <папка> <фото двери.jpg> ...
Пишет <папка>/door_<имя фото>.png (RGBA). Сайт кладёт слой поверх комнаты с любым полом.
"""
import sys
from pathlib import Path

import bpy

argv = sys.argv[sys.argv.index('--') + 1:]
OUT, IMGS = Path(argv[0]), argv[1:]
sc = bpy.context.scene
dr = bpy.data.objects['ДВЕРЬ']
for o in sc.objects:                                   # остальное — «дыра» в кадре, но свет и тени остаются
    if o.type == 'MESH' and o is not dr: o.is_holdout = True
sc.render.film_transparent = True
sc.use_nodes = False                                   # маски и глубина уже сняты в room_living.py
sc.render.image_settings.file_format = 'PNG'; sc.render.image_settings.color_mode = 'RGBA'
nt = dr.data.materials[0].node_tree
ti = next((n for n in nt.nodes if n.type == 'TEX_IMAGE'), None) or nt.nodes.new('ShaderNodeTexImage')
nt.links.new(ti.outputs['Color'], nt.nodes['Principled BSDF'].inputs['Base Color'])
for f in IMGS:
    ti.image = bpy.data.images.load(f)
    sc.render.filepath = str(OUT / f'door_{Path(f).stem}.png')
    bpy.ops.render.render(write_still=True)
print('ГОТОВО', OUT)
