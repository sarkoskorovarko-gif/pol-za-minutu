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
    out = np.where(zone > 0, m, base)
    # "keep" — места, где пол точно не рисуем: ковёр или деревянная ножка цвета пола.
    # В обучение GrabCut их не даём (собьют его), применяем в самом конце.
    for k in d.get("keep", []):
        cv2.fillPoly(out, [np.int32(np.round(k))], 0)
    out = cv2.GaussianBlur(out, (3, 3), 0)
    # 1024 по длинной стороне — как маска на сайте
    t = 1024 / max(W, H)
    out = cv2.resize(out, (round(W * t), round(H * t)), interpolation=cv2.INTER_AREA)
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
