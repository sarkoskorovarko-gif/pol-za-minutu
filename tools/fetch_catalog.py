"""Превращает raw/egger_raw.json (собран в браузере скриптом collect_in_browser.js)
в data/catalog.json и скачивает текстуры в data/textures/.

Запуск из папки проекта:  python tools/fetch_catalog.py
Параметр --textures N — сколько текстур скачать (по умолчанию 15, 0 = все).
"""
import argparse, io, json, math, re, sys, time
from datetime import date
from pathlib import Path

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw" / "egger_raw.json"
DATA = ROOT / "data"
TEX = DATA / "textures"
PAUSE = 1.5  # пауза между скачиваниями, сек

# Цвет Материка → группа для фильтра. Проверяем по порядку, первое совпадение.
COLOR_GROUPS = [
    ("сер", "серый"), ("бел", "светлый"), ("светл", "светлый"), ("молоч", "светлый"),
    ("бежев", "бежевый"), ("песоч", "бежевый"), ("натур", "бежевый"),
    ("тёмн", "тёмный"), ("темн", "тёмный"), ("венге", "тёмный"), ("черн", "тёмный"),
    ("коричн", "коричневый"), ("орех", "коричневый"), ("рыж", "коричневый"), ("медов", "коричневый"),
]


def num(s):
    """'1.99' или '1,99' → 1.99; пусто → None."""
    m = re.search(r"\d+(?:[.,]\d+)?", s or "")
    return float(m.group().replace(",", ".")) if m else None


def color_group(color):
    c = (color or "").lower()
    for key, group in COLOR_GROUPS:
        if key in c:
            return group
    return "другой"


def srgb_to_lab(r, g, b):
    """Средний цвет (0–255) → L (светлота 0–100) и b (жёлтый + / синий −)."""
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = lin(r), lin(g), lin(b)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    f = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    return 116 * f(y) - 16, 200 * (f(y) - f(z))


def process_image(content, out_path):
    """Сжимает до 800 px, сохраняет jpg 80%. Возвращает (lightness, warmth, texture_ok)."""
    img = Image.open(io.BytesIO(content)).convert("RGB")
    w, h = img.size
    # Средний цвет без краёв (по 10% с каждой стороны)
    core = img.crop((w // 10, h // 10, w - w // 10, h - h // 10)).resize((1, 1), Image.Resampling.BOX)
    L, b = srgb_to_lab(*core.getpixel((0, 0)))
    # Похоже на упаковку, а не пол: странные пропорции или светлые поля по краям
    ratio = w / h
    border = img.crop((0, 0, w, max(1, h // 30))).resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))
    ok = 1.3 <= ratio <= 2.0 and not all(c > 245 for c in border)
    img.thumbnail((800, 800))
    img.save(out_path, "JPEG", quality=80)
    return round(L, 1), round(b, 1), ok


def make_decor(it):
    p = it["props"]
    # Код декора из названия: EPL038, EHL098, EPC020 ...
    m = re.search(r"\b(E[A-Z]{2}\d{3})\b", it.get("name") or "")
    if not m:
        return None
    cls = num(p.get("Класс износостойкости"))
    water = p.get("Влагостойкость", "").strip().lower()
    return {
        "id": m.group(1),
        "name": p.get("Наименование цвета производителя") or it["name"],
        "collection": p.get("Коллекция", ""),
        "price_m2": it.get("price"),
        "pack_m2": num(p.get("Количество квадратных метров в упаковке")),
        "pack_pcs": int(num(p.get("Количество штук в упаковке")) or 0) or None,
        "board_len_mm": num(p.get("Длина доски, мм")),
        "board_w_mm": num(p.get("Ширина доски, мм")),
        "class": int(cls) if cls else None,
        "thickness_mm": num(p.get("Толщина доски, мм")),
        "chamfer": bool(p.get("Фаска")) and "без" not in p.get("Фаска", "").lower(),
        "water_resistant": bool(water) and water not in ("нет", "-"),
        "color": p.get("Цвет", ""),
        "color_group": color_group(p.get("Цвет")),
        "in_stock": (it.get("availability") or "").endswith("InStock"),
        "texture": None, "texture_ok": None, "lightness": None, "warmth": None,
        "texture_scale_m": None,
        "image_src": it.get("image"),
        "url": it["url"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--textures", type=int, default=15)
    args = ap.parse_args()

    if not RAW.exists():
        sys.exit(f"Нет файла {RAW}. Сначала соберите данные в браузере (collect_in_browser.js).")
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    items = raw.get("items") or []
    if not items:
        sys.exit("В raw-файле нет товаров — возможно, сайт изменился. Проверьте сборщик.")

    decors, seen, problems = [], set(), []
    for it in items:
        d = make_decor(it)
        if not d:
            problems.append(f"нет кода декора: {it.get('name')}")
            continue
        if d["id"] in seen:  # тот же декор в другой толщине/классе — оставляем первый
            continue
        seen.add(d["id"])
        for k in ("price_m2", "pack_m2", "board_len_mm", "board_w_mm"):
            if not d[k]:
                problems.append(f"{d['id']}: не найдено поле {k}")
        decors.append(d)
    if not decors:
        sys.exit("Не удалось разобрать ни одного декора — структура сайта изменилась.")

    # Старый каталог: сохраняем уже скачанные текстуры и ручные правки масштаба
    old = {}
    old_path = DATA / "catalog.json"
    if old_path.exists():
        old = {d["id"]: d for d in json.loads(old_path.read_text(encoding="utf-8"))["decors"]}

    TEX.mkdir(parents=True, exist_ok=True)
    limit = args.textures or len(decors)
    done = 0
    for d in decors:
        o = old.get(d["id"], {})
        d["texture_scale_m"] = o.get("texture_scale_m")
        path = TEX / f"{d['id']}.jpg"
        if path.exists() and o.get("lightness") is not None:
            d.update({k: o[k] for k in ("texture", "texture_ok", "lightness", "warmth")})
            continue
        if done >= limit or not d["image_src"]:
            continue
        print(f"Текстура {d['id']} …", flush=True)
        try:
            r = requests.get(d["image_src"], headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            r.raise_for_status()
            L, w, ok = process_image(r.content, path)
            d.update(texture=f"textures/{d['id']}.jpg", texture_ok=ok, lightness=L, warmth=w)
            done += 1
        except Exception as e:
            problems.append(f"{d['id']}: картинка не скачалась ({e})")
        time.sleep(PAUSE)

    catalog = {"updated": date.today().isoformat(), "decors": decors,
               "underlay": [], "skirting": []}
    old_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")

    with_tex = sum(1 for d in decors if d["texture"])
    print(f"\nГотово: декоров {len(decors)}, с текстурой {with_tex}. Файл: {old_path}")
    if problems:
        print("\nПроблемы (проверьте вручную):")
        for p in problems:
            print(" -", p)


if __name__ == "__main__":
    main()
