r"""Фото двери из каталога ×4 нейросетью (4x-UltraSharp): 250×600 → 1000×2400, чтобы дверь в комнате была чёткой.

Запуск:  python tools/blender/door_upscale.py <имя> [имя ...]
Берёт D:\pol-ai\doors\<имя>.jpg, пишет D:\pol-ai\doors\4x\<имя>.png. Дальше door_model.py натягивает его на 3D-полотно.
"""
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from ai_realism import api, server, upload
from upscale_tex import wf

SRC = Path(r'D:\pol-ai\doors'); OUT = SRC / '4x'


def main():
    OUT.mkdir(exist_ok=True)
    proc = server()
    try:
        for name in sys.argv[1:]:
            pid = api('/prompt', json.dumps({'prompt': wf(upload(SRC / f'{name}.jpg', f'pol_door_{name}.jpg'))}).encode())['prompt_id']
            while True:
                time.sleep(1)
                h = api(f'/history/{pid}')
                if pid in h and h[pid].get('outputs'):
                    im = h[pid]['outputs']['4']['images'][0]; break
                if pid in h and h[pid].get('status', {}).get('status_str') == 'error':
                    raise RuntimeError(json.dumps(h[pid]['status'])[:800])
            (OUT / f'{name}.png').write_bytes(api(f"/view?filename={im['filename']}&subfolder={im['subfolder']}&type=output", raw=True))
            print('ok', name, cv2.imread(str(OUT / f'{name}.png')).shape)
    finally:
        if proc: proc.terminate()


if __name__ == '__main__':
    main()
