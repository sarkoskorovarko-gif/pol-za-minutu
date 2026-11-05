"""Автопроверка 3D-двери против фото каталога.

Запуск: python tools/blender/door_check.py <имя двери> [--photo]  (--photo: дверь из фото 4x)
  берёт tools/blender/doors/<имя>.json и D:/pol-ai/doors/<имя>.jpg, рендерит door_model.py с прозрачным фоном,
  обрезает обе двери по рамке, приводит к одному размеру и сравнивает:
  - полосы (стекло, филёнки): профиль яркости по центру полотна, сдвиг ≤ 1,5 % высоты;
  - цвет полотна и стекла: разница ΔE (Lab) ≤ 8;
  - ручка: место тёмного пятна на левом бруске, ≤ 2 % высоты.
Пишет ВЕРНО/НЕВЕРНО по каждому пункту и картинку <scratch>/check_<имя>.jpg (фото | 3D | разница).
"""
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
BL = r'D:\pol-ai\blender\blender.exe'
name = sys.argv[1]
spec = ROOT / 'tools/blender/doors' / f'{name}.json'
photo = Path('D:/pol-ai/doors') / f'{name}.jpg'
out = Path('D:/pol-ai/doors/check'); out.mkdir(parents=True, exist_ok=True)
png = out / f'render_{name}.png'
png.unlink(missing_ok=True)
_r = subprocess.run([BL, '-b', '-P', str(ROOT / 'tools/blender/door_model.py'), '--', f'spec={spec}', f'out={png}', 'alpha=1', *([f'photo={Path("D:/pol-ai/doors/4x") / (name + ".png")}'] if '--photo' in sys.argv else [])],
               capture_output=True, check=True, text=True, encoding='utf-8', errors='replace')
if not png.exists() or 'Traceback' in _r.stdout + _r.stderr: sys.exit('Blender упал: ' + (_r.stdout + _r.stderr)[-1500:])
s = json.loads(spec.read_text(encoding='utf-8'))

ph = cv2.imread(str(photo)); g = cv2.cvtColor(ph, cv2.COLOR_BGR2GRAY)
ys, xs = np.where(g < 235); ph = ph[ys.min():ys.max() + 1, xs.min():xs.max() + 1]; asp_p = ph.shape[1] / ph.shape[0]
rd = cv2.imread(str(png), cv2.IMREAD_UNCHANGED)
ys, xs = np.where(rd[..., 3] > 128); rd = rd[ys.min():ys.max() + 1, xs.min():xs.max() + 1, :3]; asp_r = rd.shape[1] / rd.shape[0]
H, W = 900, int(900 * ph.shape[1] / ph.shape[0])
ph, rd = cv2.resize(ph, (W, H), interpolation=cv2.INTER_AREA), cv2.resize(rd, (W, H), interpolation=cv2.INTER_AREA)
k = H / s['h']; X = lambda px: int(px * W / s['w'])

ok_all = True
def report(what, ok, detail):
    global ok_all; ok_all &= ok
    print(('ВЕРНО   ' if ok else 'НЕВЕРНО ') + what + ': ' + detail)

# 0. пропорции: ширина/высота двери с наличником (до приведения к одному размеру)
report('пропорции', abs(asp_r / asp_p - 1) <= 0.02, f'фото {asp_p:.3f}, 3D {asp_r:.3f}')

# 1. линии по ВСЕЙ двери: горизонтальные (по рядам) и вертикальные (по столбцам) — должны совпасть до 1,5 %
c0, c1 = X(s['casing'] + s['stile'] + 8), X(s['w'] - s['casing'] - s['stile'] - 8)
def lines(im, axis):
    g = cv2.GaussianBlur(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY).astype(np.float32), (5, 5), 0)
    if axis == 'y': p = np.abs(np.diff(g, axis=0))[:, X(s['casing']) + 4:X(s['w'] - s['casing']) - 4].mean(1)
    else: p = np.abs(np.diff(g, axis=1))[int(H * 0.15):int(H * 0.85)].mean(0)
    t = max(2.5, 0.2 * p[15:-15].max())
    return [i for i in range(15, len(p) - 15) if p[i] >= t and p[i] == p[i - 4:i + 5].max()]
for ax, n, L in (('y', 'горизонтальные линии', H), ('x', 'вертикальные линии', W)):
    ea, eb = lines(ph, ax), lines(rd, ax); tol = max(4, 0.015 * L)
    miss = [y for y in ea if not any(abs(y - z) <= tol for z in eb)]
    extra = [y for y in eb if not any(abs(y - z) <= tol for z in ea)]
    report(n, not miss and not extra, f'на фото {len(ea)}, в 3D {len(eb)}; нет в 3D: {miss}; лишние в 3D: {extra}')

# 2. цвет полотна (верхняя филёнка) и стекла (самая широкая полоса), ΔE в Lab
lab = lambda im: cv2.cvtColor(im, cv2.COLOR_BGR2LAB).astype(np.float32)
def de(y0, y1):
    pa = np.median(lab(ph)[y0:y1, c0:c1].reshape(-1, 3), 0); pb = np.median(lab(rd)[y0:y1, c0:c1].reshape(-1, 3), 0)
    pa[0] *= 100 / 255; pb[0] *= 100 / 255
    global last; last = pb - pa
    return float(np.linalg.norm(pa - pb))
ly0 = int((s['rail_top'] + 10) * k); ly1 = int(((s['glass'][0][0] if s.get('glass') else s['h'] / 2) - 10) * k)
if ly1 - ly0 < 20:   # стекло во всю высоту — полотно меряем на нижней перемычке
    ly0, ly1 = int((s['h'] - s['rail_bot'] - 25) * k), int((s['h'] - s['rail_bot'] - 5) * k)
d = de(ly0, ly1); report('цвет полотна', d <= 8, f'ΔE {d:.1f} (3D: светлота {last[0]:+.0f}, a {last[1]:+.0f}, b {last[2]:+.0f})')
if s.get('glass'):
    gl = max(s['glass'], key=lambda g: g[1] - g[0]); gy0, gy1 = int(gl[0] * k) + 4, int(gl[1] * k) - 4
    if s.get('mirror'): print('—       цвет стекла: зеркало, отражает комнату — не сравниваем')
    elif gy1 > gy0: d = de(gy0, gy1); report('цвет стекла', d <= 12, f'ΔE {d:.1f}')

# 3. ручка: самое тёмное пятно на левом бруске
def handle(im):
    zone = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)[int(H * 0.3):int(H * 0.7), X(s['casing'] + 3):X(s['casing'] + s['stile'] - 3)]
    return int(H * 0.3) + int(np.argmin(cv2.blur(zone, (9, 9)).mean(1)))
hy, hr = handle(ph), handle(rd)
report('ручка', abs(hy - hr) <= 0.02 * H, f'на фото {hy}, в 3D {hr} (из {H})')

diff = cv2.applyColorMap(cv2.convertScaleAbs(cv2.absdiff(ph, rd).max(2), alpha=3), cv2.COLORMAP_JET)
cv2.imwrite(str(out / f'check_{name}.jpg'), np.hstack([ph, rd, diff]))
print('ИТОГ:', 'дверь соответствует фото' if ok_all else 'есть расхождения', '→', out / f'check_{name}.jpg')
