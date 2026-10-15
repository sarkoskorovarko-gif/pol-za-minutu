"""Готовый рендер из Blender → комната на сайте.

Берёт room.png, floor_mask0001.png, room.json из папки рендера и кладёт:
data/photos/<id>.jpg, masks/<id>.png, thumbs/<id>.jpg и запись в data/photos.json (render: true).
Запуск из папки проекта:  python tools/blender/to_site.py <папка рендера> <id> "<название>"
"""
import json, sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from save_photos_json import dump

src, rid, title = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
P = ROOT / 'data' / 'photos'
img = cv2.imread(str(src / 'room.png'))
cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tofile(P / f'{rid}.jpg')
th = cv2.imdecode(np.fromfile(next((P / 'thumbs').glob('r2*.jpg')), np.uint8), 1)   # размер как у остальных
cv2.imencode('.jpg', cv2.resize(img, th.shape[1::-1], interpolation=cv2.INTER_AREA), [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tofile(P / 'thumbs' / f'{rid}.jpg')
m = cv2.imread(str(src / 'floor_mask0001.png'), 0)
cv2.imencode('.png', m)[1].tofile(P / 'masks' / f'{rid}.png')
# отражения в полу: только там, где пол (остальное чёрное — файл маленький)
rf = cv2.imread(str(src / 'room_refl.png'))
if rf is not None:
    (P / 'refl').mkdir(exist_ok=True)
    rf = (rf.astype(np.float32) * (cv2.GaussianBlur(m, (0, 0), 2)[..., None] / 255.0)).astype(np.uint8)
    cv2.imencode('.jpg', rf, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tofile(P / 'refl' / f'{rid}.jpg')
cs, _ = cv2.findContours((m > 127).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
poly = cv2.approxPolyDP(max(cs, key=cv2.contourArea), 2.0, True)[:, 0].tolist()
r = json.load(open(src / 'room.json'))
pj = ROOT / 'data' / 'photos.json'
data = json.loads(pj.read_text(encoding='utf-8'))
old = next((i for i, x in enumerate(data) if x['id'] == rid), None)
entry = {'id': rid, 'title': title, 'file': f'{rid}.jpg', 'img': r['img'], 'quad': r['quad'], 'size': r['size'],
         'floor': poly, 'holes': [], 'windows': [], 'focus': [800, 800], 'render': True}
if old is None: data.insert(0, entry)
else: data[old] = entry
dump(data, pj)
print(rid, title, '— пол', round((m > 127).mean() * 100), '% кадра')
