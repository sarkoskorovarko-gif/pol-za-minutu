r"""Фото декора ×4 нейросетью (ComfyUI + 4x-UltraSharp): доски вблизи чёткие, видны поры.

Запуск:  python tools/blender/upscale_tex.py <id> [id ...]
Пишет D:\pol-ai\tex4x\<id>.png — floor_tex.py берёт его, если он есть.
"""
import json, sys, time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from ai_realism import api, server, upload

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(r'D:\pol-ai\tex4x')


def wf(img):
    return {'1': {'class_type': 'LoadImage', 'inputs': {'image': img}},
            '2': {'class_type': 'UpscaleModelLoader', 'inputs': {'model_name': '4x-UltraSharp.pth'}},
            '3': {'class_type': 'ImageUpscaleWithModel', 'inputs': {'upscale_model': ['2', 0], 'image': ['1', 0]}},
            '4': {'class_type': 'SaveImage', 'inputs': {'images': ['3', 0], 'filename_prefix': 'pol_tex4x'}}}


def main():
    OUT.mkdir(exist_ok=True); tmp = OUT / '_in'; tmp.mkdir(exist_ok=True)
    proc = server()
    try:
        for did in sys.argv[1:]:
            png = tmp / f'{did}.png'                          # ComfyUI ждёт латиницу в пути — копия рядом
            cv2.imencode('.png', cv2.imdecode(np.fromfile(ROOT / 'data' / 'textures' / f'{did}.jpg', np.uint8), 1))[1].tofile(png)
            pid = api('/prompt', json.dumps({'prompt': wf(upload(png, f'pol_{did}.png'))}).encode())['prompt_id']
            while True:
                time.sleep(1)
                h = api(f'/history/{pid}')
                if pid in h and h[pid].get('outputs'):
                    im = h[pid]['outputs']['4']['images'][0]; break
                if pid in h and h[pid].get('status', {}).get('status_str') == 'error':
                    raise RuntimeError(json.dumps(h[pid]['status'])[:800])
            (OUT / f'{did}.png').write_bytes(api(f"/view?filename={im['filename']}&subfolder={im['subfolder']}&type=output", raw=True))
            print('ok', did)
    finally:
        if proc: proc.terminate()


if __name__ == '__main__':
    main()
