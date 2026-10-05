"""Автопроверка фото-комнат: цифры качества + картинка с худшими местами.

Для каждой комнаты из data/photos.json (маска — data/photos/masks/<id>.png):
 1. edge   — % границы пола, лежащей на настоящем крае фото (±3 px). Хорошо: > 80 %.
 2. leak   — % площади рядом с границей (снаружи), похожей по цвету на старый пол
             — значит, старый пол не заменён. Хорошо: < 1 %.
 3. over   — % площади пола, совсем непохожей на старый пол (мебель под ламинатом). Хорошо: < 1 %.
 4. persp  — средняя ошибка направления линий старых досок относительно нашей
             перспективы, в градусах. Хорошо: < 3°.
 5. size   — ширина×глубина размеченного прямоугольника, м (правдоподобно 2–12).
Худшие места обводятся на картинке tools/check/qa_<id>.jpg (красное — утечка
старого пола, синее — пол на мебели, жёлтое — граница мимо края).

Запуск:  python tools/qa_photos.py [id ...]
"""
import json, sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "check"


def homography(src, dst):
    return cv2.getPerspectiveTransform(np.float32(src), np.float32(dst))


def load(d):
    img = cv2.imdecode(np.fromfile(ROOT / "data" / "photos" / d["file"], np.uint8), cv2.IMREAD_COLOR)
    H, W = img.shape[:2]
    m = cv2.imdecode(np.fromfile(ROOT / "data" / "photos" / "masks" / f"{d['id']}.png", np.uint8), 0)
    m = cv2.resize(m, (W, H), interpolation=cv2.INTER_LINEAR) > 127
    return img, m


def floor_model(lab, m):
    """Цвет старого пола: среднее и разброс по надёжной середине маски."""
    core = cv2.erode(m.astype(np.uint8), np.ones((25, 25), np.uint8)) > 0
    px = lab[core].astype(np.float32)
    lo, hi = np.percentile(px[:, 0], [10, 90])            # блики и глубокие тени не в счёт
    px = px[(px[:, 0] >= lo) & (px[:, 0] <= hi)]
    mu = px.mean(0)
    cov = np.cov(px.T) + np.eye(3) * 4
    return mu, np.linalg.inv(cov)


def mdist(lab, mu, icov):
    d = lab.reshape(-1, 3).astype(np.float32) - mu
    return np.sqrt(np.einsum("ij,jk,ik->i", d, icov, d)).reshape(lab.shape[:2])


def check(d):
    img, m = load(d)
    H, W = img.shape[:2]
    lab = cv2.cvtColor(cv2.GaussianBlur(img, (5, 5), 0), cv2.COLOR_BGR2LAB)
    mu, icov = floor_model(lab, m)
    dist = mdist(lab, mu, icov)
    mu8 = m.astype(np.uint8)
    # фактура: сила мелкого рисунка (древесина, стыки) — у стены и потолка её почти нет
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    hp = np.abs(g - cv2.GaussianBlur(g, (0, 0), 2))
    tex = cv2.blur(hp, (15, 15))
    core = cv2.erode(mu8, np.ones((25, 25), np.uint8)) > 0
    t0 = np.median(tex[core])
    tex_like = (tex > t0 * 0.5) & (tex < t0 * 2.5)

    # 1. граница пола — на настоящем крае фото? (края кадра не считаем)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 30, 90)
    near_edge = cv2.dilate(edges, np.ones((7, 7), np.uint8)) > 0
    bnd = (cv2.morphologyEx(mu8, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0)
    bnd[:4, :] = bnd[-4:, :] = False; bnd[:, :4] = bnd[:, -4:] = False
    edge_ok = near_edge[bnd].mean() * 100 if bnd.any() else 100
    bad_edge = bnd & ~near_edge
    # согласие с нейросетью (если её маска есть): граница не дальше 6 px от её границы
    ai_ok = None
    ap = Path(r"D:/pol-ai/ai_masks") / f"{d['id']}.png"
    if ap.exists() and bnd.any():
        am = cv2.resize(cv2.imdecode(np.fromfile(ap, np.uint8), 0), (W, H)) > 127
        ae = cv2.morphologyEx(am.astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8))
        near_ai = cv2.dilate(ae, np.ones((13, 13), np.uint8)) > 0
        ai_ok = near_ai[bnd].mean() * 100
        bad_edge = bad_edge & ~near_ai     # на картинке — только места, где не согласны оба

    # 2. утечка старого пола: снаружи маски, рядом (до 40 px), цвет как у пола
    ring = (cv2.dilate(mu8, np.ones((81, 81), np.uint8)) > 0) & ~m
    leak = ring & (dist < 2.0) & tex_like
    leak = cv2.morphologyEx(leak.astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    # тонкие полосы вдоль стены — это плинтус, а не пол: оставляем только «толстые» пятна
    n, lbl, st, _ = cv2.connectedComponentsWithStats(leak)
    thick = cv2.distanceTransform(leak, cv2.DIST_L2, 5)
    keep = np.zeros(n, bool)
    for i in range(1, n):
        keep[i] = thick[lbl == i].max() >= 9
    leak = keep[lbl]
    # 3. пол на мебели: внутри маски, цвет совсем не как у пола
    over = m & (dist > 6.0) & ~tex_like
    over = cv2.morphologyEx(over.astype(np.uint8), cv2.MORPH_OPEN, np.ones((7, 7), np.uint8)) > 0

    # 4. перспектива: линии на старом полу против направлений нашей сетки
    Wq, Dq = d["size"]
    Hm = homography([[0, 0], [Wq, 0], [Wq, Dq], [0, Dq]], d["quad"])     # метры → пиксели
    Hi = np.linalg.inv(Hm)
    segs = cv2.createLineSegmentDetector().detect(gray)[0].reshape(-1, 4)
    errs = []
    inner = cv2.erode(mu8, np.ones((15, 15), np.uint8)) > 0
    for x1, y1, x2, y2 in segs:
        if np.hypot(x2 - x1, y2 - y1) < 40:
            continue
        cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
        if not (0 <= cx < W and 0 <= cy < H and inner[cy, cx]):
            continue
        p = Hi @ np.array([cx, cy, 1.0]); p = p[:2] / p[2]
        best = 90.0
        for dv in ([0.3, 0], [0, 0.3]):                 # два направления сетки в этой точке
            q = Hm @ np.array([p[0] + dv[0], p[1] + dv[1], 1.0]); q = q[:2] / q[2]
            a = np.degrees(np.arctan2(q[1] - cy, q[0] - cx))
            b = np.degrees(np.arctan2(y2 - y1, x2 - x1))
            e = abs((a - b + 90) % 180 - 90)
            best = min(best, e)
        errs.append(best)
    # линии не по доскам (солнечные полосы, тени) дают большую ошибку — их не считаем
    inl = [e for e in errs if e < 15]
    persp = float(np.median(inl)) if len(inl) >= 5 else None

    res = dict(edge=round(edge_ok, 1), ai=None if ai_ok is None else round(ai_ok, 1), leak=round(leak.mean() * 100, 2), over=round(over.mean() * 100, 2),
               persp=None if persp is None else round(persp, 1), lines=len(errs), size=[Wq, Dq],
               floor=round(m.mean() * 100))

    # картинка: худшие места
    vis = img.copy()
    vis[m] = (vis[m] * 0.75 + np.array([0, 90, 0]) * 0.25).astype(np.uint8)
    vis[leak] = (0, 0, 255)
    vis[over] = (255, 80, 0)
    vis[cv2.dilate(bad_edge.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0] = (0, 230, 255)
    for mask, col in ((leak, (0, 0, 255)), (over, (255, 80, 0))):
        n, lbl, st, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8))
        for i in np.argsort(-st[1:, 4])[:5] + 1:
            if st[i, 4] < 150:
                continue
            x, y, w, h = st[i, :4]
            cv2.rectangle(vis, (x - 6, y - 6), (x + w + 6, y + h + 6), col, 3)
    txt = f"{d['id']} edge {res['edge']}%  leak {res['leak']}%  over {res['over']}%  persp {res['persp']}deg"
    cv2.putText(vis, txt, (12, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 0, 0), 5)
    cv2.putText(vis, txt, (12, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 255, 255), 2)
    OUT.mkdir(exist_ok=True)
    cv2.imencode(".jpg", cv2.resize(vis, (1200, int(H * 1200 / W))))[1].tofile(OUT / f"qa_{d['id']}.jpg")
    return res


def verdict(r):
    bad = []
    if r["edge"] < 80 and (r["ai"] is None or r["ai"] < 85): bad.append("края")
    if r["leak"] > 1: bad.append("старый пол виден")
    if r["over"] > 1: bad.append("пол на мебели")
    if r["persp"] is not None and r["persp"] > 3: bad.append("перспектива")
    if not all(1.5 < v < 25 for v in r["size"]): bad.append("размер")
    return "OK" if not bad else "ПЛОХО: " + ", ".join(bad)


if __name__ == "__main__":
    data = json.loads((ROOT / "data" / "photos.json").read_text(encoding="utf-8"))
    ids = sys.argv[1:]
    for d in data:
        if ids and d["id"] not in ids:
            continue
        r = check(d)
        print(f"{d['id']:4} {d['title'][:26]:26} пол {r['floor']:3}%  края {r['edge']:5}%  "
              f"нейросеть {r['ai']}%  утечка {r['leak']:5}%  на мебели {r['over']:5}%  персп. {r['persp']}° ({r['lines']} линий)  "
              f"{r['size'][0]}×{r['size'][1]} м  → {verdict(r)}")
