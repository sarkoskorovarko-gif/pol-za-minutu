"""Фото декора → цельные полосы досок без стыков с фото.

На фото EGGER несколько досок со своими стыками (продольными и торцевыми). Если резать фото полосами
своей ширины, в одну доску попадают чужие стыки и куски соседних досок — пол выглядит «лоскутами» (22.10).
Здесь: находим ряды досок на фото, стираем все стыки фото (inpaint) и отдаём список рядов [y0, y1] в долях высоты.
"""
import cv2
import numpy as np


def _peaks(prof, min_gap, k=2.5):
    """Тёмные линии: провалы профиля яркости ниже медианы на k сигм (после снятия плавного хода)."""
    p = prof - cv2.GaussianBlur(prof.reshape(-1, 1), (0, 0), 15).ravel()
    thr = -k * np.std(p)
    idx = [i for i in range(1, len(p) - 1) if p[i] < thr and p[i] <= p[i - 1] and p[i] <= p[i + 1]]
    out = []
    for i in sorted(idx, key=lambda i: p[i]):
        if all(abs(i - j) >= min_gap for j in out): out.append(i)
    return sorted(out)


def _joints(band, W):
    """Торцевой стык — тёмная линия через ВСЮ высоту ряда (сучок/волокно так не умеют)."""
    d = band[:, 3:-3] - (band[:, :-6] + band[:, 6:]) / 2           # колонка темнее соседей в 3 px
    score = (d < -0.025).mean(0)
    cs = [i + 3 for i in range(1, len(score) - 1) if score[i] > 0.6 and score[i] >= score[i - 1] and score[i] >= score[i + 1]]
    out = []
    for c in sorted(cs, key=lambda c: -score[c - 3]):
        if all(abs(c - o) >= max(8, W // 10) for o in out): out.append(c)
    return sorted(out)


def segments(img, min_frac=0.3):
    """img float32 0..1 (H, W, 3), доски вдоль x. → куски досок фото [(v0, v1, u0, u1)] в долях (без стыков внутри) или None.
    Кусок — одна доска фото между её стыками; доска на полу берёт рисунок только из одного куска."""
    H, W = img.shape[:2]
    g = img.mean(2)
    rows = _peaks(g.mean(1), max(8, H // 12))
    cuts = [0] + rows + [H]
    bands = [(a, b) for a, b in zip(cuts, cuts[1:]) if b - a > H // 12]
    if len(bands) < 2: return None
    pad = 4                                                # у стыка фаска/тень — не берём
    out = []
    for a, b in bands:
        band = g[a + 3:b - 3]
        cs = _joints(band, W) if band.shape[0] >= 5 else []
        xs = [0] + cs + [W]
        for x0, x1 in zip(xs, xs[1:]):
            if x1 - x0 >= W * min_frac: out.append(((a + pad) / H, (b - pad) / H, (x0 + (pad if x0 else 0)) / W, (x1 - (pad if x1 < W else 0)) / W))
    return out or None
