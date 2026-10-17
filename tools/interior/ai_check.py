"""Проверка после нейросети: что она ДОРИСОВАЛА или ВЫБРОСИЛА по сравнению с кадром Blender.

Запуск: python tools/interior/ai_check.py <папка прогона>
Итог: <папка>/ai_check.jpg (красные рамки — подозрительные места), код 1 — есть находки.
Ищет крупные пятна контуров, которых не было в Blender (новые предметы), и наоборот (пропавшие).
"""
import sys
from pathlib import Path

import cv2
import numpy as np

AREA = 0.004          # доля кадра: пятно меньше — шум, не считаем


def load(p, size=None):
    im = cv2.imdecode(np.fromfile(str(p), np.uint8), 1)
    return cv2.resize(im, size) if size else im


def edges(im):
    g = cv2.GaussianBlur(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    return cv2.Canny(g, 60, 150)


def blobs(extra, total):
    m = cv2.morphologyEx(extra, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    n, _, st, _ = cv2.connectedComponentsWithStats(m)
    return [st[i, :4] for i in range(1, n) if st[i, 4] > AREA * total]


def main(d):
    d = Path(d)
    ai = load(d / 'room_ai.png')
    h, w = ai.shape[:2]
    bl = load(d / 'room_blender.png', (w, h))
    ea, eb = edges(ai), edges(bl)
    k = np.ones((15, 15), np.uint8)
    new = cv2.bitwise_and(ea, cv2.bitwise_not(cv2.dilate(eb, k)))     # есть у нейросети, не было в Blender
    gone = cv2.bitwise_and(eb, cv2.bitwise_not(cv2.dilate(ea, k)))    # было в Blender, пропало
    out = ai.copy()
    found = []
    for name, m, col in (('новое', new, (0, 0, 255)), ('пропало', gone, (255, 0, 0))):
        for x, y, bw, bh in blobs(m, w * h):
            cv2.rectangle(out, (x, y), (x + bw, y + bh), col, 4)
            found.append(f'{name}: x {x}-{x + bw}, y {y}-{y + bh}' + (' (у края кадра)' if x < 0.05 * w or x + bw > 0.95 * w else ''))
    cv2.imencode('.jpg', out, [1, 85])[1].tofile(str(d / 'ai_check.jpg'))
    print('\n'.join(found) or 'нейросеть ничего крупного не дорисовала и не выбросила')
    return 1 if found else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
