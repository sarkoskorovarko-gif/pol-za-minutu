"""Уточняет маску пола по самому фото: края мебели вместо грубых многоугольников.

Берёт разметку из data/photos.json (контур пола минус вырезы) и в узкой полосе
вокруг границ решает по цвету (OpenCV GrabCut), где пол, а где мебель.
Дальше полосы маска не меняется — ошибки не могут «уползти» далеко.
Результат: data/photos/masks/<id>.png (белое — пол). Сайт берёт его, если есть.

Запуск из папки проекта:  python tools/refine_masks.py [id ...]
"""
import json, sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
PHOTOS = ROOT / "data" / "photos"
OUT = PHOTOS / "masks"
BAND = 24      # пикселей фото: насколько граница пола может сдвинуться за контур
WORK = 1000    # размер для расчёта (по длинной стороне)


def poly_mask(d, shape):
    m = np.zeros(shape, np.uint8)
    cv2.fillPoly(m, [np.int32(np.round(d["floor"]))], 255)
    for h in d.get("holes", []):
        cv2.fillPoly(m, [np.int32(np.round(h))], 0)
    return m


def straight_walls(d, m, W, H):
    """Стороны контура пола у стен — прямые, проведённые через точную (но волнистую) границу
    GrabCut: и точно по краю на фото, и ровно. Сторона без надёжной опоры остаётся как в разметке."""
    P = np.array(d["floor"], float)
    n = len(P)
    edge = cv2.morphologyEx((m > 127).astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8))
    ys, xs = np.nonzero(edge)
    E = np.stack([xs, ys], 1).astype(float)
    e = 3
    on_border = lambda a: a[0] <= e or a[0] >= W - e or a[1] >= H - e or a[1] <= e
    rng = np.random.default_rng(1)
    lines = []
    for i in range(n):
        p, q = P[i], P[(i + 1) % n]
        L = np.linalg.norm(q - p)
        if L < 60 or (on_border(p) and on_border(q)):
            lines.append(None); continue
        u = (q - p) / L; nv = np.array([-u[1], u[0]])
        rel = E - p
        t, o = rel @ u, rel @ nv
        S = E[(t > 0.05 * L) & (t < 0.95 * L) & (np.abs(o) < 14)]
        if len(S) < 0.3 * L:
            lines.append(None); continue
        best, bi = None, 0
        for _ in range(300):
            a, b = S[rng.choice(len(S), 2, replace=False)]
            v = b - a; lv = np.linalg.norm(v)
            if lv < 0.2 * L:
                continue
            v /= lv; nn = np.array([-v[1], v[0]])
            inl = np.abs((S - a) @ nn) < 1.5
            if inl.sum() > bi:
                bi, best = inl.sum(), inl
        if best is None or bi < 0.4 * L:
            lines.append(None); continue
        Q = S[best]; mq = Q.mean(0)
        dv = np.linalg.eigh(np.cov((Q - mq).T))[1][:, 1]
        lines.append((mq, dv) if abs(dv @ u) > np.cos(np.radians(5)) else None)
    out = []
    for i in range(n):
        a, b = lines[i - 1], lines[i]
        pt = P[i]
        if a is not None and b is not None:
            A = np.array([a[1], -b[1]]).T
            if abs(np.linalg.det(A)) > 1e-6:
                x = a[0] + np.linalg.solve(A, b[0] - a[0])[0] * a[1]
                if np.linalg.norm(x - pt) < 30:
                    pt = x
        elif a is not None or b is not None:
            mq, dv = a if a is not None else b
            x = mq + ((pt - mq) @ dv) * dv
            if np.linalg.norm(x - pt) < 20:
                pt = x
        out.append(pt)
    return np.array(out), sum(l is not None for l in lines)


def refine(d):
    img = cv2.imdecode(np.fromfile(PHOTOS / d["file"], np.uint8), cv2.IMREAD_COLOR)  # путь с кириллицей
    H, W = img.shape[:2]
    base = poly_mask(d, (H, W))
    s = WORK / max(W, H)
    im = cv2.resize(img, (round(W * s), round(H * s)), interpolation=cv2.INTER_AREA)
    bm = cv2.resize(base, im.shape[1::-1], interpolation=cv2.INTER_NEAREST)
    b = max(2, round(BAND * s))
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * b + 1, 2 * b + 1))
    sure_fg = cv2.erode(bm, k)
    # «Точно не пол»: всё вне контура пола, а внутри вырезов — только их середина
    # (вырезы нарисованы с запасом; что в них похоже на пол — станет полом)
    fl = np.zeros_like(bm)
    cv2.fillPoly(fl, [np.int32(np.round(np.array(d["floor"]) * s))], 255)
    holes = cv2.bitwise_and(fl, 255 - bm)
    kc = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (6 * b + 1, 6 * b + 1))
    sure_bg = cv2.bitwise_or(cv2.erode(255 - fl, k), cv2.erode(holes, kc))
    gc = np.full(bm.shape, cv2.GC_PR_BGD, np.uint8)
    gc[bm > 0] = cv2.GC_PR_FGD
    gc[sure_fg > 0] = cv2.GC_FGD
    gc[sure_bg > 0] = cv2.GC_BGD
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.grabCut(im, gc, None, bgd, fgd, 6, cv2.GC_INIT_WITH_MASK)
    m = np.where((gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    # мелкий мусор убрать: дырочки и островки меньше ~3 px
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    m = cv2.resize(m, (W, H), interpolation=cv2.INTER_LINEAR)
    # Тонкие ножки мебели бывают цвета пола — GrabCut их «съедает».
    # Внутри вырезов чёткие контуры предметов (и всё между близкими контурами) — не пол.
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 40, 110)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))
    edges = cv2.dilate(edges, np.ones((5, 5), np.uint8))
    m[(base == 0) & (edges > 0)] = 0
    # вне полосы — как в разметке; край мягкий
    # менять можно внутри контура пола (с полосой) — стены и потолок не трогаем
    floor_full = np.zeros_like(base)
    cv2.fillPoly(floor_full, [np.int32(np.round(d["floor"]))], 255)
    zone = cv2.dilate(floor_full, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * BAND + 1,) * 2))
    # Границы со стенами уже прямые (tools/snap_floor.py) — по цвету их не трогаем:
    # По умолчанию — только вокруг мебели (вырезов); "exact_floor": false — уточнять и стены.
    if d.get("exact_floor", False):
        hz = np.zeros_like(base)
        for h in d.get("holes", []):
            cv2.fillPoly(hz, [np.int32(np.round(h))], 255)
        zone = cv2.dilate(hz, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * BAND + 1,) * 2))
    # Стены — прямые через точную границу GrabCut (ровно и по краю)
    floor_poly, nfit = straight_walls(d, m, W, H) if not d.get("exact_floor", False) else (np.array(d["floor"], float), 0)
    # GrabCut дальше нужен только вокруг мебели
    hz = np.zeros_like(base)
    for h in d.get("holes", []):
        cv2.fillPoly(hz, [np.int32(np.round(h))], 255)
    zone = cv2.dilate(hz, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * BAND + 1,) * 2))
    if d.get("no_grabcut"):        # мебель обведена точно вручную, а цвет пола как у плинтуса — не уточняем
        zone[:] = 0
    # Края мебели после GrabCut рваные — сглаживаем (убираем «зубчики», форма остаётся)
    ms = cv2.GaussianBlur(m.astype(np.float32), (0, 0), 2.0)
    m = np.where(ms > 127, 255, 0).astype(np.uint8)
    # Пол у стен — точный многоугольник с гладким краем: рисуем в 4 раза крупнее и уменьшаем
    big = np.zeros((H * 4, W * 4), np.uint8)
    # углы на краю кадра выносим за край — иначе у края фото остаётся полоска старого пола
    # и стены, которые подходят к краю кадра «чуть не доходя», продлеваем за край вдоль стены
    fp = floor_poly.copy()
    n_ = len(fp)
    on_b = lambda q: q[0] <= 0.5 or q[0] >= W - 0.5 or q[1] >= H - 0.5
    for i in range(n_):
        v = fp[i]
        for k in (-1, 1):
            nb = floor_poly[(i + k) % n_]
            if on_b(nb) or on_b(v):
                continue
            dv = v - nb
            for axis, lim in ((0, -6), (0, W + 6), (1, H + 6)):
                near = v[axis] < 25 if lim < 0 else v[axis] > (W if axis == 0 else H) - 25
                if near and abs(dv[axis]) > 1e-6 and np.sign(dv[axis]) == np.sign(lim - v[axis]):
                    t = (lim - nb[axis]) / dv[axis]
                    fp[i] = nb + dv * t
    fp[fp[:, 0] <= 8, 0] = -6; fp[fp[:, 0] >= W - 8, 0] = W + 6
    fp[fp[:, 1] >= H - 8, 1] = H + 6; fp[fp[:, 1] <= 8, 1] = -6
    cv2.fillPoly(big, [np.int32(np.round(fp * 4))], 255, lineType=cv2.LINE_AA)
    smooth = cv2.resize(big, (W, H), interpolation=cv2.INTER_AREA).astype(np.float32)
    for h in d.get("holes", []):
        hb = np.zeros((H * 4, W * 4), np.uint8)
        cv2.fillPoly(hb, [np.int32(np.round(np.array(h) * 4))], 255, lineType=cv2.LINE_AA)
        smooth = np.minimum(smooth, 255 - cv2.resize(hb, (W, H), interpolation=cv2.INTER_AREA).astype(np.float32))
    out = np.where(zone > 0, m.astype(np.float32), smooth)
    # "keep" — места, где пол точно не рисуем: ковёр или деревянная ножка цвета пола.
    # В обучение GrabCut их не даём (собьют его), применяем в самом конце.
    for k in d.get("keep", []):
        kb = np.zeros((H * 4, W * 4), np.uint8)
        cv2.fillPoly(kb, [np.int32(np.round(np.array(k) * 4))], 255, lineType=cv2.LINE_AA)
        out = np.minimum(out, 255 - cv2.resize(kb, (W, H), interpolation=cv2.INTER_AREA).astype(np.float32))
    # края мебели — чуть мягче (1 px), края стен уже гладкие
    soft = cv2.GaussianBlur(out, (0, 0), 0.7)
    out = np.where(zone > 0, soft, out)
    out = np.clip(out, 0, 255).astype(np.uint8)        # полный размер фото — без ступенек
    OUT.mkdir(exist_ok=True)
    cv2.imencode(".png", out)[1].tofile(OUT / f"{d['id']}.png")
    changed = np.mean(np.abs(m.astype(int) - base.astype(int)) > 128) * 100
    return round(changed, 2)


if __name__ == "__main__":
    data = json.loads((ROOT / "data" / "photos.json").read_text(encoding="utf-8"))
    ids = sys.argv[1:]
    for d in data:
        if not ids or d["id"] in ids:
            print(d["id"], d["title"], "— изменено", refine(d), "% фото")
