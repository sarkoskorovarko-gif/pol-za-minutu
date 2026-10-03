"""Перспектива пола по самому фото: точки схода из прямых линий + высота камеры.

1) Находит на фото отрезки (OpenCV LSD) и ищет две горизонтальные точки схода
   (линии вдоль стен, плинтусов, досок, мебели) — RANSAC.
2) По ним — фокус камеры и наклон пола. Масштаб в метрах — из высоты камеры
   (у фото квартир обычно 1,2–1,5 м; по умолчанию 1,35 м).
3) Пишет quad/size для data/photos.json и картинку проверки с сеткой 0,5 м.

Запуск:  python tools/auto_quad.py r10 [высота_камеры]
Нужны поля floor (контур пола) у записи в photos.json. Результат — в photos.json.
"""
import json, sys, random
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
PH = ROOT / "data" / "photos.json"
OUT = Path(__file__).resolve().parent / "check"


def segments(gray):
    lsd = cv2.createLineSegmentDetector()
    lines = lsd.detect(gray)[0]
    if lines is None:
        return np.zeros((0, 4))
    L = lines.reshape(-1, 4)
    ln = np.hypot(L[:, 2] - L[:, 0], L[:, 3] - L[:, 1])
    return L[ln > gray.shape[1] * 0.04]


def homog_line(s):
    return np.cross([s[0], s[1], 1.0], [s[2], s[3], 1.0])


def vp_support(vp, segs, tol_deg=1.5):
    """Сколько (по длине) отрезков смотрят в точку vp (vp — однородные координаты)."""
    mid = (segs[:, :2] + segs[:, 2:]) / 2
    d = segs[:, 2:] - segs[:, :2]
    if abs(vp[2]) < 1e-9:
        to = np.tile(vp[:2], (len(segs), 1))
    else:
        to = vp[:2] / vp[2] - mid
    cos = np.abs((d * to).sum(1)) / (np.linalg.norm(d, axis=1) * np.linalg.norm(to, axis=1) + 1e-9)
    ok = cos > np.cos(np.radians(tol_deg))
    return ok, (np.linalg.norm(d, axis=1) * ok).sum()


def ransac_vp(segs, iters=3000, exclude=None):
    best, bs = None, 0
    n = len(segs)
    for _ in range(iters):
        i, j = random.sample(range(n), 2)
        vp = np.cross(homog_line(segs[i]), homog_line(segs[j]))
        if np.linalg.norm(vp) < 1e-9:
            continue
        vp = vp / np.linalg.norm(vp)
        if exclude is not None and exclude(vp):
            continue
        _, s = vp_support(vp, segs)
        if s > bs:
            best, bs = vp, s
    # уточнение: МНК по поддерживающим отрезкам
    ok, _ = vp_support(best, segs)
    A = np.array([homog_line(s) / np.linalg.norm(homog_line(s)[:2]) for s in segs[ok]])
    _, _, vt = np.linalg.svd(A)
    return vt[-1], segs[ok]


def solve(img, floor, cam_h, vps=None):
    H, W = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    segs = segments(gray)
    c = np.array([W / 2, H / 2])
    # вертикальные (почти отвесные) убираем — нужны горизонтальные направления
    ang = np.degrees(np.arctan2(segs[:, 3] - segs[:, 1], segs[:, 2] - segs[:, 0])) % 180
    hor = segs[(np.abs(ang - 90) > 20)]
    if vps is None:
        random.seed(1)
        v1, s1 = ransac_vp(hor)
        def far_from_v1(vp):  # второе направление — заметно другое
            a = vp[:2] / (np.linalg.norm(vp[:2]) + 1e-12); b = v1[:2] / (np.linalg.norm(v1[:2]) + 1e-12)
            if abs(vp[2]) > 1e-6 and abs(v1[2]) > 1e-6:
                p, q = vp[:2] / vp[2], v1[:2] / v1[2]
                return np.linalg.norm(p - q) < W * 0.5
            return abs(a @ b) > 0.97
        rest = hor[~vp_support(v1, hor)[0]]
        v2, s2 = ransac_vp(rest, exclude=far_from_v1)
    else:
        v1, v2 = [np.array([*v, 1.0]) for v in vps]
        s1 = s2 = None
    # фокус из перпендикулярности двух направлений (обе точки конечны)
    p1 = v1[:2] / v1[2] - c if abs(v1[2]) > 1e-9 else None
    p2 = v2[:2] / v2[2] - c if abs(v2[2]) > 1e-9 else None
    if p1 is not None and p2 is not None and -(p1 @ p2) > 0:
        f = float(np.sqrt(-(p1 @ p2)))
    else:
        f = W * 0.75  # одна точка схода «на бесконечности» — типичный широкий объектив
    K = np.array([[f, 0, c[0]], [0, f, c[1]], [0, 0, 1]])
    Ki = np.linalg.inv(K)
    r1 = Ki @ v1; r1 /= np.linalg.norm(r1)
    r2 = Ki @ v2; r2 -= (r2 @ r1) * r1; r2 /= np.linalg.norm(r2)
    nrm = np.cross(r1, r2)
    if nrm[1] < 0:      # нормаль пола — вверх в кадре (ось y камеры вниз)
        nrm = -nrm
    # начало координат — точка пола в середине контура
    fl = np.array(floor, float)
    o = fl.mean(0)
    ray = Ki @ np.array([*o, 1.0])
    t = ray * (cam_h / abs(nrm @ ray))
    Hm = K @ np.column_stack([r1, r2, t])            # метры пола → пиксели
    Hi = np.linalg.inv(Hm)
    pts = np.array([Hi @ np.array([x, y, 1.0]) for x, y in fl])
    pts = pts[:, :2] / pts[:, 2:3]
    lo, hi = pts.min(0), pts.max(0)
    quad = []
    for a, b in [(lo[0], lo[1]), (hi[0], lo[1]), (hi[0], hi[1]), (lo[0], hi[1])]:
        q = Hm @ np.array([a, b, 1.0]); quad.append([round(float(q[0] / q[2]), 1), round(float(q[1] / q[2]), 1)])
    size = [round(float(hi[0] - lo[0]), 2), round(float(hi[1] - lo[1]), 2)]
    info = dict(f=round(f), v1=(v1[:2] / v1[2]).round(0).tolist() if abs(v1[2]) > 1e-9 else 'inf',
                v2=(v2[:2] / v2[2]).round(0).tolist() if abs(v2[2]) > 1e-9 else "inf")
    return quad, size, Hm, lo, hi, info


def preview(img, d, Hm, lo, hi, path):
    out = img.copy()
    mask = np.zeros(img.shape[:2], np.uint8)
    cv2.fillPoly(mask, [np.int32(d["floor"])], 255)
    for h in d.get("holes", []):
        cv2.fillPoly(mask, [np.int32(h)], 0)
    grid = np.zeros_like(out)
    for k in np.arange(np.floor(lo[0] / .5) * .5, hi[0] + .5, .5):
        a = [Hm @ np.array([k, y, 1.0]) for y in np.linspace(lo[1], hi[1], 60)]
        cv2.polylines(grid, [np.int32([p[:2] / p[2] for p in a])], False, (0, 0, 255), 2)
    for k in np.arange(np.floor(lo[1] / .5) * .5, hi[1] + .5, .5):
        a = [Hm @ np.array([x, k, 1.0]) for x in np.linspace(lo[0], hi[0], 60)]
        cv2.polylines(grid, [np.int32([p[:2] / p[2] for p in a])], False, (0, 0, 255), 2)
    out[(mask > 0) & (grid[:, :, 2] > 0)] = (0, 0, 255)
    cv2.polylines(out, [np.int32(d["floor"])], True, (0, 255, 0), 2)
    for h in d.get("holes", []):
        cv2.polylines(out, [np.int32(h)], True, (255, 0, 255), 2)
    OUT.mkdir(exist_ok=True)
    cv2.imencode(".jpg", cv2.resize(out, (1200, int(out.shape[0] * 1200 / out.shape[1]))))[1].tofile(path)


if __name__ == "__main__":
    pid = sys.argv[1]
    cam_h = float(sys.argv[2]) if len(sys.argv) > 2 else 1.35
    data = json.loads(PH.read_text(encoding="utf-8"))
    d = next(x for x in data if x["id"] == pid)
    img = cv2.imdecode(np.fromfile(ROOT / "data" / "photos" / d["file"], np.uint8), cv2.IMREAD_COLOR)
    quad, size, Hm, lo, hi, info = solve(img, d["floor"], cam_h, d.get("vps"))
    d["quad"], d["size"] = quad, size
    sys.path.insert(0, str(Path(__file__).parent))
    from save_photos_json import dump
    dump(data, PH)
    preview(img, d, Hm, lo, hi, OUT / f"{pid}.jpg")
    print(pid, "size", size, info)
