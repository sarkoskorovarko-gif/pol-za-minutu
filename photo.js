// Фото-интерьеры: на настоящую фотографию комнаты подставляется выбранный ламинат.
// Как это работает:
//  1) По 4 точкам на полу (углы прямоугольника W×D метров) считаем перспективу —
//     для каждой точки фото знаем, какое место пола туда попадает (в метрах).
//  2) Маска пола (контур минус мебель) говорит, где менять пол, а где оставить фото.
//  3) Свет и тени берём с исходного фото: размытая яркость пола / средняя яркость пола.
import * as THREE from 'three';

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
      photo: { value: null }, blurP: { value: null }, mask: { value: null }, decor: { value: null },
      Hinv: { value: new THREE.Matrix3() }, imgSize: { value: new THREE.Vector2(1, 1) },
      texM: { value: new THREE.Vector2(1.3, 0.8) }, meanL: { value: 0.5 }, rot: { value: 0 },
      meanC: { value: new THREE.Vector3(0.3, 0.3, 0.3) }, roomTint: { value: new THREE.Vector3(1, 1, 1) },
      lampFloor: { value: new THREE.Vector2(1.5, 1.5) }, hasLamp: { value: 0 },
      exposure: { value: 1 }, tint: { value: new THREE.Vector3(1, 1, 1) }, night: { value: 0 },
      skCol: { value: new THREE.Vector3(1, 1, 1) }, skOn: { value: 0 }, skL: { value: 0.5 },
      showGrid: { value: 0 }, crop: { value: new THREE.Vector4(0, 0, 1, 1) },
    },
    vertexShader: `varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy * 2.0, 0.0, 1.0); }`,
    fragmentShader: `
      precision highp float;
      varying vec2 vUv;
      uniform sampler2D photo, blurP, mask, decor;
      uniform mat3 Hinv; uniform vec2 imgSize, texM; uniform float meanL, rot, exposure, night, showGrid;
      uniform vec3 tint, meanC, roomTint; uniform vec4 crop; uniform vec2 lampFloor; uniform float hasLamp;
      uniform vec3 skCol; uniform float skOn, skL;
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
        vec3 col = src;
        if (m > 0.001) {
          vec3 f = Hinv * vec3(px, 1.0);
          vec2 fm = f.xy / f.z;                          // точка пола в метрах
          float r = length(fm - lampFloor);              // расстояние до точки под люстрой
          if (rot > 0.5) fm = fm.yx;
          vec3 d = toLin(texture2D(decor, fm / texM).rgb);
          // Свет с фото: размытый цвет пола / средний цвет пола — где светлее, где тень,
          // где тёплое солнечное пятно. Плюс общий оттенок света в комнате (по стенам).
          vec3 B = toLin(texture2D(blurP, uv).rgb);
          vec3 sh = B / max(meanC, vec3(0.001));
          float L = lum(B) / meanL;
          vec3 dayLight = mix(vec3(L), sh, 0.25) * roomTint;
          // Вечер: дневной рисунок света (солнце, блики окон) убираем совсем.
          // Остаются только мягкие тени (где на фото темнее среднего), светит люстра.
          // тенью считаем только заметно тёмные места (у мебели, в углах);
          // всё, что светлее, — ровный пол, чтобы дневные блики не проступали пятнами
          float ao = mix(0.55, 1.0, smoothstep(0.2, 0.7, L));
          // Свет люстры: мягкий спад к углам, без яркого пятна
          float lampL = hasLamp > 0.5 ? 0.45 + 0.75 / (1.0 + r * r / 6.0) : 0.9;
          vec3 nightLight = vec3(ao * lampL);
          vec3 light = mix(dayLight, nightLight, night);
          vec3 fl = d * min(light, vec3(1.4));
          fl += vec3(max(L - 1.4, 0.0) * 0.5) * (1.0 - night); // блики от окон днём
          fl += vec3(0.06 * exp(-r * r / 0.5)) * night * ao * hasLamp; // отражение люстры — только если она отмечена
          if (showGrid > 0.5) {                          // сетка 0,5 м — для разметки
            vec2 g = abs(fract(fm / 0.5 + 0.5) - 0.5) / fwidth(fm / 0.5);
            fl = mix(vec3(1.0, 0.1, 0.1), fl, clamp(min(g.x, g.y), 0.0, 1.0));
          }
          col = mix(src, fl, m);
        }
        // Плинтус: синий канал маски — полоса над линией пола у стен.
        // Свет берём с фото (где старый плинтус в тени — новый тоже), ночью — как пол.
        float sk = mk.b * skOn;
        if (sk > 0.001) {
          float Ls = lum(toLin(texture2D(blurP, uv).rgb)) / skL;
          float lt = mix(clamp(Ls, 0.35, 1.3), 0.8, night * 0.6);
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
}

export function render() { if (renderer && cur && decorTex) renderer.render(scene, camera); }

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
  const [iw, ih] = d.img, s = 1024 / Math.max(iw, ih);
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
  poly(d.floor, '#f00');
  (d.holes || []).forEach(h => poly(h, '#000'));
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

function makeLight(img, maskCanvas) {
  // Размытая копия фото: исчезает рисунок старых досок, остаются свет и тени
  const s = 512 / Math.max(img.width, img.height);
  const c = document.createElement('canvas');
  c.width = Math.round(img.width * s); c.height = Math.round(img.height * s);
  const g = c.getContext('2d');
  g.filter = 'blur(5px)';
  g.drawImage(img, 0, 0, c.width, c.height);
  // Средняя яркость пола (по маске) — «нормальный» свет
  const px = g.getImageData(0, 0, c.width, c.height).data;
  const mc = document.createElement('canvas'); mc.width = c.width; mc.height = c.height;
  const mg = mc.getContext('2d'); mg.drawImage(maskCanvas, 0, 0, c.width, c.height);
  const mp = mg.getImageData(0, 0, c.width, c.height).data;
  const lin = v => Math.pow(v / 255, 2.2);
  const fl = [0, 0, 0], rest = [0, 0, 0];
  let n = 0, nr = 0, sl = 0, ns = 0;
  for (let i = 0; i < px.length; i += 4) {
    const r = lin(px[i]), g2 = lin(px[i + 1]), b = lin(px[i + 2]);
    if (mp[i + 2] > 128) { sl += 0.2126 * r + 0.7152 * g2 + 0.0722 * b; ns++; }
    if (mp[i] > 128) { fl[0] += r; fl[1] += g2; fl[2] += b; n++; }
    else if (r + g2 + b > 0.3 && r + g2 + b < 2.7) { rest[0] += r; rest[1] += g2; rest[2] += b; nr++; } // светлые стены, без окон
  }
  const meanC = n ? fl.map(v => v / n) : [0.3, 0.3, 0.3];
  const L = c3 => 0.2126 * c3[0] + 0.7152 * c3[1] + 0.0722 * c3[2];
  const wall = nr ? rest.map(v => v / nr) : [1, 1, 1];
  // Стены бывают крашеные (персиковые, серые), поэтому берём только малую часть их оттенка
  const tint = wall.map(v => Math.min(1.08, Math.max(0.92, 1 + (v / L(wall) - 1) * 0.15)));
  return { canvas: c, meanL: L(meanC), meanC, tint, skL: ns ? sl / ns : 0.5 };
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
      mat.uniforms.photo.value = c.photoTex; mat.uniforms.blurP.value = c.blurTex;
      mat.uniforms.mask.value = c.maskTex; mat.uniforms.meanL.value = c.meanL; mat.uniforms.skL.value = c.skL;
      mat.uniforms.meanC.value.set(...c.meanC); mat.uniforms.roomTint.value.set(...c.tint);
      updateGeometry(); fitCrop(); render(); ok();
    };
    if (cache[data.id] && cache[data.id].skH !== (skirt && skirt.h)) delete cache[data.id]; // другая высота плинтуса
    if (cache[data.id]) return done({ ...cache[data.id], data });
    const img = new Image();
    img.onload = () => {
      data.img = data.img || [img.width, img.height];
      const mask = makeMask(data), light = makeLight(img, mask);
      const c = { photoTex: tex(img), blurTex: tex(light.canvas), maskTex: tex(mask), meanL: light.meanL,
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
  const mask = makeMask(data), light = makeLight(c.img, mask);
  c.maskTex.dispose(); c.blurTex.dispose();
  c.maskTex = tex(mask); c.blurTex = tex(light.canvas); c.meanL = light.meanL; c.meanC = light.meanC; c.tint = light.tint; c.skL = light.skL;
  mat.uniforms.meanC.value.set(...c.meanC); mat.uniforms.roomTint.value.set(...c.tint);
  cur = { ...c, data };
  mat.uniforms.mask.value = c.maskTex; mat.uniforms.blurP.value = c.blurTex; mat.uniforms.meanL.value = c.meanL; mat.uniforms.skL.value = c.skL;
  updateGeometry(); render();
}

// Декор на полу: картинка (или нарисованная временная текстура)
export function setPhotoFloor(image, texWidthM) {
  if (decorTex) decorTex.dispose();
  decorTex = new THREE.Texture(image);
  decorTex.colorSpace = THREE.NoColorSpace;
  decorTex.wrapS = decorTex.wrapT = THREE.MirroredRepeatWrapping;
  decorTex.anisotropy = renderer.capabilities.getMaxAnisotropy();
  decorTex.needsUpdate = true;
  const w = texWidthM || DEFAULT_TEX_W_M;
  decorSize = [w, w * image.height / image.width];
  mat.uniforms.decor.value = decorTex;
  mat.uniforms.texM.value.set(...decorSize);
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

export function setGrid(on) { mat.uniforms.showGrid.value = on ? 1 : 0; render(); }
export function getCrop() { return mat.uniforms.crop.value; }

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
