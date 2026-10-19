"""Подтянуть яркость и цвет пола к фото декора (после grade.py).

Запуск: python tools/interior/floor_match.py <папка прогона> <декор> ...
Почему: свет комнаты и тон-кривая AgX сжимают разницу между декорами примерно вдвое
(светлый 226 → 154, тёмный 73 → 89; замер 19.10). Человек выбирает пол по цвету — цвет должен совпадать.
Опора — EPL273 (на нём вся комната настроена): пол в комнате = фото × REF. Подтягиваем на ALPHA, не до конца,
иначе пол выглядит «наклеенным». Только по маске пола (мягкий край), тени и блики сохраняются (умножение).
"""
import sys
from pathlib import Path

import cv2
import numpy as np

FLOORS = Path('D:/pol-ai/bk_full/floors')
REF = 1.05          # EPL273: пол в комнате / фото декора
ALPHA = 0.85        # насколько подтягиваем (1 — до конца)
CHROMA = 1.0        # насколько возвращаем оттенок (тёплый/холодный)


def rd(p):
    return cv2.imdecode(np.fromfile(str(p), np.uint8), 1)


def L(c):
    return 0.114 * c[..., 0] + 0.587 * c[..., 1] + 0.299 * c[..., 2]


def match(out, d):
    f = rd(out / f'final_{d}.jpg').astype(np.float32)
    m = (rd(out / 'floor_mask0001.png')[..., 0] > 128).astype(np.float32)
    m = cv2.resize(m, (f.shape[1], f.shape[0]))
    hard = m > 0.5
    m = cv2.GaussianBlur(m, (0, 0), 6)[..., None]                 # мягкий край у плинтуса и ножек
    photo = rd(FLOORS / f'floor_{d}.png').reshape(-1, 3).mean(0, dtype=np.float64)   # float32 на 13 млн точек врёт на треть
    have = f[hard].mean(0)
    want_l = min(L(photo) * REF, 215)                            # не выбивать в белое
    gl = (want_l / L(have)) ** ALPHA
    # оттенок: соотношение каналов как у фото (частично)
    tint = (photo / L(photo)) / (have / L(have))
    gain = gl * tint ** CHROMA
    res = f * (1 - m) + np.clip(f * gain, 0, 255) * m
    cv2.imencode('.jpg', res.astype(np.uint8), [1, 93])[1].tofile(str(out / f'final_{d}.jpg'))
    print(d, 'пол', int(L(have)), '→', int(L(res[hard].mean(0))), 'фото', int(L(photo)))


if __name__ == '__main__':
    for d in sys.argv[2:]:
        match(Path(sys.argv[1]), d)
