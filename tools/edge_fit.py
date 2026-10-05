"""Точные прямые вдоль стен: где именно пол переходит в плинтус/стену.

Для каждой стороны контура пола (кроме краёв кадра) берёт ~40 точек вдоль неё и в каждой
ищет поперёк (±RANGE px) самый резкий перепад яркости — это граница пола. По найденным
точкам проводит прямую устойчиво (RANSAC + МНК по «своим» точкам), углы контура —
пересечения соседних прямых. Если точек мало или прямая уехала далеко — сторону не трогает.

Запускать после snap_floor.py (он ставит стороны примерно — ±10 px, верх/низ плинтуса
различает по нейросети), этот скрипт доводит до пикселя:
    python tools/edge_fit.py [id ...]
"""
import json, sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
PH = ROOT / "data" / "photos.json"
RANGE = 25       # насколько искать поперёк стороны, px
SAMPLES = 40


def bilinear(img, x, y):
    h, w = img.shape
    x = np.clip(x, 0, w - 1.001); y = np.clip(y, 0, h - 1.001)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - x0, y - y0
    return (img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x0 + 1] * fx * (1 - fy)
            + img[y0 + 1, x0] * (1 - fx) * fy + img[y0 + 1, x0 + 1] * fx * fy)


def fit_side(gray, p, q, inside, floor_med):
    """inside — точка внутри пола (чтобы знать, с какой стороны пол)."""
    H, W = gray.shape
    e = 3
    edge = lambda a: a[0] <= e or a[0] >= W - e or a[1] >= H - e or a[1] <= e
    if edge(p) and edge(q):
        return None
    d = q - p; L = np.linalg.norm(d)
    if L < 60:
        return None
    u = d / L; n = np.array([-u[1], u[0]])
    if (inside - p) @ n < 0:
        n = -n                                          # n смотрит в сторону пола
    offs = np.arange(-RANGE, RANGE + 0.01, 0.5)
    pts = []
    for t in np.linspace(0.06, 0.94, SAMPLES) * L:
        c = p + u * t
        xs, ys = c[0] + offs * n[0], c[1] + offs * n[1]
        prof = bilinear(gray, xs, ys)
        gr = np.abs(np.gradient(prof))
        # годится только перепад «пол | не пол»: со стороны пола яркость как у пола, с другой — нет
        # (так верх плинтуса — «стена | плинтус» — не путается с низом)
        ok = np.zeros_like(gr, bool)
        for j in range(4, len(offs) - 4):
            fside, oside = prof[min(len(prof) - 1, j + 6)], prof[max(0, j - 6)]
            ok[j] = abs(fside - floor_med) + 6 < abs(oside - floor_med)
        gr = np.where(ok, gr, 0)
        k = int(np.argmax(gr))
        if gr[k] < 2.0 or k in (0, len(offs) - 1):      # перепада нет — пропуск
            continue
        # уточнение до долей пикселя по параболе
        a, b, c3 = gr[k - 1], gr[k], gr[k + 1]
        dk = 0.5 * (a - c3) / (a - 2 * b + c3) if (a - 2 * b + c3) != 0 else 0
        o = offs[k] + dk * 0.5
        pts.append(c + o * n)
    if len(pts) < 10:
        return None
    P = np.array(pts)
    best, bi = None, 0
    rng = np.random.default_rng(1)
    for _ in range(200):                                # RANSAC: прямая, на которой больше всего точек
        i, j = rng.choice(len(P), 2, replace=False)
        v = P[j] - P[i]
        if np.linalg.norm(v) < 10:
            continue
        v /= np.linalg.norm(v); nn = np.array([-v[1], v[0]])
        inl = np.abs((P - P[i]) @ nn) < 1.2
        if inl.sum() > bi:
            bi, best = inl.sum(), inl
    if best is None or bi < max(8, 0.5 * len(P)):
        return None
    Q = P[best]
    m = Q.mean(0)
    dv = np.linalg.eigh(np.cov((Q - m).T))[1][:, 1]
    if abs(dv @ u) < np.cos(np.radians(4)):             # направление сильно другое — не верим
        return None
    return m, dv


def intersect(l1, l2):
    (p1, d1), (p2, d2) = l1, l2
    A = np.array([d1, -d2]).T
    if abs(np.linalg.det(A)) < 1e-6:
        return None
    t = np.linalg.solve(A, p2 - p1)
    return p1 + t[0] * d1


def run(d, img):
    gray = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (3, 3), 0).astype(np.float32)
    H, W = gray.shape
    P = np.array(d["floor"], float)
    n = len(P)
    mask = np.zeros((H, W), np.uint8); cv2.fillPoly(mask, [np.int32(P)], 1)
    inner = cv2.erode(mask, np.ones((31, 31), np.uint8)) > 0
    floor_med = float(np.median(gray[inner])) if inner.any() else float(np.median(gray[mask > 0]))
    lines = []
    for i in range(n):
        p, q = P[i], P[(i + 1) % n]
        mid = (p + q) / 2
        # точка внутри пола рядом с серединой стороны
        dd = (q - p) / max(np.linalg.norm(q - p), 1e-6); nn = np.array([-dd[1], dd[0]])
        inside = mid + nn * 15 if mask[int(np.clip(mid[1] + nn[1] * 15, 0, H - 1)), int(np.clip(mid[0] + nn[0] * 15, 0, W - 1))] else mid - nn * 15
        lines.append(fit_side(gray, p, q, inside, floor_med))
    out, moved = [], []
    for i in range(n):
        a, b = lines[i - 1], lines[i]
        pt = P[i]
        if a is not None and b is not None:
            x = intersect(a, b)
            if x is not None and np.linalg.norm(x - pt) < 40:
                pt = x
        elif a is not None or b is not None:
            m, dv = a if a is not None else b
            x = m + ((pt - m) @ dv) * dv
            if np.linalg.norm(x - pt) < 30:
                pt = x
        out.append([round(float(np.clip(pt[0], 0, W)), 2), round(float(np.clip(pt[1], 0, H)), 2)])
        moved.append(round(float(np.linalg.norm(np.array(out[-1]) - P[i])), 1))
    d["floor"] = out
    return moved, sum(l is not None for l in lines)


if __name__ == "__main__":
    data = json.loads(PH.read_text(encoding="utf-8"))
    ids = sys.argv[1:]
    for d in data:
        if ids and d["id"] not in ids:
            continue
        img = cv2.imdecode(np.fromfile(ROOT / "data" / "photos" / d["file"], np.uint8), cv2.IMREAD_COLOR)
        moved, fitted = run(d, img)
        print(d["id"], "сторон уточнено:", fitted, "сдвиг углов, px:", moved)
    sys.path.insert(0, str(Path(__file__).parent))
    from save_photos_json import dump
    dump(data, PH)
