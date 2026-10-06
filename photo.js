// Фото-интерьеры: на настоящую фотографию комнаты подставляется выбранный ламинат.
// Как это работает:
//  1) По 4 точкам на полу (углы прямоугольника W×D метров) считаем перспективу —
//     для каждой точки фото знаем, какое место пола туда попадает (в метрах).
//  2) Маска пола (контур минус мебель) говорит, где менять пол, а где оставить фото.
//  3) Свет и тени берём с исходного фото: размытая яркость пола / средняя яркость пола.
import * as THREE from 'three';

const MASK_V = 'v44'; // версия масок = версия сайта (меняется вместе с ?v=), иначе телефон берёт старые из кэша
const DEFAULT_TEX_W_M = 1.3; // м пола по ширине фото декора (как в 3D)

let renderer, scene, camera, mat, mesh, canvasEl;
let cur = null;          // текущее фото: { data, photoTex, blurTex, maskTex, meanL }
let decorTex = null, decorSize = [DEFAULT_TEX_W_M, 0.8];
const grade = { b: 0.8, w: -0.2 };
let skirt = null;        // плинтус: { color: [r,g,b] 0…1 или 'decor', h: высота, м }
let decorAvg = [0.6, 0.5, 0.4];
const cache = {};

export function initPhoto(canvas) {
  canvasEl = canvas;
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  scene = new THREE.Scene();
  camera = new THREE.OrthographicCamera(-0.5, 0.5, 0.5, -0.5, 0, 1);
  mat = new THREE.ShaderMaterial({
    uniforms: {
      photo: { value: null }, blurP: { value: null }, medP: { value: null }, gloss: { value: 0.35 }, mask: { value: null }, decor: { value: null },
      Hinv: { value: new THREE.Matrix3() }, imgSize: { value: new THREE.Vector2(1, 1) },
      texM: { value: new THREE.Vector2(1.3, 0.8) }, meanL: { value: 0.5 }, rot: { value: 0 },
      meanC: { value: new THREE.Vector3(0.3, 0.3, 0.3) }, roomTint: { value: new THREE.Vector3(1, 1, 1) },
      lampFloor: { value: new THREE.Vector2(1.5, 1.5) }, hasLamp: { value: 0 },
      exposure: { value: 1 }, tint: { value: new THREE.Vector3(1, 1, 1) }, night: { value: 0 },
      skCol: { value: new THREE.Vector3(1, 1, 1) }, skOn: { value: 0 }, skL: { value: 0.5 },
      boardOn: { value: 0 }, board: { value: new THREE.Vector2(1.29, 0.193) },
      rows: { value: new THREE.Vector2(0, 0.2) }, bevel: { value: 0 },
      showGrid: { value: 0 }, crop: { value: new THREE.Vector4(0, 0, 1, 1) },
    },
    vertexShader: `varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy * 2.0, 0.0, 1.0); }`,
    fragmentShader: `
      precision highp float;
      varying vec2 vUv;
      uniform sampler2D photo, blurP, medP, mask, decor; uniform float gloss;
      uniform mat3 Hinv; uniform vec2 imgSize, texM; uniform float meanL, rot, exposure, night, showGrid;
      uniform vec3 tint, meanC, roomTint; uniform vec4 crop; uniform vec2 lampFloor; uniform float hasLamp;
      uniform vec3 skCol; uniform float skOn, skL;
      uniform float boardOn, bevel; uniform vec2 board, rows;
      float h1(vec2 p){ return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
      // Цвет пола в точке fm (метры). Доски кладём по-настоящему: ряды со смещением,
      // каждая доска — из случайного места фото декора (нет повторов и «зеркал»), фаска на стыках.
      vec3 floorColor(vec2 fm){
        vec2 uvc = fm / texM;                              // непрерывные координаты — для резкости
        if (boardOn < 0.5) return texture2D(decor, uvc).rgb;
        float L = board.x, W = board.y;
        float row = floor(fm.y / W);
        // разбег стыков соседних рядов — не меньше ~1/3 доски, как при укладке
        float x = fm.x + fract(row * 0.382 + h1(vec2(row, 7.0)) * 0.25) * L;
        float col = floor(x / L);
        vec2 loc = vec2(x - col * L, fm.y - row * W);      // место внутри доски, м
        float nr = max(1.0, floor((1.0 - rows.x) / rows.y + 0.01));
        float k = floor(h1(vec2(row, col)) * nr);          // какой ряд фото декора берём
        float u0 = h1(vec2(col, row + 31.0)) * max(0.0, 1.0 - L / texM.x);
        vec2 uv = vec2(u0 + loc.x / texM.x, 1.0 - (rows.x + (k + loc.y / W) * rows.y));
        vec2 gx = dFdx(uvc), gy = dFdy(uvc);
        vec3 c = textureGrad(decor, uv, gx, gy).rgb;
        // резкость: фото декора маленькое, вблизи оно мутнеет — возвращаем мелкий рисунок
        vec3 cb = textureGrad(decor, uv, gx * 3.0, gy * 3.0).rgb;
        float near = clamp(1.0 - length(gx) * 600.0, 0.0, 1.0);
        c = max(c + (c - cb) * 0.45 * near, 0.0);
        // разница тона и насыщенности между досками — как в жизни
        float hv = h1(vec2(col * 3.1, row * 1.7));
        c *= 0.94 + 0.12 * hv;
        c = mix(vec3(dot(c, vec3(0.333))), c, 0.92 + 0.16 * h1(vec2(row * 2.3, col)));
        // фаска / стык: тонкая тёмная линия, сглаженная по размеру пикселя
        float e = min(min(loc.x, L - loc.x), min(loc.y, W - loc.y));
        float aa = max(fwidth(fm.x), fwidth(fm.y));
        float wl = mix(0.0006, 0.0022, bevel);             // ширина линии, м
        float fade = clamp(wl / aa, 0.0, 1.0);          // вдали стык тоньше пикселя — бледнее, не толще
        float seam = (1.0 - smoothstep(wl, wl + aa, e)) * fade;
        // фаска: у дальнего края доски (к камере смотрит «скат») — тонкий блик,
        // у ближнего — тень; торцевые стыки слабее продольных
        float lng = 1.0 - smoothstep(wl, wl + aa, min(loc.y, W - loc.y));
        float hiE = W - loc.y;                            // дальний продольный край
        float hl = (smoothstep(wl, wl + aa, hiE) - smoothstep(wl * 2.2, wl * 2.2 + aa, hiE)) * fade * bevel;
        float sd = mix(0.12, 0.30, bevel) * mix(0.6, 1.0, lng);
        return c * (1.0 - seam * sd) * (1.0 + hl * 0.18);
      }
      // sRGB <-> линейный свет (тени и свет умножаем в линейном пространстве)
      vec3 toLin(vec3 c){ return pow(c, vec3(2.2)); }
      vec3 toSrgb(vec3 c){ return pow(max(c, 0.0), vec3(1.0/2.2)); }
      float lum(vec3 c){ return dot(c, vec3(0.2126, 0.7152, 0.0722)); }
      void main(){
        vec2 uv = crop.xy + vUv * crop.zw;              // какая часть фото на экране
        vec2 px = vec2(uv.x, 1.0 - uv.y) * imgSize;      // пиксели фото (y вниз)
        vec3 src = toLin(texture2D(photo, uv).rgb);
        vec4 mk = texture2D(mask, uv);
        float m = mk.r;                                  // красный канал — пол, зелёный — окна
        // Пол считаем для всех пикселей (без if): иначе производные (резкость, стыки)
        // у края маски «искрят»
        vec3 f = Hinv * vec3(px, 1.0);
        vec2 fm = f.xy / f.z;                            // точка пола в метрах
        float r = length(fm - lampFloor);                // расстояние до точки под люстрой
        if (rot > 0.5) fm = fm.yx;
        vec3 d = toLin(floorColor(fm));
        // Свет с фото — только освещение, без рисунка и тона старого пола:
        // крупный и средний размытый свет ПОЛА (стены не подмешаны), к «нормальной» яркости
        vec4 BL = texture2D(blurP, uv), BM = texture2D(medP, uv);
        float Ll = lum(toLin(BL.rgb)) / meanL, Lm = lum(toLin(BM.rgb)) / meanL;
        float S = pow(clamp(mix(Ll, Lm, 0.45), 0.3, 2.4), 0.92);
        // у стен и мебели пол чуть темнее (свет туда попадает меньше)
        float occ = (1.0 - 0.22 * BM.a) * (1.0 - 0.10 * BL.a);
        vec3 dayLight = vec3(S * occ) * roomTint;
        // Вечер: дневной рисунок света (солнце, блики окон) убираем совсем.
        // Остаются только мягкие тени (где на фото темнее среднего), светит люстра.
        float ao = mix(0.55, 1.0, smoothstep(0.2, 0.7, Ll)) * occ;
        float lampL = hasLamp > 0.5 ? 0.45 + 0.75 / (1.0 + r * r / 6.0) : 0.9;
        vec3 light = mix(dayLight, vec3(ao * lampL), night);
        vec3 fl = d * light;
        // отражения окон и ламп: где старый пол ярче общего света (средний минус крупный);
        // сильнее к дальней части комнаты — под скользящим углом пол блестит больше
        float refl = max(lum(toLin(BM.rgb)) - lum(toLin(BL.rgb)) * 1.08, 0.0);
        float fres = mix(0.5, 1.3, smoothstep(0.0, 0.6, vUv.y));
        fl += vec3(refl * gloss * fres) * (1.0 - night);
        fl += vec3(0.06 * exp(-r * r / 0.5)) * night * ao * hasLamp; // отражение люстры — если отмечена
        // мягкое «плечо»: яркое не выгорает в белое пятно
        fl = mix(fl, 0.6 + 0.4 * (1.0 - exp(-(fl - 0.6) / 0.4)), step(0.6, fl));
        // зерно как у фото — слишком чистый пол выглядит наклеенным
        fl *= 1.0 + (h1(px) + h1(px + 17.3) - 1.0) * 0.03;
        if (showGrid > 0.5) {                            // сетка 0,5 м — для разметки
          vec2 gq = abs(fract(fm / 0.5 + 0.5) - 0.5) / fwidth(fm / 0.5);
          fl = mix(vec3(1.0, 0.1, 0.1), fl, clamp(min(gq.x, gq.y), 0.0, 1.0));
        }
        // тонкий край маски: без полупрозрачной полосы старого пола
        vec3 col = mix(src, fl, smoothstep(0.02, 0.98, m)); // край маски уже сглажен — не «ужесточаем» (иначе лесенка)
        // Плинтус: синий канал маски — полоса над линией пола у стен.
        // Свет берём с фото (где старый плинтус в тени — новый тоже), ночью — как пол.
        float sk = mk.b * skOn * (1.0 - smoothstep(0.2, 0.8, m)); // на пол плинтус не заходит
        if (sk > 0.001) {
          float Ls = lum(toLin(texture2D(blurP, uv).rgb)) / skL;
          float lt = mix(clamp(Ls, 0.3, 1.0) * 0.9, 0.7, night * 0.6); // не ярче, чем было на фото — иначе «светится»
          col = mix(col, skCol * lt, sk);
        }
        // Вечер: яркие окна (не пол) становятся тёмным вечерним небом
        // вечером в окнах — тёмное небо; рамы (тёмные на фото) остаются
        float glass = mk.g * smoothstep(0.25, 0.6, lum(src));
        col = mix(col, vec3(0.015, 0.025, 0.06), glass * night);
        // Свет: яркость и оттенок; вечером — темнее, теплее, края темнее
        col *= exposure * tint;
        vec2 q = vUv - 0.5;
        col *= 1.0 - night * 0.55 * dot(q, q) * 2.0;
        col = mix(col, vec3(lum(col)), night * 0.2);
        gl_FragColor = vec4(toSrgb(col), 1.0);
      }`,
  });
  mat.extensions = { derivatives: true };
  mesh = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), mat);
  scene.add(mesh);
  new ResizeObserver(resize).observe(canvas);
}

function resize() {
  const w = canvasEl.clientWidth, h = canvasEl.clientHeight;
  if (!w || !h) return;
  renderer.setSize(w, h, false);
  fitCrop();
  render();
}

// Фото заполняет экран целиком (как background-size: cover), середина по центру
function fitCrop() {
  if (!cur) return;
  const [iw, ih] = cur.data.img;
  const ca = canvasEl.clientWidth / canvasEl.clientHeight, ia = iw / ih;
  const fx = cur.data.focus ? cur.data.focus[0] / iw : 0.5; // куда смещать кадр на узком экране
  let c;
  if (ia > ca) { const s = ca / ia; c = [Math.min(1 - s, Math.max(0, fx - s / 2)), 0, s, 1]; }
  else { const s = ia / ca; c = [0, (1 - s) / 2, 1, s]; }
  mat.uniforms.crop.value.set(...c);
  fitFurnCrop();
}

export function render() {
  if (!(renderer && cur && decorTex)) return;
  renderer.render(scene, camera);
  if (furnOn && furn.group.children.length && furn.cam) {   // мебель — 3D поверх фото
    renderer.autoClear = false; renderer.clearDepth();
    renderer.render(furn.scene, furn.cam);
    renderer.autoClear = true;
  }
}

// ---------- Мебель: 3D-модели, поставленные на пол фото ----------
// По 4 точкам пола восстанавливаем камеру (фокус, положение, поворот) — модели рисуются
// под тем же углом, что и фото. Мебель задаётся в photos.json: furniture: [{ m, x, y, rot }]
// (x, y — метры в прямоугольнике пола, rot — градусы; модели в data/furniture/<m>/).
let furnOn = false;
const furn = { scene: null, cam: null, group: null, models: {}, roomId: null, loader: null };

function initFurniture() {
  furn.scene = new THREE.Scene();
  furn.scene.add(new THREE.HemisphereLight(0xffffff, 0x8a7a6a, 2.2));
  const sun = new THREE.DirectionalLight(0xffffff, 1.4); sun.position.set(1, 3, 2); furn.scene.add(sun);
  furn.group = new THREE.Group(); furn.group.matrixAutoUpdate = false;
  furn.scene.add(furn.group);
  furn.cam = new THREE.PerspectiveCamera();
  furn.cam.matrixAutoUpdate = false; furn.cam.matrixWorldAutoUpdate = false;
}

// Камера из перспективы пола. false — если по этим точкам камеру не восстановить
function solveCamera(d) {
  const [W, D] = d.size, [iw, ih] = d.img, cx = iw / 2, cy = ih / 2;
  const h = homography([[0, 0], [W, 0], [W, D], [0, D]], d.quad);   // метры → пиксели
  const M = [[h[0] - cx * h[6], h[1] - cx * h[7], h[2] - cx * h[8]],
             [h[3] - cy * h[6], h[4] - cy * h[7], h[5] - cy * h[8]],
             [h[6], h[7], h[8]]];
  const col = i => [M[0][i], M[1][i], M[2][i]];
  const [a1, b1, g1] = col(0), [a2, b2, g2] = col(1);
  const f2 = -(a1 * a2 + b1 * b2) / (g1 * g2);
  if (!(f2 > 0)) return false;
  const f = Math.sqrt(f2), kv = v => [v[0] / f, v[1] / f, v[2]], len = v => Math.hypot(...v);
  const c1 = kv(col(0)), c2 = kv(col(1)), c3 = kv(col(2));
  let lam = 2 / (len(c1) + len(c2));
  if (c3[2] * lam < 0) lam = -lam;                                   // фото — перед камерой
  const r1 = c1.map(v => v * lam), t = c3.map(v => v * lam);
  let r2 = c2.map(v => v * lam);
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const r3 = cross(r1, r2); r2 = cross(r3, r1);
  const n = v => { const l = len(v); return v.map(x => x / l); };
  const R = [n(r1), n(r2), n(r3)];                                   // столбцы R
  // вид камеры three.js: оси OpenCV (y вниз, z вперёд) → (y вверх, z назад)
  const V = new THREE.Matrix4().set(
     R[0][0],  R[1][0],  R[2][0],  t[0],
    -R[0][1], -R[1][1], -R[2][1], -t[1],
    -R[0][2], -R[1][2], -R[2][2], -t[2],
     0, 0, 0, 1);
  const cam = furn.cam;
  cam.fov = 2 * Math.atan(ih / 2 / f) * 180 / Math.PI;
  cam.aspect = iw / ih; cam.near = 0.05; cam.far = 100;
  cam.matrixWorldInverse.copy(V); cam.matrixWorld.copy(V).invert();
  // где «верх»: камера должна быть над полом
  const camZ = -(R[2][0] * t[0] + R[2][1] * t[1] + R[2][2] * t[2]);
  const s = camZ > 0 ? 1 : -1;
  // модели: x → X пола, y (вверх) → s·Z, z → −s·Y (так поворот не зеркальный)
  furn.group.matrix.set(1, 0, 0, 0,  0, 0, -s, 0,  0, s, 0, 0,  0, 0, 0, 1);
  furn.group.matrixWorldNeedsUpdate = true;
  furn.f = f; furn.s = s;
  return true;
}

function fitFurnCrop() {
  if (!furn.cam || !cur) return;
  const [iw, ih] = cur.data.img, c = mat.uniforms.crop.value;
  furn.cam.setViewOffset(iw, ih, c.x * iw, c.y * ih, c.z * iw, c.w * ih);
  furn.cam.updateProjectionMatrix();
}

function shadowTex() {
  const c = document.createElement('canvas'); c.width = c.height = 128;
  const g = c.getContext('2d'), gr = g.createRadialGradient(64, 64, 8, 64, 64, 64);
  gr.addColorStop(0, 'rgba(0,0,0,0.55)'); gr.addColorStop(0.6, 'rgba(0,0,0,0.25)'); gr.addColorStop(1, 'rgba(0,0,0,0)');
  g.fillStyle = gr; g.fillRect(0, 0, 128, 128);
  return new THREE.CanvasTexture(c);
}

async function loadModel(m) {
  if (furn.models[m]) return furn.models[m];
  if (!furn.loader) {
    const { GLTFLoader } = await import('./lib/jsm/loaders/GLTFLoader.js');
    furn.loader = new GLTFLoader();
  }
  const gltf = await furn.loader.loadAsync(`${window.PHOTO_BASE || ''}data/furniture/${m}/${m}.gltf`);
  const obj = gltf.scene, box = new THREE.Box3().setFromObject(obj), size = box.getSize(new THREE.Vector3());
  obj.position.y -= box.min.y;                                       // ножки — на пол
  obj.position.x -= (box.min.x + box.max.x) / 2; obj.position.z -= (box.min.z + box.max.z) / 2;
  const holder = new THREE.Group(); holder.add(obj);
  // мягкая тень под мебелью
  const sh = new THREE.Mesh(new THREE.PlaneGeometry(size.x * 1.25, size.z * 1.35),
    new THREE.MeshBasicMaterial({ map: furn.shadow || (furn.shadow = shadowTex()), transparent: true, depthWrite: false }));
  sh.rotation.x = -Math.PI / 2; sh.position.y = 0.002; sh.renderOrder = -1;
  holder.add(sh);
  return (furn.models[m] = holder);
}

async function placeFurniture() {
  if (!cur) return;
  const d = cur.data;
  if (!furn.scene) initFurniture();
  furn.group.clear();
  furn.roomId = d.id;
  if (!furnOn || !d.furniture || !d.size) { render(); return; }
  if (!solveCamera(d)) { render(); throw new Error('для этого фото не вычисляется камера'); }
  fitFurnCrop();
  const errs = [];
  for (const it of d.furniture) {
    try {
      const proto = await loadModel(it.m);
      if (furn.roomId !== d.id) return;                              // пока грузили — сменили комнату
      const o = proto.clone();
      o.position.set(it.x, 0, -furn.s * it.y);                       // z модели → Y пола (см. матрицу группы)
      o.rotation.y = (it.rot || 0) * Math.PI / 180;
      furn.group.add(o);
    } catch (e) { console.warn('мебель не загрузилась', it.m, e); errs.push(it.m + ': ' + (e && e.message || e)); }
  }
  render();
  if (errs.length) throw new Error(errs.join('; '));
}

export function setFurniture(on) { furnOn = on; return placeFurniture(); }
export function roomHasFurniture(d) { return !!(d && d.furniture && d.furniture.length); }

// ---------- Перспектива: 4 точки фото → прямоугольник W×D м ----------
// Решаем систему 8×8 (классическое преобразование по 4 точкам)
function homography(src, dst) {
  const A = [], b = [];
  for (let i = 0; i < 4; i++) {
    const [x, y] = src[i], [u, v] = dst[i];
    A.push([x, y, 1, 0, 0, 0, -u * x, -u * y]); b.push(u);
    A.push([0, 0, 0, x, y, 1, -v * x, -v * y]); b.push(v);
  }
  // метод Гаусса
  for (let c = 0; c < 8; c++) {
    let p = c;
    for (let r = c + 1; r < 8; r++) if (Math.abs(A[r][c]) > Math.abs(A[p][c])) p = r;
    [A[c], A[p]] = [A[p], A[c]]; [b[c], b[p]] = [b[p], b[c]];
    for (let r = 0; r < 8; r++) if (r !== c) {
      const k = A[r][c] / A[c][c];
      for (let j = c; j < 8; j++) A[r][j] -= k * A[c][j];
      b[r] -= k * b[c];
    }
  }
  const h = b.map((v, i) => v / A[i][i]);
  return [h[0], h[1], h[2], h[3], h[4], h[5], h[6], h[7], 1];
}

function updateGeometry() {
  const d = cur.data, [W, D] = d.size;
  const h = homography(d.quad, [[0, 0], [W, 0], [W, D], [0, D]]); // фото → метры
  mat.uniforms.Hinv.value.set(...h);
  if (d.lamp) {
    const [x, y] = d.lamp, z = h[6] * x + h[7] * y + h[8];
    mat.uniforms.lampFloor.value.set((h[0] * x + h[1] * y + h[2]) / z, (h[3] * x + h[4] * y + h[5]) / z);
  }
  mat.uniforms.hasLamp.value = d.lamp ? 1 : 0; // без отметки люстры — ровный вечерний свет
  mat.uniforms.imgSize.value.set(...d.img);
  mat.uniforms.rot.value = d.rotate ? 1 : 0;
}

// ---------- Маска пола и карта света ----------
function makeMask(d) {
  const [iw, ih] = d.img, s = Math.min(1, 2048 / Math.max(iw, ih)); // полный размер — края без ступенек
  const c = document.createElement('canvas');
  c.width = Math.round(iw * s); c.height = Math.round(ih * s);
  const g = c.getContext('2d');
  g.scale(s, s);
  g.filter = `blur(${1.5 / s}px)`; // мягкий край, чтобы не было «лесенки»
  const poly = (pts, color) => {
    g.fillStyle = color; g.beginPath();
    pts.forEach(([x, y], i) => i ? g.lineTo(x, y) : g.moveTo(x, y));
    g.closePath(); g.fill();
  };
  g.fillStyle = '#000'; g.fillRect(0, 0, iw, ih);
  if (d._maskImg) {
    // уточнённая маска (tools/refine_masks.py): белое — пол → в красный канал
    g.filter = 'none';
    g.drawImage(d._maskImg, 0, 0, iw, ih);
    g.globalCompositeOperation = 'multiply'; g.fillStyle = '#f00'; g.fillRect(0, 0, iw, ih);
    g.globalCompositeOperation = 'source-over'; g.filter = `blur(${1.5 / s}px)`;
  } else {
    poly(d.floor, '#f00');
    (d.holes || []).forEach(h => poly(h, '#000'));
  }
  g.globalCompositeOperation = 'lighter';         // окна — в зелёный канал, пол не трогаем
  (d.windows || []).forEach(h => poly(h, '#0f0'));
  const band = skirtBand(d, c.width, c.height, s);
  if (band) { g.filter = 'none'; g.setTransform(1, 0, 0, 1, 0, 0); g.drawImage(band, 0, 0); }
  return c;
}

// Линии «пол — стена»: из разметки (base) или рёбра контура пола, не лежащие на краю фото
function baseLines(d) {
  if (d.base) return d.base;
  const [iw, ih] = d.img, e = 3, out = [];
  const edge = ([x, y]) => x <= e || x >= iw - e || y >= ih - e;
  d.floor.forEach((p, i) => {
    const q = d.floor[(i + 1) % d.floor.length];
    if (!(edge(p) && edge(q)) && !(p[0] === q[0] && (edge(p) || edge(q)))) out.push([p, q]);
  });
  return out;
}

// Полоса плинтуса (синий канал): высота в пикселях — по масштабу пола в этой точке
function skirtBand(d, w, h, s) {
  if (!d.size) return null;
  const [W, D] = d.size, H = homography([[0, 0], [W, 0], [W, D], [0, D]], d.quad); // метры → фото
  const Hi = homography(d.quad, [[0, 0], [W, 0], [W, D], [0, D]]);
  const ap = (m, x, y) => { const z = m[6] * x + m[7] * y + m[8]; return [(m[0] * x + m[1] * y + m[2]) / z, (m[3] * x + m[4] * y + m[5]) / z]; };
  const hm = (skirt && skirt.h) || 0.07;
  const up = ([x, y]) => {        // сколько пикселей вверх занимает плинтус высотой hm у точки пола
    const [a, b] = ap(Hi, x, y), k = 0.05;
    const dx = ap(H, a + k, b), dy = ap(H, a, b + k);
    const sc = Math.max(Math.hypot(dx[0] - x, dx[1] - y), Math.hypot(dy[0] - x, dy[1] - y)) / k;
    return Math.min(sc * hm, 200);
  };
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  const g = c.getContext('2d');
  g.scale(s, s); g.filter = `blur(${1 / s}px)`; g.fillStyle = '#00f';
  for (const [p, q] of baseLines(d)) {
    const n = 8;
    g.beginPath();
    for (let i = 0; i <= n; i++) { const t = i / n, x = p[0] + (q[0] - p[0]) * t, y = p[1] + (q[1] - p[1]) * t; i ? g.lineTo(x, y - up([x, y])) : g.moveTo(x, y - up([x, y])); }
    for (let i = n; i >= 0; i--) { const t = i / n; g.lineTo(p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t + 1.5); }
    g.closePath(); g.fill();
  }
  // мебель закрывает плинтус
  g.globalCompositeOperation = 'destination-out'; g.fillStyle = '#000';
  (d.holes || []).forEach(pts => { g.beginPath(); pts.forEach(([x, y], i) => i ? g.lineTo(x, y) : g.moveTo(x, y)); g.closePath(); g.fill(); });
  return c;
}

// Размытие «коробкой» (3 прохода ≈ гаусс) с повтором края; a — массив w*h
function boxBlur(a, w, h, r) {
  let src = a;
  const tmp = new Float32Array(w * h);
  for (let pass = 0; pass < 3; pass++) {
    const out = new Float32Array(w * h);
    for (let y = 0; y < h; y++) {                 // по строкам
      let acc = 0; const o = y * w;
      for (let k = -r; k <= r; k++) acc += src[o + Math.min(w - 1, Math.max(0, k))];
      for (let x = 0; x < w; x++) {
        tmp[o + x] = acc / (2 * r + 1);
        acc += src[o + Math.min(w - 1, x + r + 1)] - src[o + Math.max(0, x - r)];
      }
    }
    for (let x = 0; x < w; x++) {                 // по столбцам
      let acc = 0;
      for (let k = -r; k <= r; k++) acc += tmp[Math.min(h - 1, Math.max(0, k)) * w + x];
      for (let y = 0; y < h; y++) {
        out[y * w + x] = acc / (2 * r + 1);
        acc += tmp[Math.min(h - 1, y + r + 1) * w + x] - tmp[Math.max(0, y - r) * w + x];
      }
    }
    src = out;
  }
  return src;
}

// Карта света пола. Размываем ТОЛЬКО пол (стены и мебель не «натекают» на край — нет каймы):
// blur(фото·маска) / blur(маска), в линейном свете. Две ширины: крупная — общий свет и тени,
// средняя — пятна солнца и отражения окон. Плюс затенение у стен и мебели (по маске).
function makeLight(img, maskCanvas) {
  const s = 512 / Math.max(img.width, img.height);
  const w = Math.round(img.width * s), h = Math.round(img.height * s), N = w * h;
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  const g = c.getContext('2d');
  g.drawImage(img, 0, 0, w, h);
  const px = g.getImageData(0, 0, w, h).data;
  const mc = document.createElement('canvas'); mc.width = w; mc.height = h;
  const mg = mc.getContext('2d'); mg.drawImage(maskCanvas, 0, 0, w, h);
  const mp = mg.getImageData(0, 0, w, h).data;
  const LUT = new Float32Array(256).map((_, v) => Math.pow(v / 255, 2.2));
  const m = new Float32Array(N), ch = [0, 1, 2].map(() => new Float32Array(N));
  const rest = [0, 0, 0]; let nr = 0, sl = 0, ns = 0;
  for (let i = 0; i < N; i++) {
    const r = LUT[px[4 * i]], g2 = LUT[px[4 * i + 1]], b = LUT[px[4 * i + 2]];
    const mm = mp[4 * i] / 255; m[i] = mm;
    ch[0][i] = r * mm; ch[1][i] = g2 * mm; ch[2][i] = b * mm;
    if (mp[4 * i + 2] > 128) { sl += 0.2126 * r + 0.7152 * g2 + 0.0722 * b; ns++; }
    if (mm < 0.5 && r + g2 + b > 0.3 && r + g2 + b < 2.7) { rest[0] += r; rest[1] += g2; rest[2] += b; nr++; } // светлые стены
  }
  const masked = rad => {
    const den = boxBlur(m, w, h, rad);
    return ch.map(a => { const b = boxBlur(a, w, h, rad); for (let i = 0; i < N; i++) b[i] /= Math.max(den[i], 1e-3); return b; });
  };
  const SL = masked(14), SM = masked(4);
  // затенение: сколько «не пола» вокруг (стены, мебель)
  const nf = new Float32Array(N); for (let i = 0; i < N; i++) nf[i] = 1 - m[i];
  const aoN = boxBlur(nf, w, h, 3), aoF = boxBlur(nf, w, h, 12);
  // «нормальная» яркость пола — 60-й процентиль (солнечные пятна не тянут всё вниз)
  const ls = [], fl = [0, 0, 0];
  for (let i = 0; i < N; i++) if (m[i] > 0.5) {
    ls.push(0.2126 * SM[0][i] + 0.7152 * SM[1][i] + 0.0722 * SM[2][i]);
    fl[0] += SM[0][i]; fl[1] += SM[1][i]; fl[2] += SM[2][i];
  }
  const n = ls.length;
  ls.sort((a, b) => a - b);
  const meanL = n ? ls[Math.floor(n * 0.6)] : 0.3;
  const meanC = n ? fl.map(v => v / n) : [0.3, 0.3, 0.3];
  // в текстуры: RGB = свет (в sRGB — тени не теряют точность), A = затенение; снизу вверх, как фото
  const pack = (S, ao) => {
    const out = new Uint8Array(N * 4);
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const i = y * w + x, o = ((h - 1 - y) * w + x) * 4;
      for (let k = 0; k < 3; k++) out[o + k] = Math.min(255, Math.round(Math.pow(Math.max(S[k][i], 0), 1 / 2.2) * 255));
      out[o + 3] = Math.round(Math.min(1, ao[i]) * 255);
    }
    const t = new THREE.DataTexture(out, w, h, THREE.RGBAFormat);
    t.colorSpace = THREE.NoColorSpace; t.minFilter = t.magFilter = THREE.LinearFilter; t.needsUpdate = true;
    return t;
  };
  const L = c3 => 0.2126 * c3[0] + 0.7152 * c3[1] + 0.0722 * c3[2];
  const wall = nr ? rest.map(v => v / nr) : [1, 1, 1];
  // Стены бывают крашеные (персиковые, серые), поэтому берём только малую часть их оттенка
  const tint = wall.map(v => Math.min(1.08, Math.max(0.92, 1 + (v / L(wall) - 1) * 0.15)));
  return { bigTex: pack(SL, aoF), medTex: pack(SM, aoN), meanL, meanC, tint, skL: ns ? sl / ns : 0.5 };
}

function tex(src) {
  const t = src instanceof HTMLCanvasElement ? new THREE.CanvasTexture(src) : new THREE.Texture(src);
  t.colorSpace = THREE.NoColorSpace; // перевод в линейный свет делаем в шейдере
  t.minFilter = THREE.LinearFilter; t.generateMipmaps = false;
  t.needsUpdate = true;
  return t;
}

// Показать фото. data — запись из data/photos.json
export function showPhoto(data) {
  return new Promise((ok, fail) => {
    const done = c => {
      cur = c;
      Object.assign(mat.uniforms, {});
      mat.uniforms.photo.value = c.photoTex; mat.uniforms.blurP.value = c.blurTex; mat.uniforms.medP.value = c.medTex;
      mat.uniforms.mask.value = c.maskTex; mat.uniforms.meanL.value = c.meanL; mat.uniforms.skL.value = c.skL;
      mat.uniforms.meanC.value.set(...c.meanC); mat.uniforms.roomTint.value.set(...c.tint);
      updateGeometry(); fitCrop(); render(); placeFurniture().catch(e => console.warn(e)); ok();
    };
    if (cache[data.id] && cache[data.id].skH !== (skirt && skirt.h)) delete cache[data.id]; // другая высота плинтуса
    if (cache[data.id]) return done({ ...cache[data.id], data });
    const img = new Image();
    let left = 2;          // ждём фото и уточнённую маску
    const mk = new Image();
    mk.onload = () => { data._maskImg = mk; ready(); };
    mk.onerror = () => ready(); // маски нет — режем по многоугольникам
    mk.src = (window.PHOTO_BASE || '') + 'data/photos/masks/' + data.id + '.png?v=' + MASK_V;
    const ready = () => { if (--left === 0) build(); };
    img.onload = () => ready();
    const build = () => {
      data.img = data.img || [img.width, img.height];
      const mask = makeMask(data), light = makeLight(img, mask);
      const c = { photoTex: tex(img), blurTex: light.bigTex, medTex: light.medTex, maskTex: tex(mask), meanL: light.meanL,
                  meanC: light.meanC, tint: light.tint, skL: light.skL, img, skH: skirt && skirt.h };
      cache[data.id] = c;
      done({ ...c, data });
    };
    img.onerror = fail;
    img.src = (window.PHOTO_BASE || '') + 'data/photos/' + data.file; // страница разметки лежит в tools/
  });
}

// Пересчитать после правки разметки (страница разметки)
export function refreshPhoto(data) {
  if (!cur) return;
  const c = cache[data.id];
  data._maskImg = null; // разметку правят — режем по многоугольникам
  const mask = makeMask(data), light = makeLight(c.img, mask);
  c.maskTex.dispose(); c.blurTex.dispose(); c.medTex.dispose();
  c.maskTex = tex(mask); c.blurTex = light.bigTex; c.medTex = light.medTex; c.meanL = light.meanL; c.meanC = light.meanC; c.tint = light.tint; c.skL = light.skL;
  mat.uniforms.meanC.value.set(...c.meanC); mat.uniforms.roomTint.value.set(...c.tint);
  cur = { ...c, data };
  mat.uniforms.mask.value = c.maskTex; mat.uniforms.blurP.value = c.blurTex; mat.uniforms.medP.value = c.medTex; mat.uniforms.meanL.value = c.meanL; mat.uniforms.skL.value = c.skL;
  updateGeometry(); render();
}

// Декор на полу: картинка (или нарисованная временная текстура)
// decor (из каталога) — для раскладки досками: размер доски, ряды на фото, фаска
export function setPhotoFloor(image, texWidthM, decor) {
  if (decorTex) decorTex.dispose();
  decorTex = new THREE.Texture(image);
  decorTex.colorSpace = THREE.NoColorSpace;
  decorTex.wrapS = decorTex.wrapT = THREE.RepeatWrapping;
  decorTex.anisotropy = renderer.capabilities.getMaxAnisotropy();
  decorTex.needsUpdate = true;
  const w = texWidthM || DEFAULT_TEX_W_M;
  decorSize = [w, w * image.height / image.width];
  mat.uniforms.decor.value = decorTex;
  mat.uniforms.texM.value.set(...decorSize);
  const boards = decor && !decor.pattern && decor.board_len_mm && decor.board_w_mm;
  mat.uniforms.boardOn.value = boards ? 1 : 0;
  if (boards) {
    const Wb = decor.board_w_mm / 1000;
    mat.uniforms.board.value.set(decor.board_len_mm / 1000, Wb);
    // ряды на фото декора: найденные стыки или (если их не видно) просто по ширине доски
    const r = decor.tex_rows || [0, Math.min(1, Wb / decorSize[1])];
    mat.uniforms.rows.value.set(r[0], r[1]);
    mat.uniforms.bevel.value = decor.chamfer ? 1 : 0;
  }
  // средний цвет декора — для плинтуса «в тон пола»
  const t = document.createElement('canvas'); t.width = t.height = 1;
  const g = t.getContext('2d'); g.drawImage(image, 0, 0, 1, 1);
  decorAvg = [...g.getImageData(0, 0, 1, 1).data].slice(0, 3).map(v => v / 255);
  applySkirt();
  render();
}

// Свет на фото: brightness 0…1, warmth −1 (холодный) … +1 (тёплый)
export function setPhotoLight(b, w) {
  Object.assign(grade, { b, w });
  const night = Math.min(1, Math.max(0, (0.65 - b) / 0.35)); // кнопка «Вечер» (30%) — полная ночь
  mat.uniforms.exposure.value = 0.35 + 0.75 * b;
  const warm = [1.0, 0.86, 0.66], cold = [0.86, 0.93, 1.06];
  const t = w > 0 ? warm : cold, k = Math.abs(w);
  mat.uniforms.tint.value.set(1 + (t[0] - 1) * k, 1 + (t[1] - 1) * k, 1 + (t[2] - 1) * k);
  mat.uniforms.night.value = night;
  render();
}

// Пересчитать размер (если окно было скрыто и ResizeObserver не сработал)
export function resizePhoto() { resize(); }
// Картинка комнаты как на экране — для отправки клиенту (null, если фото не показано)
export function photoBlob() {
  if (!renderer || !cur || !decorTex) return Promise.resolve(null);
  // всё фото целиком, 1600 px по ширине — не зависит от размера экрана телефона
  const [iw, ih] = cur.data.img, w = Math.min(1600, iw);
  renderer.setSize(w, Math.round(w * ih / iw), false);
  mat.uniforms.crop.value.set(0, 0, 1, 1);
  fitFurnCrop();
  render();
  const p = new Promise(res => renderer.domElement.toBlob(res, 'image/jpeg', 0.88)); // кадр снят сразу
  resize();
  return p;
}

export function setGrid(on) { mat.uniforms.showGrid.value = on ? 1 : 0; render(); }

// Плинтус на фото. sk: { color: '#rrggbb' или 'decor' (в тон пола), height_mm } или null — не рисовать
export function setPhotoSkirting(sk) {
  const h = sk ? (sk.height_mm || 70) / 1000 : null;
  skirt = sk ? { color: sk.color || '#f2f0eb', h } : null;
  applySkirt();
  if (cur && cur.skH !== h) showPhoto(cur.data); // высота другая — перестроить маску
  else render();
}

function applySkirt() {
  if (!mat) return;
  mat.uniforms.skOn.value = skirt ? 1 : 0;
  if (!skirt) return;
  let c = decorAvg;
  if (skirt.color !== 'decor') { const n = parseInt(skirt.color.slice(1), 16); c = [n >> 16, (n >> 8) & 255, n & 255].map(v => v / 255); }
  else c = c.map(v => v * 0.92); // плинтус в тон — чуть темнее среднего цвета досок
  mat.uniforms.skCol.value.set(...c.map(v => Math.pow(v, 2.2)));
}
