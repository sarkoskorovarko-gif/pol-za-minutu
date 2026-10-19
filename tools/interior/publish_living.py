"""Готовые картинки гостиной → сайт: data/living/<декор>.jpg (1600 px) + index.json (список декоров).

Запуск: python tools/interior/publish_living.py [папка прогона]   (по умолчанию D:/pol-ai/full_living13)
Берёт только декоры из каталога, у которых есть final_<id>.jpg.
"""
import json, sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
src = Path(sys.argv[1] if len(sys.argv) > 1 else 'D:/pol-ai/full_living13')
dst = ROOT / 'data' / 'living'; dst.mkdir(exist_ok=True)
ids = [d['id'] for d in json.load(open(ROOT / 'data' / 'catalog.json', encoding='utf-8'))['decors']]
done = []
for d in ids:
    p = src / f'final_{d}.jpg'
    if not p.exists(): continue
    im = cv2.imdecode(np.fromfile(str(p), np.uint8), 1)
    im = cv2.resize(im, (1600, round(im.shape[0] * 1600 / im.shape[1])), interpolation=cv2.INTER_AREA)
    cv2.imencode('.jpg', im, [cv2.IMWRITE_JPEG_QUALITY, 82, cv2.IMWRITE_JPEG_PROGRESSIVE, 1])[1].tofile(str(dst / f'{d}.jpg'))
    done.append(d)
(dst / 'index.json').write_text(json.dumps(done), encoding='utf-8')
print(f'на сайте {len(done)} из {len(ids)} декоров; нет картинки: {", ".join(x for x in ids if x not in done) or "—"}')
