r"""Новая или обновлённая дверь в ГОТОВЫХ слоях комнаты — без Blender и без перерендера полов.

Запуск:  python tools/blender/door_relayer.py <папка рендера> <имя двери> [образец]
  <папка рендера> — D:/pol-ai/door_test (гостиная день), door_night (гостиная вечер), bed_door (спальня);
  <имя> — фото D:/pol-ai/doors/<имя>.jpg и его ×4 D:/pol-ai/doors/4x/<имя>.png (door_upscale.py);
  [образец] — готовый слой другой двери, с которого берутся место, свет и блики (по умолчанию yurkas-17x).
Пишет <папка>/door_<имя>.png. Потом: door_match.py <папка> <D:/yurkas/data/...> — цвет под комнату,
и добавить дверь в D:/yurkas/data/doors.json. Старый слой сохраняется в <папка>/old/. Папки D:/pol-ai/* — сырые слои (без тёплого вечера), свет берётся только оттуда.
Внимание: вечер гостиной в D:/yurkas дополнительно перекрашен в тёплый — после door_match прогнать слой
через тот же тёплый фильтр (см. журнал AGENTS.md Юркаса) или попросить Claude.
"""
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np

D = Path('D:/pol-ai/doors')
if len(sys.argv) < 3: sys.exit(__doc__)
F = Path(sys.argv[1]); n = sys.argv[2]; tpl = sys.argv[3] if len(sys.argv) > 3 else 'yurkas-17x'
f = F / f'door_{n}.png'
if f.exists():                                   # обновляем свою же дверь: место и свет — из её старого слоя
    bak = F / 'old' / f.name
    if not bak.exists(): bak.parent.mkdir(exist_ok=True); shutil.copy(f, bak)
    src_layer, src_photo = bak, n
else:                                            # новая дверь: место и свет — из слоя образца
    src_layer = F / 'old' / f'door_{tpl}.png'
    if not src_layer.exists(): src_layer = F / f'door_{tpl}.png'
    src_photo = tpl

L = cv2.imread(str(src_layer), -1).astype(np.float32); a = L[..., 3]
c = max(cv2.findContours((a > 128).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0],
        key=cv2.contourArea).reshape(-1, 2).astype(np.float32)
s = c.sum(1); d = c[:, 0] - c[:, 1]
q = np.float32([c[s.argmin()], c[d.argmax()], c[s.argmax()], c[d.argmin()]])   # углы двери: лв, пв, пн, лн
H, W = a.shape


def warp(im):
    h, w = im.shape[:2]
    M = cv2.getPerspectiveTransform(np.float32([[0, 0], [w, 0], [w, h], [0, h]]), q)
    return cv2.warpPerspective(im.astype(np.float32), M, (W, H), flags=cv2.INTER_AREA)


old = warp(cv2.imread(str(D / f'{src_photo}.jpg'))); new = warp(cv2.imread(str(D / '4x' / f'{n}.png')))
lin = lambda x: (np.maximum(x, 0) / 255) ** 2.2
m = (a > 128)[..., None]; k = (61, 61)
bl = lambda x: cv2.blur(x * m, k) / np.maximum(cv2.blur(m.astype(np.float32), k), 1e-3)[..., None]
Ll, ol = lin(L[..., :3]), lin(old)
light = bl(Ll) / np.maximum(bl(ol), 1e-3)       # свет комнаты = старый рендер / старое фото (размыто)
spec = np.maximum(Ll - ol * light, 0)            # блики стекла из старого рендера
out = lin(new) * light + spec
L[..., :3] = np.where(m, np.clip(out ** (1 / 2.2) * 255, 0, 255), L[..., :3])
cv2.imwrite(str(f), L.astype(np.uint8)); print('ok', f)
