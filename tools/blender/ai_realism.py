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
NEG = ('empty frame, blank canvas, abstract painting, extra furniture, missing objects, burlap, cgi, 3d render, computer graphics, cartoon, drawing style, plastic, oversaturated, blurry, distorted, '
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


def workflow(img, depth, denoise, seed, edges=None, change=None):
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
            'model': ['21', 0] if change else ['1', 0],
            'positive': ['14', 0] if edges else ['7', 0], 'negative': ['14', 1] if edges else ['7', 1],
            'latent_image': ['23', 0] if change else ['9', 0],
            'seed': seed, 'steps': 32, 'cfg': 5.0, 'sampler_name': 'dpmpp_2m', 'scheduler': 'karras', 'denoise': denoise}},
        '11': {'class_type': 'VAEDecode', 'inputs': {'samples': ['10', 0], 'vae': ['1', 2]}},
        '12': {'class_type': 'SaveImage', 'inputs': {'images': ['11', 0], 'filename_prefix': 'pol'}},
    } | ({  # второй поводок — контуры: нейросеть не меняет очертания предметов (урок: подменяла картину/вазу/плед)
        '13': {'class_type': 'LoadImage', 'inputs': {'image': edges}},
        '15': {'class_type': 'SetUnionControlNetType', 'inputs': {'control_net': ['4', 0], 'type': 'canny/lineart/anime_lineart/mlsd'}},
        '14': {'class_type': 'ControlNetApplyAdvanced', 'inputs': {
            'positive': ['7', 0], 'negative': ['7', 1], 'control_net': ['15', 0], 'image': ['13', 0], 'vae': ['1', 2],
            'strength': 0.55, 'start_percent': 0.0, 'end_percent': 0.7}},
    } if edges else {}) | ({  # карта силы: белое — менять смело, тёмное — почти не трогать
        '20': {'class_type': 'LoadImageMask', 'inputs': {'image': change, 'channel': 'red'}},
        '21': {'class_type': 'DifferentialDiffusion', 'inputs': {'model': ['1', 0]}},
        '23': {'class_type': 'SetLatentNoiseMask', 'inputs': {'samples': ['9', 0], 'mask': ['20', 0]}},
    } if change else {})


def prompt_from_layout(src):
    """Подсказка из расстановки (урок прогона 5: устаревший текст «abstract art» → нейросеть подменяла картину)."""
    lay = src / 'layout.json'
    if not lay.exists(): return POS
    L = json.loads(lay.read_text(encoding='utf-8'))
    lib = json.loads((Path(__file__).resolve().parents[1] / 'interior' / 'library.json').read_text(encoding='utf-8'))
    keys = [i['key'] for i in L['items']] + ['art_woodcut' if L.get('style', {}).get('art') == 'art_woodcut' else '',
                                              'books_real', 'vase_white', 'curtains']
    descs = list(dict.fromkeys(lib[k]['desc'] for k in keys if k in lib and lib[k].get('desc')))
    walls = lib['_finishes'].get(L.get('style', {}).get('walls', ''), {}).get('desc', 'smooth light painted walls')
    return ('professional interior photograph of a cozy lived-in living room, ' + ', '.join(descs) + ', ' + walls +
            ', white ceiling with cornice, window with trees outside, soft natural daylight, realistic textures, '
            'subtle imperfections, shot on canon eos r5, 24mm lens, high detail, photorealistic, magazine quality')


def main():
    src = Path(sys.argv[1]); denoise = float(sys.argv[2]) if len(sys.argv) > 2 else 0.4
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 7
    tmp = src / '_ai'; tmp.mkdir(exist_ok=True)
    ai_in = cv2.resize(cv2.imread(str(src / 'room_ai.png')), SIZE, interpolation=cv2.INTER_AREA)
    d = cv2.imread(str(src / 'depth0001.png'), 0).astype(np.float32)
    lo, hi = np.percentile(d, 1), np.percentile(d, 99.5)                # растянуть контраст глубины
    d = np.clip((d - lo) / max(hi - lo, 1) * 255, 0, 255).astype(np.uint8)
    cv2.imwrite(str(tmp / 'in.png'), ai_in); cv2.imwrite(str(tmp / 'depth.png'), cv2.resize(d, SIZE))
    # контуры предметов (из кадра Blender) и карта силы по меткам предметов
    g = cv2.cvtColor(ai_in, cv2.COLOR_BGR2GRAY)
    cv2.imwrite(str(tmp / 'edges.png'), cv2.Canny(cv2.GaussianBlur(g, (3, 3), 0), 60, 150))
    chg = np.ones(SIZE[::-1], np.float32)
    for name, keep in (('art_mask0001.png', 0.05), ('decor_mask0001.png', 0.35)):
        if (src / name).exists():
            mk = cv2.resize(cv2.imread(str(src / name), 0), SIZE).astype(np.float32) / 255
            mk = cv2.dilate(mk, np.ones((9, 9), np.uint8)); chg = np.minimum(chg, 1 - mk * (1 - keep))
    cv2.imwrite(str(tmp / 'change.png'), (cv2.GaussianBlur(chg, (0, 0), 3) * 255).astype(np.uint8))
    proc = server()
    try:
        a, b = upload(tmp / 'in.png', 'pol_in.png'), upload(tmp / 'depth.png', 'pol_depth.png')
        e_, c_ = upload(tmp / 'edges.png', 'pol_edges.png'), upload(tmp / 'change.png', 'pol_change.png')
        global POS
        POS = prompt_from_layout(src); print('ПОДСКАЗКА:', POS[:300])
        pid = api('/prompt', json.dumps({'prompt': workflow(a, b, denoise, seed, e_, c_)}).encode())['prompt_id']
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
    if (src / 'art_mask0001.png').exists():
        am = cv2.GaussianBlur(cv2.imread(str(src / 'art_mask0001.png'), 0).astype(np.float32) / 255, (0, 0), 1.0)[..., None]
        m = np.maximum(m, am)
    cv2.imwrite(str(src / 'room.png'), (out.astype(np.float32) * (1 - m) + base * m).astype(np.uint8))
    print('ГОТОВО', src / 'room.png')


if __name__ == '__main__':
    main()
