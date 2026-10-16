r"""Цветокоррекция «как у фотографа интерьеров»: экспозиция и баланс белого по замеру, а не наугад.

Запуск:  python tools/interior/grade.py <картинка> [выход] [--target 118] [--warm 1.08]
Замер прогона 5: средняя яркость 70 (у интерьерных фото 110–130), R/B = 1,52 (сильно жёлтый),
стены 71/56/44 (коричневые вместо светло-бежевых). Делаем:
1) баланс белого: светлые нейтральные места (стены/потолок — верхняя половина кадра, яркие, малонасыщенные)
   доводим до лёгкого тёплого R/B ≈ warm;
2) экспозиция: медиана яркости → target (мягкой кривой, без пересвета светлых мест).
Пол меняется вместе со всем кадром — так же, как на настоящем фото.
"""
import sys
from pathlib import Path

import cv2
import numpy as np


def rd(p):
    return cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)


def grade(img, target=118, warm=1.08):
    f = img.astype(np.float32) / 255
    lin = f ** 2.2
    h = f.shape[0]
    top = lin[: h // 2]
    lum = top.mean(2); sat = top.max(2) - top.min(2)
    sel = (lum > np.percentile(lum, 50)) & (sat < np.percentile(sat, 50)) & (lum < 0.95)
    b, g, r = [top[..., i][sel].mean() for i in range(3)]
    # баланс: зелёный — опора; красный/синий — так, чтобы R/B = warm, R/G ≈ (warm ** 0.5)
    kr, kb = (g * warm ** 0.5) / r, (g / warm ** 0.5) / b
    lin = lin * np.array([kb, 1.0, kr], np.float32)
    # экспозиция: медиана → target (в гамме), мягкое «плечо» для светлых
    f = np.clip(lin, 0, None) ** (1 / 2.2)
    med = np.median(f.mean(2)) * 255
    k = target / max(med, 1)
    x = f * k
    x = np.where(x > 0.8, 0.8 + (1 - np.exp(-(x - 0.8) / 0.2)) * 0.2, x)   # плечо: светлое не выбивается в белое
    out = (np.clip(x, 0, 1) * 255).astype(np.uint8)
    return out, {'R/B до': round(r / b, 2), 'медиана до': round(float(med)), 'k экспозиции': round(float(k), 2)}


if __name__ == '__main__':
    args, opt, it = [], {}, iter(sys.argv[1:])
    for a in it:
        if a.startswith('--'): opt[a] = next(it, None)          # --target 118 → значение не попадает в имена файлов
        else: args.append(a)
    target = float(opt.get('--target') or 118); warm = float(opt.get('--warm') or 1.08)
    src = Path(args[0]); dst = Path(args[1]) if len(args) > 1 else src.with_name(src.stem + '_graded.jpg')
    out, info = grade(rd(src), target, warm)
    cv2.imencode('.jpg', out, [cv2.IMWRITE_JPEG_QUALITY, 93])[1].tofile(str(dst))
    g = out.astype(np.float32)
    print(info, '→ медиана', round(float(np.median(g.mean(2)))), 'R/B', round(float(g[..., 2].mean() / g[..., 0].mean()), 2), dst)
