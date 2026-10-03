"""Находит на фото декора ряды досок: где проходят продольные стыки и какой у них шаг.

По шагу и ширине доски (из каталога) уточняет масштаб: сколько метров по ширине фото.
Пишет в data/catalog.json у каждого декора:
  tex_rows: [начало первого ряда, шаг ряда] — в долях высоты фото (сверху), или null;
  texture_scale_m — по найденному шагу (если стыки видны).
«Ёлочку» и плитку (pattern: true) досками не раскладываем.

Запуск из папки проекта:  python tools/analyze_textures.py
"""
import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
CAT = ROOT / "data" / "catalog.json"
PATTERN_WORDS = ("мрамор", "камень", "крестинкорт", "уэно", "сланец", "бетон", "терраццо")


def seam_rows(path):
    im = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_GRAYSCALE).astype(np.float32)
    H, W = im.shape
    sy = np.abs(cv2.Sobel(cv2.GaussianBlur(im, (3, 3), 0), cv2.CV_32F, 0, 1))
    frac = (sy > np.percentile(sy, 90)).mean(1)          # шов — сильный край почти через всю ширину
    frac = np.convolve(frac, np.ones(3) / 3, "same")
    pk = [y for y in range(2, H - 2) if frac[y] == frac[max(0, y - 6):y + 7].max() and frac[y] > 0.35]
    groups = []                                           # соседние пики — один шов (фаска даёт 2–3 линии)
    for y in pk:
        if groups and y - groups[-1][-1] <= 5:
            groups[-1].append(y)
        else:
            groups.append([y])
    ys = [float(np.mean(g)) for g in groups]
    if len(ys) < 3:
        return H, W, None
    dif = np.diff(ys)
    per = float(np.median(dif))
    if per < H / 15 or np.mean(np.abs(dif - per) < per * 0.12) < 0.7:   # шаг должен быть ровным
        return H, W, None
    phase = ys[0] % per
    return H, W, (phase / H, per / H)


def main():
    cat = json.loads(CAT.read_text(encoding="utf-8"))
    found = 0
    for d in cat["decors"]:
        if not d.get("texture"):
            continue
        d["pattern"] = any(w in d["name"].lower() for w in PATTERN_WORDS)
        H, W, rows = seam_rows(ROOT / "data" / d["texture"])
        if d["pattern"] or not rows:
            d["tex_rows"] = None
            continue
        d["tex_rows"] = [round(rows[0], 4), round(rows[1], 4)]
        if d.get("board_w_mm"):
            d["texture_scale_m"] = round(W * d["board_w_mm"] / 1000 / (rows[1] * H), 3)
        found += 1
    CAT.write_text(json.dumps(cat, ensure_ascii=False, indent=1), encoding="utf-8")
    print("Стыки найдены у", found, "декоров из", len(cat["decors"]))


if __name__ == "__main__":
    main()
