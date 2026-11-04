"""Слои дверей — к цвету готовой комнаты (после нейросети и цветокоррекции).

Запуск:  python tools/blender/door_match.py <папка рендера> <куда класть слои>
Множитель по каналам = нейтральная дверь в final_*.jpg / она же в room_blender.png (маска art_mask0001.png);
им умножаются все door_*.png. Урок: вечером слой без этого «светился» на тёмной комнате.
"""
import sys
from pathlib import Path

import cv2
import numpy as np

src, dst = Path(sys.argv[1]), Path(sys.argv[2])
m = cv2.erode(cv2.imread(str(src / 'art_mask0001.png'), 0), np.ones((7, 7), np.uint8)) > 128
raw = cv2.imread(str(src / 'room_blender.png')).astype(np.float64)
gains = []
for f in sorted(src.glob('final_*.jpg')):
    fin = cv2.imdecode(np.fromfile(str(f), np.uint8), 1).astype(np.float64)
    gains.append(np.median(fin[m], 0) / np.maximum(np.median(raw[m], 0), 1))
if not gains: sys.exit(f'нет final_*.jpg в {src}')   # иначе NaN и испорченные слои
g = np.median(gains, 0)
print('множитель B,G,R:', np.round(g, 3))
dst.mkdir(parents=True, exist_ok=True)
for f in sorted(src.glob('door_*.png')):
    im = cv2.imread(str(f), cv2.IMREAD_UNCHANGED).astype(np.float64)
    im[..., :3] = np.clip(im[..., :3] * g, 0, 255)
    cv2.imencode('.png', im.astype(np.uint8), [cv2.IMWRITE_PNG_COMPRESSION, 9])[1].tofile(str(dst / f.name))
print('ГОТОВО', dst)
