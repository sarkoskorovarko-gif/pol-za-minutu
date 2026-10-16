"""Рендер из Blender → «как фото» нейросетью (ComfyUI + RealVisXL + ControlNet по глубине).

Нейросеть перерисовывает всё, КРОМЕ пола: стены, мебель, ткани, вид за окном становятся фотографичными,
а пол остаётся из Blender (белый, с точным светом) — сайт кладёт на него любой декор.
ComfyUI лежит вне проекта: D:\\pol-ai\\comfyui (запускается этим скриптом сам).

Запуск:  python tools/blender/ai_realism.py <папка рендера> [сила 0.25–0.6] [seed]
Берёт room_ai.png, depth0001.png, room.png, floor_mask0001.png; пишет room_photo.png
и room.png (исходник сохраняется как room_blender.png).
"""
import json, subprocess, sys, time, uuid
from pathlib import Path
from urllib import request

import cv2
import numpy as np

COMFY = Path(r'D:\pol-ai\comfyui')
URL = 'http://127.0.0.1:8188'
SIZE = (1344, 896)                    # размер, на котором учили SDXL (3:2)
POS = ('professional interior photograph of a modern scandinavian living room, beige linen sofa with grey cushions on walnut frame, '
       'glass and walnut coffee table with a ceramic vase, cognac leather lounge armchair, large potted plant, brass floor lamp, '
       'framed abstract art, sheer white curtains, '
       'window with trees outside, soft natural daylight, sunlight patches, realistic fabric texture, subtle imperfections, '
       'shot on canon eos r5, 24mm lens, high detail, photorealistic, magazine quality')
NEG = ('cgi, 3d render, computer graphics, cartoon, illustration, painting, plastic, oversaturated, blurry, distorted, '
       'deformed furniture, extra objects, people, text, watermark, logo, lowres')


def api(path, data=None, raw=False):
    req = request.Request(URL + path, data=data, headers={} if data is None else {'Content-Type': 'application/json'})
    with request.urlopen(req, timeout=600) as r:
        b = r.read()
    return b if raw else json.loads(b)


def server():
    try:
        api('/system_stats'); return None
    except Exception:
        pass
    py = COMFY / 'python_embeded' / 'python.exe'
    p = subprocess.Popen([str(py), '-s', 'ComfyUI/main.py', '--listen', '127.0.0.1', '--port', '8188', '--disable-auto-launch'],
                         cwd=COMFY, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(180):
        time.sleep(2)
        try:
            api('/system_stats'); return p
        except Exception:
            pass
    raise RuntimeError('ComfyUI не запустился')


def upload(path, name):
    b = '----pol' + uuid.uuid4().hex
    body = (f'--{b}\r\nContent-Disposition: form-data; name="image"; filename="{name}"\r\nContent-Type: image/png\r\n\r\n').encode() \
        + Path(path).read_bytes() + f'\r\n--{b}\r\nContent-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n--{b}--\r\n'.encode()
    req = request.Request(URL + '/upload/image', data=body, headers={'Content-Type': f'multipart/form-data; boundary={b}'})
    return json.loads(request.urlopen(req).read())['name']


def workflow(img, depth, denoise, seed):
    return {
        '1': {'class_type': 'CheckpointLoaderSimple', 'inputs': {'ckpt_name': 'RealVisXL_V5.0_fp16.safetensors'}},
        '2': {'class_type': 'CLIPTextEncode', 'inputs': {'text': POS, 'clip': ['1', 1]}},
        '3': {'class_type': 'CLIPTextEncode', 'inputs': {'text': NEG, 'clip': ['1', 1]}},
        '4': {'class_type': 'ControlNetLoader', 'inputs': {'control_net_name': 'controlnet-union-sdxl-promax.safetensors'}},
        '5': {'class_type': 'SetUnionControlNetType', 'inputs': {'control_net': ['4', 0], 'type': 'depth'}},
        '6': {'class_type': 'LoadImage', 'inputs': {'image': depth}},
        '7': {'class_type': 'ControlNetApplyAdvanced', 'inputs': {
            'positive': ['2', 0], 'negative': ['3', 0], 'control_net': ['5', 0], 'image': ['6', 0], 'vae': ['1', 2],
            'strength': 0.75, 'start_percent': 0.0, 'end_percent': 0.85}},
        '8': {'class_type': 'LoadImage', 'inputs': {'image': img}},
        '9': {'class_type': 'VAEEncode', 'inputs': {'pixels': ['8', 0], 'vae': ['1', 2]}},
        '10': {'class_type': 'KSampler', 'inputs': {
            'model': ['1', 0], 'positive': ['7', 0], 'negative': ['7', 1], 'latent_image': ['9', 0],
            'seed': seed, 'steps': 32, 'cfg': 5.0, 'sampler_name': 'dpmpp_2m', 'scheduler': 'karras', 'denoise': denoise}},
        '11': {'class_type': 'VAEDecode', 'inputs': {'samples': ['10', 0], 'vae': ['1', 2]}},
        '12': {'class_type': 'SaveImage', 'inputs': {'images': ['11', 0], 'filename_prefix': 'pol'}},
    }


def main():
    src = Path(sys.argv[1]); denoise = float(sys.argv[2]) if len(sys.argv) > 2 else 0.4
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 7
    tmp = src / '_ai'; tmp.mkdir(exist_ok=True)
    ai_in = cv2.resize(cv2.imread(str(src / 'room_ai.png')), SIZE, interpolation=cv2.INTER_AREA)
    d = cv2.imread(str(src / 'depth0001.png'), 0).astype(np.float32)
    lo, hi = np.percentile(d, 1), np.percentile(d, 99.5)                # растянуть контраст глубины
    d = np.clip((d - lo) / max(hi - lo, 1) * 255, 0, 255).astype(np.uint8)
    cv2.imwrite(str(tmp / 'in.png'), ai_in); cv2.imwrite(str(tmp / 'depth.png'), cv2.resize(d, SIZE))
    proc = server()
    try:
        a, b = upload(tmp / 'in.png', 'pol_in.png'), upload(tmp / 'depth.png', 'pol_depth.png')
        pid = api('/prompt', json.dumps({'prompt': workflow(a, b, denoise, seed)}).encode())['prompt_id']
        while True:
            time.sleep(2)
            h = api(f'/history/{pid}')
            if pid in h and h[pid].get('outputs'):
                im = h[pid]['outputs']['12']['images'][0]; break
            if pid in h and h[pid].get('status', {}).get('status_str') == 'error':
                raise RuntimeError(json.dumps(h[pid]['status'])[:800])
        png = api(f"/view?filename={im['filename']}&subfolder={im['subfolder']}&type=output", raw=True)
    finally:
        if proc: proc.terminate()
    out = cv2.imdecode(np.frombuffer(png, np.uint8), 1)
    base = cv2.imread(str(src / 'room.png')); H, W = base.shape[:2]
    out = cv2.resize(out, (W, H), interpolation=cv2.INTER_LANCZOS4)
    cv2.imwrite(str(src / 'room_photo.png'), out)
    # итог: нейросеть — везде, кроме пола; пол — из Blender (по нему сайт считает свет)
    m = cv2.imread(str(src / 'floor_mask0001.png'), 0).astype(np.float32) / 255
    m = cv2.GaussianBlur(m, (0, 0), 1.2)[..., None]
    if not (src / 'room_blender.png').exists():
        cv2.imwrite(str(src / 'room_blender.png'), base)
    base = cv2.imread(str(src / 'room_blender.png')).astype(np.float32)
    cv2.imwrite(str(src / 'room.png'), (out.astype(np.float32) * (1 - m) + base * m).astype(np.uint8))
    print('ГОТОВО', src / 'room.png')


if __name__ == '__main__':
    main()
