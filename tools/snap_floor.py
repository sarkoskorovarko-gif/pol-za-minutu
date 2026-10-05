"""Притягивает стороны контура пола к настоящим линиям на фото (низ стен, плинтусов).

Для каждой стороны контура ищет рядом (до 25 px) отрезки той же направленности
(OpenCV LSD), подгоняет по ним прямую и пересчитывает углы как пересечения
соседних прямых. Стороны по краю кадра не трогает.

Запуск:  python tools/snap_floor.py r20 [r21 ...]   — правит floor в data/photos.json
"""
import json, sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
PH = ROOT / "data" / "photos.json"
NEAR, ANG = 25, 4.0


def fit_side(p, q, segs, W, H, aid=None):
    e = 3
    on_edge = lambda a: a[0] <= e or a[0] >= W - e or a[1] >= H - e or a[1] <= e
    if on_edge(p) and on_edge(q):
        return None
    d = q - p
    L = np.linalg.norm(d)
    if L < 40:
        return None
    u = d / L
    n = np.array([-u[1], u[0]])
    pts, wts = [], []
    for s in segs:
        a, b = s[:2], s[2:]
        v = b - a
        lv = np.linalg.norm(v)
        if lv < 15 or abs(v @ u) / lv < np.cos(np.radians(ANG)):
            continue
        for c in (a, b, (a + b) / 2):
            t = (c - p) @ u
            if -10 < t < L + 10 and abs((c - p) @ n) < NEAR:
                pts.append(c); wts.append(lv)
    if len(pts) < 4:
        return None
    pts, wts = np.array(pts), np.array(wts)
    if aid is not None:
        # несколько параллельных линий (верх и низ плинтуса, стык досок) — берём ту,
        # что ближе к границе пола по нейросети (её точность ±5 px, плинтус ~15 px)
        dd = np.array([aid[int(np.clip(c[1], 0, H - 1)), int(np.clip(c[0], 0, W - 1))] for c in pts])
        wts = wts * np.exp(-(dd / 5.0) ** 2)
        if wts.sum() < 1e-6:
            return None
    # нижняя из найденных линий — граница пола (низ плинтуса), если их несколько
    off = (pts - p) @ n
    m = (pts * wts[:, None]).sum(0) / wts.sum()
    c = np.cov((pts - m).T, aweights=wts)
    w, v = np.linalg.eigh(c)
    dirv = v[:, 1]
    return m, dirv


def intersect(l1, l2):
    (p1, d1), (p2, d2) = l1, l2
    A = np.array([d1, -d2]).T
    if abs(np.linalg.det(A)) < 1e-6:
        return None
    t = np.linalg.solve(A, p2 - p1)
    return p1 + t[0] * d1


def fit_side_ai(p, q, edge_pts, segs, W, H):
    """Прямая стороны по границе пола нейросети (выпрямленной), уточнённая чёткими линиями фото."""
    e = 3
    on_edge = lambda a: a[0] <= e or a[0] >= W - e or a[1] >= H - e or a[1] <= e
    if on_edge(p) and on_edge(q):
        return None
    d = q - p; L = np.linalg.norm(d)
    if L < 40:
        return None
    u = d / L; n = np.array([-u[1], u[0]])
    rel = edge_pts - p
    t, o = rel @ u, rel @ n
    sel = edge_pts[(t > L * 0.08) & (t < L * 0.92) & (np.abs(o) < NEAR)]
    if len(sel) < 20:
        return None
    vx, vy, x0, y0 = cv2.fitLine(sel.astype(np.float32), cv2.DIST_HUBER, 0, 0.01, 0.01).ravel()
    m, dv = np.array([x0, y0]), np.array([vx, vy])
    if abs(dv @ u) < np.cos(np.radians(8)):          # нейросеть «увела» направление — не верим
        return None
    nn = np.array([-dv[1], dv[0]])
    pts, wts = [], []                                # чёткие отрезки в 4 px от этой прямой
    for s in segs:
        a, b = s[:2], s[2:]; v = b - a; lv = np.linalg.norm(v)
        if lv < 15 or abs(v @ dv) / lv < np.cos(np.radians(ANG)):
            continue
        if abs((a - m) @ nn) < 4 and abs((b - m) @ nn) < 4:
            pts += [a, b]; wts += [lv, lv]
    if len(pts) >= 4:
        P, w = np.array(pts), np.array(wts)
        m = (P * w[:, None]).sum(0) / w.sum()
        ev = np.linalg.eigh(np.cov((P - m).T, aweights=w))[1][:, 1]
        dv = ev
    return m, dv


def snap(img, poly, aid=None, edge_pts=None):
    H, W = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    segs = cv2.createLineSegmentDetector().detect(gray)[0].reshape(-1, 4)
    P = np.array(poly, float)
    n = len(P)
    lines = []
    for i in range(n):
        f = fit_side_ai(P[i], P[(i + 1) % n], edge_pts, segs, W, H) if edge_pts is not None else None
        if f is None:
            f = fit_side(P[i], P[(i + 1) % n], segs, W, H, aid)
        lines.append(f)
    out = []
    for i in range(n):
        a, b = lines[i - 1], lines[i]       # стороны до и после вершины i
        pt = P[i]
        if a is not None and b is not None:
            x = intersect(a, b)
            if x is not None and np.linalg.norm(x - pt) < 40:
                pt = x
        elif a is not None or b is not None:
            m, d = a if a is not None else b   # проекция на найденную прямую
            pt = m + ((pt - m) @ d) * d
            if np.linalg.norm(pt - P[i]) > 30:
                pt = P[i]
        out.append([round(float(np.clip(pt[0], 0, W)), 1), round(float(np.clip(pt[1], 0, H)), 1)])
    moved = [round(float(np.linalg.norm(np.array(o) - p)), 1) for o, p in zip(out, P)]
    return out, moved


if __name__ == "__main__":
    data = json.loads(PH.read_text(encoding="utf-8"))
    for pid in sys.argv[1:]:
        d = next(x for x in data if x["id"] == pid)
        img = cv2.imdecode(np.fromfile(ROOT / "data" / "photos" / d["file"], np.uint8), cv2.IMREAD_COLOR)
        # граница пола по нейросети (tools/ai_floor.py кладёт её в D:/pol-ai/ai_masks)
        aid = None
        edge_pts = None
        ap = Path(r"D:/pol-ai/ai_masks") / f"{pid}.png"
        if ap.exists():
            am = cv2.resize(cv2.imdecode(np.fromfile(ap, np.uint8), 0), img.shape[1::-1]) > 127
            edge = cv2.morphologyEx(am.astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8))
            aid = cv2.distanceTransform(1 - edge, cv2.DIST_L2, 5)
            ys, xs = np.nonzero(edge)
            edge_pts = np.stack([xs, ys], 1).astype(float)
        d["floor"], moved = snap(img, d["floor"], aid, edge_pts if aid is not None else None)
        print(pid, "сдвиг углов, px:", moved)
    sys.path.insert(0, str(Path(__file__).parent))
    from save_photos_json import dump
    dump(data, PH)
