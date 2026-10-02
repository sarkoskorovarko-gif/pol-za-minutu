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
      exposure: { value: 1 }, tint: { value: new THREE.Vector3(1, 1, 1) }, night: { value: 0 },
      showGrid: { value: 0 }, crop: { value: new THREE.Vector4(0, 0, 1, 1) },
    },
    vertexShader: `varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy * 2.0, 0.0, 1.0); }`,
    fragmentShader: `
      precision highp float;
      varying vec2 vUv;
      uniform sampler2D photo, blurP, mask, decor;
      uniform mat3 Hinv; uniform vec2 imgSize, texM; uniform float meanL, rot, exposure, night, showGrid;
      uniform vec3 tint; uniform vec4 crop;
      // sRGB <-> линейный свет (тени и свет умножаем в линейном пространстве)
      vec3 toLin(vec3 c){ return pow(c, vec3(2.2)); }
      vec3 toSrgb(vec3 c){ return pow(max(c, 0.0), vec3(1.0/2.2)); }
      float lum(vec3 c){ return dot(c, vec3(0.2126, 0.7152, 0.0722)); }
      void main(){
        vec2 uv = crop.xy + vUv * crop.zw;              // какая часть фото на экране
        vec2 px = vec2(uv.x, 1.0 - uv.y) * imgSize;      // пиксели фото (y вниз)
        vec3 src = toLin(texture2D(photo, uv).rgb);
        float m = texture2D(mask, uv).r;
        vec3 col = src;
        if (m > 0.001) {
          vec3 f = Hinv * vec3(px, 1.0);
          vec2 fm = f.xy / f.z;                          // точка пола в метрах
          if (rot > 0.5) fm = fm.yx;
          vec3 d = toLin(texture2D(decor, fm / texM).rgb);
          float L = lum(toLin(texture2D(blurP, uv).rgb)) / meanL;  // свет и тень с фото
          vec3 fl = d * min(L, 1.4) + vec3(max(L - 1.4, 0.0) * 0.5); // яркие блики — белые
          if (showGrid > 0.5) {                          // сетка 0,5 м — для разметки
            vec2 g = abs(fract(fm / 0.5 + 0.5) - 0.5) / fwidth(fm / 0.5);
            fl = mix(vec3(1.0, 0.1, 0.1), fl, clamp(min(g.x, g.y), 0.0, 1.0));
          }
          col = mix(src, fl, m);
        }
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
  poly(d.floor, '#fff');
  (d.holes || []).forEach(h => poly(h, '#000'));
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
  let sum = 0, n = 0;
  const lin = v => Math.pow(v / 255, 2.2);
  for (let i = 0; i < px.length; i += 4) if (mp[i] > 128) {
    sum += 0.2126 * lin(px[i]) + 0.7152 * lin(px[i + 1]) + 0.0722 * lin(px[i + 2]); n++;
  }
  return { canvas: c, meanL: n ? sum / n : 0.3 };
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
      mat.uniforms.mask.value = c.maskTex; mat.uniforms.meanL.value = c.meanL;
      updateGeometry(); fitCrop(); render(); ok();
    };
    if (cache[data.id]) return done({ ...cache[data.id], data });
    const img = new Image();
    img.onload = () => {
      data.img = data.img || [img.width, img.height];
      const mask = makeMask(data), light = makeLight(img, mask);
      const c = { photoTex: tex(img), blurTex: tex(light.canvas), maskTex: tex(mask), meanL: light.meanL, img };
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
  c.maskTex = tex(mask); c.blurTex = tex(light.canvas); c.meanL = light.meanL;
  cur = { ...c, data };
  mat.uniforms.mask.value = c.maskTex; mat.uniforms.blurP.value = c.blurTex; mat.uniforms.meanL.value = c.meanL;
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
  render();
}

// Свет на фото: brightness 0…1, warmth −1 (холодный) … +1 (тёплый)
export function setPhotoLight(b, w) {
  Object.assign(grade, { b, w });
  const night = Math.min(1, Math.max(0, (0.6 - b) / 0.45));
  mat.uniforms.exposure.value = 0.35 + 0.75 * b;
  const warm = [1.0, 0.86, 0.66], cold = [0.86, 0.93, 1.06];
  const t = w > 0 ? warm : cold, k = Math.abs(w);
  mat.uniforms.tint.value.set(1 + (t[0] - 1) * k, 1 + (t[1] - 1) * k, 1 + (t[2] - 1) * k);
  mat.uniforms.night.value = night;
  render();
}

export function setGrid(on) { mat.uniforms.showGrid.value = on ? 1 : 0; render(); }
export function getCrop() { return mat.uniforms.crop.value; }
