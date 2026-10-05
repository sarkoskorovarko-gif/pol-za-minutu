"""Маска пола нейросетью (SegFormer-B2, обучена на интерьерах ADE20K, класс «пол»).

Нейросеть и её окружение лежат вне проекта: D:\\pol-ai (venv + models).
Запуск (именно этим Python):
    D:\\pol-ai\\venv\\Scripts\\python tools/ai_floor.py [id ...]

Что делает:
 1. Считает для каждого пикселя вероятность «пол» (фото в двух масштабах, среднее).
 2. Ограничивает её разметкой: внутри контура floor (с запасом 30 px), без "keep".
 3. Уточняет край по самому фото (направленный фильтр) — граница ложится на край предмета.
 4. Обрезает точную маску (data/photos/masks/<id>.png из tools/refine_masks.py)
    там, где нейросеть уверена, что это не пол. Запускать ПОСЛЕ refine_masks.py.
"""
import json, sys
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

ROOT = Path(__file__).resolve().parent.parent
MODEL = Path(r"D:\pol-ai\models\segformer-b2-ade.onnx")
FLOOR, RUG = 3, 28
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)

sess = ort.InferenceSession(str(MODEL), providers=["CPUExecutionProvider"])


def probs(img, long_side):
    H, W = img.shape[:2]
    s = long_side / max(H, W)
    w, h = int(round(W * s / 32) * 32), int(round(H * s / 32) * 32)
    x = cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2RGB), (w, h), interpolation=cv2.INTER_AREA)
    x = ((x.astype(np.float32) / 255 - MEAN) / STD).transpose(2, 0, 1)[None]
    lg = sess.run(None, {"pixel_values": x})[0][0].astype(np.float32)   # (150, h/4, w/4)
    lg = lg - lg.max(0, keepdims=True)
    e = np.exp(lg)
    p = e[FLOOR] / e.sum(0)
    return cv2.resize(p, (W, H), interpolation=cv2.INTER_LINEAR)


def guided(I, p, r=8, eps=1e-3):
    """Направленный фильтр (He et al.): сглаживает p, сохраняя края изображения I."""
    I = I.astype(np.float32) / 255
    mI = cv2.boxFilter(I, -1, (r, r)); mp = cv2.boxFilter(p, -1, (r, r))
    cIp = cv2.boxFilter(I * p, -1, (r, r)) - mI * mp
    vI = cv2.boxFilter(I * I, -1, (r, r)) - mI * mI
    a = cIp / (vI + eps); b = mp - a * mI
    return cv2.boxFilter(a, -1, (r, r)) * I + cv2.boxFilter(b, -1, (r, r))


def make(d):
    img = cv2.imdecode(np.fromfile(ROOT / "data" / "photos" / d["file"], np.uint8), cv2.IMREAD_COLOR)
    H, W = img.shape[:2]
    p = (probs(img, 1024) + probs(img, 768)) / 2
    # область, где вообще может быть пол — контур разметки с запасом
    zone = np.zeros((H, W), np.uint8)
    cv2.fillPoly(zone, [np.int32(np.round(d["floor"]))], 255)
    zone = cv2.dilate(zone, np.ones((61, 61), np.uint8)) > 0
    p = np.where(zone, p, 0).astype(np.float32)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    p = np.clip(guided(gray, p, 6, 1e-3), 0, 1)
    m = (p > 0.5).astype(np.uint8)
    # убрать мелкий мусор: островки и дырочки меньше ~0,05 % кадра
    n, lbl, st, _ = cv2.connectedComponentsWithStats(m)
    for i in range(1, n):
        if st[i, 4] < H * W * 0.0005:
            m[lbl == i] = 0
    n, lbl, st, _ = cv2.connectedComponentsWithStats(1 - m)
    for i in range(1, n):
        if st[i, 4] < H * W * 0.0002:
            m[lbl == i] = 1
    for k in d.get("keep", []):                  # точно не пол — по ручной разметке
        cv2.fillPoly(m, [np.int32(np.round(k))], 0)
    # Итог: точная маска по краям фото (tools/refine_masks.py) обрезается там, где
    # нейросеть уверена, что это не пол (плинтус, мебель цвета пола). Край нейросети
    # грубее (±5 px), поэтому ей даём запас, а точную границу оставляем свою.
    raw = Path(r"D:/pol-ai/ai_masks"); raw.mkdir(exist_ok=True)   # «сырая» маска нейросети — для snap_floor.py
    cv2.imencode(".png", m * 255)[1].tofile(raw / f"{d['id']}.png")
    path = ROOT / "data" / "photos" / "masks" / f"{d['id']}.png"
    own = cv2.imdecode(np.fromfile(path, np.uint8), 0)
    own = cv2.resize(own, (W, H), interpolation=cv2.INTER_LINEAR) > 127
    ai = cv2.dilate(m, np.ones((11, 11), np.uint8)) > 0
    if d.get("ai_trim", True) is False:          # блики/плитка сбивают нейросеть — не режем
        ai = np.ones_like(ai)
    cut = own & ~ai
    final = (own & ai).astype(np.float32)
    out = cv2.GaussianBlur(final * 255, (3, 3), 0)
    t = 1024 / max(W, H)
    out = cv2.resize(out, (round(W * t), round(H * t)), interpolation=cv2.INTER_AREA).astype(np.uint8)
    cv2.imencode(".png", out)[1].tofile(path)
    return round(final.mean() * 100, 1), round(cut.mean() * 100, 2)


if __name__ == "__main__":
    data = json.loads((ROOT / "data" / "photos.json").read_text(encoding="utf-8"))
    ids = sys.argv[1:]
    for d in data:
        if not ids or d["id"] in ids:
            f, c = make(d)
            print(d["id"], d["title"], "— пол", f, "% кадра, нейросеть отрезала", c, "%", flush=True)
