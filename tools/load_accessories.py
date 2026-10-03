"""Подложка и плинтус из data/accessories_diy.json → в data/catalog.json.

Запуск из папки проекта:  python tools/load_accessories.py
Цены в accessories_diy.json правятся вручную (или после нового сбора с diy.by).
"""
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"


def load_accessories():
    a = json.loads((DATA / "accessories_diy.json").read_text(encoding="utf-8"))
    underlay = [{"id": i, "name": n, "price": round(pm2 * m2, 2), "pack_m2": m2, "price_m2": pm2}
                for i, n, pm2, m2 in a["underlay"]]
    skirting = [{"id": i, "name": n, "price": p, "length_m": ln, "height_mm": h, "color": c,
                 "needs_accessories": bool(cp and kp), "corner_price": cp, "cap_price": kp}
                for i, n, p, ln, h, c, cp, kp in a["skirting"]]
    return {"underlay": underlay, "skirting": skirting}


if __name__ == "__main__":
    path = DATA / "catalog.json"
    cat = json.loads(path.read_text(encoding="utf-8"))
    cat.update(load_accessories())
    path.write_text(json.dumps(cat, ensure_ascii=False, indent=1), encoding="utf-8")
    print("Подложек:", len(cat["underlay"]), "плинтусов:", len(cat["skirting"]))
