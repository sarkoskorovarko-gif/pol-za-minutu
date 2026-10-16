r"""Полный прогон комнаты — с проверкой ПЕРЕД запуском (правило пользователя: проверить, поучиться, исправить, потом запускать).

Запуск:  python tools/interior/run_full.py <layout.json> <папка> [декор ...] [--check] [--denoise 0.5]
  --check — только проверка, без рендера.
Шаги: проверка (код, план без нарушений, файлы моделей, видеокарта) → Blender (Cycles) → нейросеть →
пол по декорам → склейка → цветокоррекция (grade.py). Итог: <папка>/final_<декор>.jpg
"""
import json, py_compile, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BL = r'D:\pol-ai\blender\blender.exe'
FLOORS = Path(r'D:\pol-ai\bk_full\floors')
sys.path.insert(0, str(ROOT / 'tools' / 'interior'))


def precheck(layout, decors):
    problems = []
    for f in ['tools/interior/build.py', 'tools/interior/assets.py', 'tools/interior/plan.py', 'tools/interior/grade.py',
              'tools/blender/ai_realism.py', 'tools/blender/floor_render.py', 'tools/blender/floor_composite.py']:
        try: py_compile.compile(str(ROOT / f), doraise=True)
        except py_compile.PyCompileError as e: problems.append(f'код: {f}: {e.msg[:120]}')
    import re                                               # урок (дважды!): команда «утонула» в комментарии после «a; # … ; b = …»
    for f in (ROOT / 'tools').rglob('*.py'):
        for n, line in enumerate(f.read_text(encoding='utf-8').splitlines(), 1):
            if '#' in line and re.search(r'#.*;\s*\w+(\.\w+)+\s*=', line):
                problems.append(f'код в комментарии: {f.relative_to(ROOT)}:{n}')
    import plan
    L = json.loads(Path(layout).read_text(encoding='utf-8'))
    for _, msg in plan.check(L): problems.append(f'план: {msg}')
    bk = Path('D:/pol-ai/bk_assets')
    for it in L['items']:
        if it['key'] not in plan.LIB: problems.append(f"нет паспорта: {it['key']}"); continue
        if not (bk / f"{plan.LIB[it['key']]['file']}.blend").exists(): problems.append(f"нет файла модели: {it['key']}")
    for d in decors:
        if not (FLOORS / f'floor_{d}.png').exists(): problems.append(f'нет текстуры пола {d}: python tools/blender/floor_tex.py {d} {FLOORS}')
    try:
        used = int(subprocess.run(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'],
                                  capture_output=True, text=True).stdout.split()[0])
        if used > 4000: problems.append(f'видеокарта занята: {used} МБ (игра/другой рендер?)')
    except Exception: pass
    return problems


def run(cmd):
    print('»', ' '.join(str(c) for c in cmd)[:160], flush=True)
    r = subprocess.run([str(c) for c in cmd], cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode or 'Traceback' in (r.stdout + r.stderr):
        print((r.stdout + r.stderr)[-2000:]); sys.exit(f'ошибка на шаге: {cmd[0]}')
    return r.stdout


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    layout, out, decors = args[0], Path(args[1]), args[2:] or ['EPL179', 'EPL273']
    dn = sys.argv[sys.argv.index('--denoise') + 1] if '--denoise' in sys.argv else '0.5'
    if dn in args: args.remove(dn); decors = [d for d in decors if d != dn]
    probs = precheck(layout, decors)
    for p in probs: print('ПРОБЛЕМА:', p)
    if probs: sys.exit('Сначала исправить проблемы (правило: проверить → исправить → запускать).')
    print('Проверка пройдена.')
    if '--check' in sys.argv: sys.exit(0)
    run([BL, '-b', '-P', 'tools/interior/build.py', '--', layout, out, '256'])
    run([sys.executable, 'tools/blender/ai_realism.py', out, dn])
    run([BL, '-b', out / 'room.blend', '-P', 'tools/blender/floor_render.py', '--', FLOORS, '256', *decors])
    fl = out / 'floors'; fl.mkdir(exist_ok=True)
    for d in decors: (fl / f'room_{d}.png').write_bytes((FLOORS / f'room_{d}.png').read_bytes())
    run([sys.executable, 'tools/blender/floor_composite.py', out, fl, *decors])
    for d in decors:
        print(run([sys.executable, 'tools/interior/grade.py', fl / f'final_{d}.jpg', out / f'final_{d}.jpg']).strip())
    print('ГОТОВО:', ', '.join(str(out / f'final_{d}.jpg') for d in decors))
