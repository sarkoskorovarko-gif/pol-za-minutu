"""Текстура всего пола комнаты из фото декора — доски раскладываются так же, как на сайте (photo.js).

Запуск:  python tools/blender/floor_tex.py <id декора> <папка вывода> [ширина_м высота_м]
Пишет floor_<id>.png (цвет) и floor_<id>_joint.png (стыки досок, для рельефа фаски).
"""
import json, sys
from pathlib import Path

import cv2
import numpy as np

import plank_src

ROOT = Path(__file__).resolve().parents[2]
PX = 800                               # точек на метр пола (с фото ×4 — 1400)
TEX4X = Path('D:/pol-ai/tex4x')         # увеличенные фото декоров (upscale_tex.py)
TEX_W_M = 1.3                          # как DEFAULT_TEX_W_M в photo.js


def h1(x, y):
    return np.modf(np.sin(x * 12.9898 + y * 78.233) * 43758.5453)[0] % 1.0


def vertical(img):
    """Волокна/доски на фото идут сверху вниз: перепады яркости по x сильнее, чем по y."""
    g = cv2.GaussianBlur(img.mean(2), (0, 0), 2)
    gx, gy = cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1)
    return float((gx ** 2).mean() / (gy ** 2).mean()) > 1.3


def build(d, w_m, h_m):
    big = TEX4X / f"{d['id']}.png"
    img = cv2.imdecode(np.fromfile(big if big.exists() else ROOT / 'data' / d['texture'], np.uint8), cv2.IMREAD_COLOR)[:, :, ::-1].astype(np.float32) / 255
    th, tw = img.shape[:2]
    s = d.get('texture_scale_m') or TEX_W_M                  # ширина ИСХОДНОГО фото, м
    texM = (s, s * th / tw)
    if not d.get('pattern') and vertical(img):               # доски на фото вертикально (35 из 108) — повернуть:
        img = np.ascontiguousarray(np.rot90(img))            # иначе в комнате рисунок идёт от стены, а не от окна (20.10)
        texM = (s * th / tw, s); th, tw = tw, th
    px = 1400 if big.exists() else PX
    W, H = int(w_m * px), int(h_m * px)
    fx, fy = np.meshgrid((np.arange(W) + 0.5) / px, (np.arange(H) + 0.5) / px)
    joint = np.ones((H, W), np.float32)
    if d.get('pattern') or not (d.get('board_len_mm') and d.get('board_w_mm')):
        u, v = fx / texM[0], fy / texM[1]
    else:
        L, Wb = d['board_len_mm'] / 1000, d['board_w_mm'] / 1000
        rows = d.get('tex_rows') or [0, min(1, Wb / texM[1])]
        row = np.floor(fy / Wb)
        x = fx + np.modf(row * 0.382 + h1(row, 7.0) * 0.25)[0] % 1.0 * L
        col = np.floor(x / L)
        lx, ly = x - col * L, fy - row * Wb
        nr = max(1.0, np.floor((1 - rows[0]) / rows[1] + 0.01))
        k = np.floor(h1(row, col) * nr)
        u0 = h1(col, row + 31.0) * max(0.0, 1 - L / texM[0])
        u, v = u0 + lx / texM[0], 1 - (rows[0] + (k + ly / Wb) * rows[1])
        seg = plank_src.segments(img)                        # доска = один цельный кусок доски с фото, без чужих стыков (22.10)
        if seg:
            sg = np.array(seg)[np.floor(h1(row + 5.3, col + 2.1) * len(seg)).astype(int) % len(seg)]   # (H, W, 4)
            sw = (sg[..., 3] - sg[..., 2]) * texM[0]            # длина куска, м
            span = np.minimum(sw, L)                             # длиннее доски — берём часть, короче — растягиваем (до ~2 раз)
            st = sg[..., 2] * texM[0] + h1(col + 9.7, row) * (sw - span)
            u = (st + lx / L * span) / texM[0]
            v = 1 - (sg[..., 0] + ly / Wb * (sg[..., 1] - sg[..., 0]))
        e = np.minimum(np.minimum(lx, L - lx), np.minimum(ly, Wb - ly))
        joint = np.clip(e / (0.0022 if d.get('chamfer') else 0.0008), 0, 1) ** 0.5
    mx = ((u % 1) * tw).astype(np.float32); my = (((1 - v) % 1) * th).astype(np.float32)
    c = cv2.remap(img, mx, my, cv2.INTER_CUBIC, borderMode=cv2.BORDER_WRAP)
    if not d.get('pattern') and d.get('board_len_mm'):
        hv = h1(col * 3.1, row * 1.7)[..., None]
        c = c * (0.94 + 0.12 * hv)
        g = c.mean(2, keepdims=True); s = (0.92 + 0.16 * h1(row * 2.3, col))[..., None]
        c = g + (c - g) * s
        c = c * (0.55 + 0.45 * joint[..., None])
    return np.clip(c, 0, 1), joint


if __name__ == '__main__':
    did, out = sys.argv[1], Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
    across = '--across' in sys.argv; sys.argv = [a for a in sys.argv if a != '--across']
    w_m, h_m = (float(sys.argv[3]), float(sys.argv[4])) if len(sys.argv) > 4 else (5.0, 4.2)
    d = next(x for x in json.load(open(ROOT / 'data' / 'catalog.json', encoding='utf-8'))['decors'] if x['id'] == did)
    if across:                                               # поперёк: доски от окна вглубь комнаты (по y) — строим повёрнутым и транспонируем
        c, j = build(d, h_m, w_m); c, j = np.ascontiguousarray(c.transpose(1, 0, 2)), np.ascontiguousarray(j.T)
    else:
        c, j = build(d, w_m, h_m)
    cv2.imencode('.png', (c[:, :, ::-1] * 255).astype(np.uint8))[1].tofile(out / f'floor_{did}.png')
    cv2.imencode('.png', (j * 255).astype(np.uint8))[1].tofile(out / f'floor_{did}_joint.png')
    print('ok', did, c.shape)
