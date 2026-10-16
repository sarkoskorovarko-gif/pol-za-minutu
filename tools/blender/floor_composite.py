"""Склейка: всё, кроме пола, — от нейросети (room.png после ai_realism.py), пол — из Blender (room_<id>.png).

Запуск:  python tools/blender/floor_composite.py <папка рендера> <папка полов> <id> [id ...]
Пишет <папка полов>/final_<id>.jpg.
"""
import sys
from pathlib import Path

import cv2
import numpy as np


def rd(p, flag=cv2.IMREAD_COLOR):
    return cv2.imdecode(np.fromfile(p, np.uint8), flag)


src, fl = Path(sys.argv[1]), Path(sys.argv[2])
ai = rd(src / 'room.png').astype(np.float32)
m = rd(src / 'floor_mask0001.png', cv2.IMREAD_GRAYSCALE).astype(np.float32) / 255
m = cv2.GaussianBlur(m, (0, 0), 1.2)[..., None]          # мягкий край, без «ореола»
lin = lambda x: (x / 255) ** 2.2
white = cv2.resize(rd(src / 'room_blender.png'), (ai.shape[1], ai.shape[0])).astype(np.float32)   # белый пол: только свет
ROOT = Path(__file__).resolve().parents[2]
for did in sys.argv[3:]:
    f = rd(fl / f'room_{did}.png').astype(np.float32)
    f = cv2.resize(f, (ai.shape[1], ai.shape[0]), interpolation=cv2.INTER_AREA)
    # цвет как у образца: ожидаемый пол = свет (белый пол) × средний цвет фото декора
    tex = lin(rd(ROOT / 'data' / 'textures' / f'{did}.jpg').reshape(-1, 3).astype(np.float32).mean(0))
    w = m[..., 0] > 0.5
    want = (lin(white[w]) * tex).mean(0); have = lin(f[w]).mean(0)
    gain = (want / have) ** 0.7                               # не до конца: тени и блики остаются из Blender
    f = 255 * (lin(f) * gain).clip(0, 1) ** (1 / 2.2)
    print(did, 'color x', gain.round(2))
    out = ai * (1 - m) + f * m
    cv2.imencode('.jpg', out.clip(0, 255).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tofile(fl / f'final_{did}.jpg')
    print('ok', did)
