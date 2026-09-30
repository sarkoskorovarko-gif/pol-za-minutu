// 3D-интерьер на three.js: 5 комнат-пресетов, пол из текстуры декора,
// меняются цвет/обои стен и цвет мебели. Мебель собирается из простых
// скруглённых форм и рисованных текстур — ничего тяжёлого не скачиваем.
import * as THREE from './lib/three.module.min.js';

const ROOM_H = 2.7;            // высота потолка, м
const DEFAULT_TEX_W_M = 1.3;   // сколько метров пола по ширине на фото (если не задано в каталоге)

// ---------- Варианты стен и мебели ----------
export const WALLS = [
  { id: 'milk',   name: 'Молочный',  color: '#efe9df' },
  { id: 'white',  name: 'Белый',     color: '#f6f6f3' },
  { id: 'beige',  name: 'Бежевый',   color: '#e3d5c0' },
  { id: 'grey',   name: 'Серый',     color: '#cfd0cd' },
  { id: 'sage',   name: 'Шалфей',    color: '#c9d1bf' },
  { id: 'blue',   name: 'Голубой',   color: '#c8d5dd' },
  { id: 'terra',  name: 'Терракота', color: '#d9b49c' },
  { id: 'graph',  name: 'Графит',    color: '#6f7274' },
  { id: 'stripe', name: 'Обои: полоска', color: '#e6dccb', pattern: 'stripe' },
  { id: 'leaf',   name: 'Обои: узор',    color: '#dfe3d8', pattern: 'leaf' },
];

export const THEMES = {
  light: { name: 'Светлая', body: '#f1eee8', wood: '#d8c3a0', fabric: '#d9d4cb', accent: '#b9b2a6' },
  wood:  { name: 'Дерево',  body: '#b58a5c', wood: '#9c7148', fabric: '#8c9096', accent: '#6c7076' },
  dark:  { name: 'Тёмная',  body: '#3b3835', wood: '#4a3a2c', fabric: '#56585c', accent: '#2c2d2f' },
};

// ---------- Комнаты: размер по умолчанию и расстановка ----------
// Координаты: левая стена x = -w/2, задняя стена z = -d/2. Камера — в ближнем правом углу.
export const PRESETS = {
  living:  { name: 'Гостиная',       icon: '🛋️', w: 5,   d: 4,   build: buildLiving },
  bedroom: { name: 'Спальня',        icon: '🛏️', w: 4,   d: 3.5, build: buildBedroom },
  kitchen: { name: 'Кухня-столовая', icon: '🍽️', w: 4.5, d: 3.5, build: buildKitchen },
  kids:    { name: 'Детская',        icon: '🧸', w: 3.5, d: 3.2, build: buildKids },
  hall:    { name: 'Прихожая',       icon: '🚪', w: 1.6, d: 4,   build: buildHall },
};

let renderer, scene, camera, sun, floorMat, wallMat, roomGroup;
const view = { type: 'living', w: 5, d: 4, wall: 'milk', theme: 'wood', furniture: true };
const texCache = {};
let mats = {}; // материалы мебели текущей темы

// ================= Запуск и отрисовка =================
export function initInterior(canvas) {
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  scene = new THREE.Scene();
  scene.background = new THREE.Color(0xf4f2ee);
  camera = new THREE.PerspectiveCamera(55, 1, 0.1, 50);

  // Свет: общий мягкий + солнце из окна (даёт тени)
  scene.add(new THREE.HemisphereLight(0xffffff, 0xcfc6b8, 1.5));
  sun = new THREE.DirectionalLight(0xfff1dc, 2.2);
  sun.castShadow = true;
  sun.shadow.mapSize.set(1024, 1024);
  sun.shadow.radius = 4;
  sun.shadow.bias = -0.0005;
  scene.add(sun, sun.target);

  floorMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.6 });
  wallMat = new THREE.MeshStandardMaterial({ roughness: 1 });
  new ResizeObserver(resize).observe(canvas);
  rebuild();
}

function resize() {
  const c = renderer.domElement, w = c.clientWidth, h = c.clientHeight;
  if (!w || !h) return;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.fov = w < h ? 75 : 55; // телефон вертикально — шире обзор
  camera.updateProjectionMatrix();
  render();
}

function render() { if (renderer) renderer.render(scene, camera); }

// ================= Управление снаружи =================
// Сменить комнату. w, d — свои размеры («Моя комната»), иначе типовые
export function setRoom(type, w, d) {
  const p = PRESETS[type];
  Object.assign(view, { type, w: w || p.w, d: d || p.d });
  rebuild();
}
export function setWall(id) { view.wall = id; applyWall(); render(); }
export function setTheme(id) { view.theme = id; rebuild(); }
export function setFurniture(on) { view.furniture = on; rebuild(); }

// Сменить декор на полу. decor.texture — путь к фото; нет фото — временная текстура
export function setFloor(decor) {
  const apply = tex => {
    const img = tex.image;
    const texW = decor.texture_scale_m || DEFAULT_TEX_W_M;   // м по ширине картинки
    const texH = texW * img.height / img.width;               // м по высоте картинки
    floorMat.userData.tex = { tex, texW, texH };
    fitFloorTex();
    floorMat.map = tex;
    floorMat.needsUpdate = true;
    render();
  };
  if (texCache[decor.id]) return apply(texCache[decor.id]);
  const done = tex => { prepTex(tex); texCache[decor.id] = tex; apply(tex); };
  if (decor.texture) new THREE.TextureLoader().load('data/' + decor.texture, done);
  else done(new THREE.CanvasTexture(placeholderWood(decor)));
}

// Заранее загрузить текстуры (первые 10 декоров), чтобы смена была мгновенной
export function preload(decors) {
  for (const d of decors.slice(0, 10)) {
    if (d.texture && !texCache[d.id]) new THREE.TextureLoader().load('data/' + d.texture, t => {
      prepTex(t); texCache[d.id] = t;
    });
  }
}

function prepTex(t) {
  t.colorSpace = THREE.SRGBColorSpace;
  t.wrapS = t.wrapT = THREE.MirroredRepeatWrapping; // зеркальный повтор — меньше видны стыки
  t.anisotropy = renderer.capabilities.getMaxAnisotropy();
}

// Масштаб текстуры пола под размер комнаты — доски реального размера
function fitFloorTex() {
  const t = floorMat.userData.tex;
  if (t) t.tex.repeat.set(view.w / t.texW, view.d / t.texH);
}

// ================= Сборка комнаты =================
function rebuild() {
  if (!scene) return;
  if (roomGroup) scene.remove(roomGroup);
  roomGroup = new THREE.Group();
  const { w, d } = view;
  makeMats(THEMES[view.theme]);

  // Пол
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(w, d), floorMat);
  floor.rotation.x = -Math.PI / 2;
  floor.receiveShadow = true;
  roomGroup.add(floor);
  fitFloorTex();

  // Стены: задняя и левая (ближние не строим — через них смотрит камера)
  const back = new THREE.Mesh(new THREE.PlaneGeometry(w, ROOM_H), wallMat);
  back.position.set(0, ROOM_H / 2, -d / 2);
  const left = new THREE.Mesh(new THREE.PlaneGeometry(d, ROOM_H), wallMat);
  left.rotation.y = Math.PI / 2;
  left.position.set(-w / 2, ROOM_H / 2, 0);
  back.receiveShadow = left.receiveShadow = true;
  roomGroup.add(back, left);
  applyWall();

  // Плинтус
  const skMat = new THREE.MeshStandardMaterial({ color: 0xf7f5f0, roughness: 0.5 });
  add(new THREE.Mesh(new THREE.BoxGeometry(w, 0.07, 0.016), skMat), 0, 0.035, -d / 2 + 0.008);
  add(new THREE.Mesh(new THREE.BoxGeometry(0.016, 0.07, d), skMat), -w / 2 + 0.008, 0.035, 0);

  // Окно на задней стене (кроме прихожей) и солнце через него
  if (view.type !== 'hall' && w >= 2.4) addWindow({ living: -w * 0.12, kitchen: w / 2 - 0.75 }[view.type] ?? w * 0.18, -d / 2);
  sun.position.set(-w / 2 + 0.5, 3.5, -d / 2 - 2);
  sun.target.position.set(0.5, 0, 0.5);
  const s = Math.max(w, d);
  Object.assign(sun.shadow.camera, { left: -s, right: s, top: s, bottom: -s, near: 0.5, far: 15 });
  sun.shadow.camera.updateProjectionMatrix();

  if (view.furniture) PRESETS[view.type].build(w, d);
  scene.add(roomGroup);

  // Камера: ближний правый угол, чуть выше глаз, смотрит в дальний левый
  camera.position.set(w / 2 - 0.2, 1.7, d / 2 - 0.2);
  camera.lookAt(-w * 0.25, 0.4, -d * 0.3);
  render();
}

function applyWall() {
  const v = WALLS.find(x => x.id === view.wall) || WALLS[0];
  wallMat.color.set(v.pattern ? '#ffffff' : v.color);
  wallMat.map = canvasTex(wallCanvas(v), 'wall-' + v.id);
  wallMat.map.repeat.set(3, 2);
  wallMat.needsUpdate = true;
}

// ---------- Помощники для мебели ----------
function add(mesh, x, y, z, rotY = 0) {
  mesh.position.set(x, y, z);
  mesh.rotation.y = rotY;
  mesh.traverse(o => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
  roomGroup.add(mesh);
  return mesh;
}

// Скруглённый брусок: w — по x, h — по y, d — по z, r — радиус скругления
const rboxCache = {};
function rbox(w, h, d, r, mat) {
  const key = [w, h, d, r].join();
  if (!rboxCache[key]) {
    r = Math.min(r, w / 2 - 0.001, h / 2 - 0.001, d / 2 - 0.001);
    const s = new THREE.Shape();
    const x = -w / 2 + r, y = -h / 2 + r, iw = w - 2 * r, ih = h - 2 * r;
    s.moveTo(x, y - r); s.lineTo(x + iw, y - r);
    s.quadraticCurveTo(x + iw + r, y - r, x + iw + r, y);
    s.lineTo(x + iw + r, y + ih); s.quadraticCurveTo(x + iw + r, y + ih + r, x + iw, y + ih + r);
    s.lineTo(x, y + ih + r); s.quadraticCurveTo(x - r, y + ih + r, x - r, y + ih);
    s.lineTo(x - r, y); s.quadraticCurveTo(x - r, y - r, x, y - r);
    const g = new THREE.ExtrudeGeometry(s, { depth: d - 2 * r, bevelEnabled: true, bevelSize: r,
      bevelThickness: r, bevelSegments: 3, curveSegments: 4 });
    g.translate(0, 0, -(d - 2 * r) / 2);
    g.computeVertexNormals();
    rboxCache[key] = g;
  }
  return new THREE.Mesh(rboxCache[key], mat);
}

function box(w, h, d, mat) { return new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat); }

// Группа: собираем предмет из частей, потом ставим целиком
function group(...parts) { const g = new THREE.Group(); parts.forEach(p => g.add(p)); return g; }
function at(mesh, x, y, z) { mesh.position.set(x, y, z); return mesh; }

function legs(w, d, h, mat, inset = 0.06) {
  const g = new THREE.Group();
  for (const sx of [-1, 1]) for (const sz of [-1, 1]) {
    g.add(at(new THREE.Mesh(new THREE.CylinderGeometry(0.018, 0.014, h, 8), mat),
      sx * (w / 2 - inset), h / 2, sz * (d / 2 - inset)));
  }
  return g;
}

function makeMats(t) {
  mats = {
    body:   new THREE.MeshStandardMaterial({ color: t.body, roughness: 0.55, map: canvasTex(noiseCanvas(6), 'n-body') }),
    wood:   new THREE.MeshStandardMaterial({ color: t.wood, roughness: 0.6, map: canvasTex(grainCanvas(), 'grain') }),
    fabric: new THREE.MeshStandardMaterial({ color: t.fabric, roughness: 0.95, map: canvasTex(fabricCanvas(), 'fabric') }),
    accent: new THREE.MeshStandardMaterial({ color: t.accent, roughness: 0.9, map: canvasTex(fabricCanvas(), 'fabric') }),
    white:  new THREE.MeshStandardMaterial({ color: '#f4f2ee', roughness: 0.4 }),
    metal:  new THREE.MeshStandardMaterial({ color: '#8d8f91', roughness: 0.35, metalness: 0.8 }),
    black:  new THREE.MeshStandardMaterial({ color: '#141414', roughness: 0.25 }),
    rug:    new THREE.MeshStandardMaterial({ color: '#d9d2c4', roughness: 1, map: canvasTex(fabricCanvas(), 'fabric') }),
    green:  new THREE.MeshStandardMaterial({ color: '#5d7a4f', roughness: 0.8 }),
    pot:    new THREE.MeshStandardMaterial({ color: '#c9b8a3', roughness: 0.7 }),
    glass:  new THREE.MeshStandardMaterial({ color: '#dfeef7', emissive: '#cfe6f5', emissiveIntensity: 0.9, roughness: 0.1 }),
  };
}

// ---------- Предметы ----------
function sofa(len) {
  const m = mats, D = 0.92;
  return group(
    at(rbox(len, 0.2, D, 0.04, m.fabric), 0, 0.22, 0),                      // основание
    at(rbox(len - 0.3, 0.16, D - 0.2, 0.06, m.fabric), 0, 0.39, 0.08),        // сиденье
    at(rbox(len, 0.5, 0.22, 0.08, m.fabric), 0, 0.57, -D / 2 + 0.11),         // спинка
    at(rbox(len / 2 - 0.2, 0.36, 0.16, 0.07, m.accent), -len / 4 + 0.05, 0.62, -D / 2 + 0.26), // подушки
    at(rbox(len / 2 - 0.2, 0.36, 0.16, 0.07, m.accent), len / 4 - 0.05, 0.62, -D / 2 + 0.26),
    at(rbox(0.16, 0.42, D, 0.06, m.fabric), -len / 2 + 0.08, 0.43, 0),        // подлокотники
    at(rbox(0.16, 0.42, D, 0.06, m.fabric), len / 2 - 0.08, 0.43, 0),
    legs(len, D, 0.12, m.wood, 0.1),
  );
}

function table(w, d, h, top = mats.wood, r = 0.01) {
  return group(at(rbox(w, 0.035, d, r, top), 0, h - 0.018, 0), legs(w, d, h - 0.035, mats.wood));
}

function cabinet(w, h, d, doors, mat = mats.body) {
  const g = group(at(rbox(w, h, d, 0.01, mat), 0, h / 2 + 0.06, 0), legs(w, d, 0.06, mats.metal, 0.05));
  for (let i = 1; i < doors; i++) g.add(at(box(0.004, h - 0.04, 0.004, mats.black), -w / 2 + w * i / doors, h / 2 + 0.06, d / 2));
  for (let i = 0; i < doors; i++) g.add(at(box(0.012, 0.12, 0.02, mats.metal), -w / 2 + w * (i + 0.5) / doors + 0.05, h * 0.6, d / 2 + 0.01));
  return g;
}

function plant(h = 0.9) {
  const g = group(at(new THREE.Mesh(new THREE.CylinderGeometry(0.15, 0.12, 0.3, 16), mats.pot), 0, 0.15, 0));
  for (let i = 0; i < 7; i++) {
    const leaf = new THREE.Mesh(new THREE.SphereGeometry(0.16, 8, 6), mats.green);
    leaf.scale.set(1, 1.6, 0.5);
    leaf.position.set(Math.cos(i) * 0.12, 0.3 + h * 0.4 + (i % 3) * 0.12, Math.sin(i * 1.7) * 0.12);
    leaf.rotation.set(i, i * 2, 0);
    g.add(leaf);
  }
  return g;
}

function rug(w, d) {
  const m = rbox(w, 0.012, d, 0.005, mats.rug);
  m.castShadow = false;
  return m;
}

function bed(w, len) {
  const m = mats;
  return group(
    at(rbox(w, 0.3, len, 0.03, m.fabric), 0, 0.2, 0),                         // основание
    at(rbox(w - 0.06, 0.2, len - 0.08, 0.06, m.white), 0, 0.45, 0.02),        // матрас
    at(rbox(w + 0.04, 0.05, len * 0.6, 0.02, m.accent), 0, 0.57, len * 0.2),  // плед
    at(rbox(w + 0.06, 1.0, 0.1, 0.04, m.fabric), 0, 0.55, -len / 2 - 0.02),   // изголовье
    at(rbox(w / 2 - 0.12, 0.13, 0.4, 0.06, m.white), -w / 4, 0.6, -len / 2 + 0.3), // подушки
    at(rbox(w / 2 - 0.12, 0.13, 0.4, 0.06, m.white), w / 4, 0.6, -len / 2 + 0.3),
    legs(w, len, 0.06, m.wood, 0.05),
  );
}

function lamp() {
  return group(
    at(new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.08, 0.25, 12), mats.pot), 0, 0.12, 0),
    at(new THREE.Mesh(new THREE.CylinderGeometry(0.1, 0.14, 0.18, 16, 1, true), mats.white), 0, 0.33, 0),
  );
}

function chair() {
  const m = mats;
  return group(
    at(rbox(0.44, 0.05, 0.44, 0.02, m.wood), 0, 0.45, 0),
    at(rbox(0.44, 0.4, 0.04, 0.02, m.wood), 0, 0.68, -0.2),
    legs(0.44, 0.44, 0.43, m.wood, 0.04),
  );
}

function shelf(w, h, d) {
  const g = group();
  const m = mats.body;
  g.add(at(box(0.02, h, d, m), -w / 2, h / 2, 0), at(box(0.02, h, d, m), w / 2, h / 2, 0));
  const n = Math.round(h / 0.38);
  for (let i = 0; i <= n; i++) g.add(at(box(w, 0.02, d, m), 0, i * h / n + 0.01, 0));
  // книги/коробки на полках
  const cols = ['#c96f53', '#e2b45c', '#6c93b3', '#8fae7c', '#e8e2d5'];
  for (let i = 0; i < n; i++) for (let j = 0; j < 3; j++) {
    const b = box(0.12 + (j % 2) * 0.1, 0.18 + (j % 3) * 0.04, d * 0.8,
      new THREE.MeshStandardMaterial({ color: cols[(i + j * 2) % 5], roughness: 0.8 }));
    g.add(at(b, -w / 2 + 0.15 + j * (w - 0.3) / 3, i * h / n + 0.12 + (j % 3) * 0.02, 0));
  }
  return g;
}

function tv() {
  return group(at(rbox(1.25, 0.72, 0.04, 0.01, mats.black), 0, 1.2, 0));
}

function addWindow(x, z) {
  const W = 1.3, H = 1.5, y = 1.55;
  const frame = new THREE.MeshStandardMaterial({ color: '#f7f7f5', roughness: 0.4 });
  const glass = new THREE.Mesh(new THREE.PlaneGeometry(W, H), mats.glass || new THREE.MeshBasicMaterial({ color: '#e6f1f8' }));
  roomGroup.add(at(glass, x, y, z + 0.005));
  for (const [w, h, dx, dy] of [[W + 0.1, 0.06, 0, H / 2], [W + 0.1, 0.06, 0, -H / 2], [0.06, H, -W / 2, 0], [0.06, H, W / 2, 0], [0.04, H, 0, 0]])
    roomGroup.add(at(box(w, h, 0.06, frame), x + dx, y + dy, z + 0.03));
  roomGroup.add(at(box(W + 0.2, 0.03, 0.2, frame), x, y - H / 2 - 0.03, z + 0.1)); // подоконник
  // Шторы
  for (const s of [-1, 1]) add(rbox(0.35, 2.3, 0.05, 0.02, mats.accent || frame), x + s * (W / 2 + 0.25), 1.2, z + 0.1);
}

// Поставить, только если помещается (для «Моей комнаты»)
const fits = (need, have) => need <= have;

// ---------- Пресеты ----------
function buildLiving(w, d) {
  const L = w, D = d;
  const sofaLen = Math.min(2.2, D - 0.8);
  if (fits(1.4, D - 0.6)) add(sofa(sofaLen), -L / 2 + 0.5, 0, 0.1, Math.PI / 2);
  add(rug(Math.min(1.8, L - 2), Math.min(2.4, D - 1)), -L / 2 + 1.8, 0.006, 0.1);
  if (fits(2.6, L)) add(table(0.55, 1.0, 0.42), -L / 2 + 1.55, 0, 0.1);
  if (fits(3.4, L)) {
    add(cabinet(1.8, 0.4, 0.4, 3), L / 2 - 1.6, 0, -D / 2 + 0.22);
    add(tv(), L / 2 - 1.6, 0, -D / 2 + 0.05);
  }
  add(plant(), -L / 2 + 0.35, 0, -D / 2 + 0.35);
}

function buildBedroom(w, d) {
  const bw = w >= 3.4 ? 1.6 : 1.4, bl = 2.05;
  const bx = -w / 2 + 0.55 + bw / 2 + (w >= 3.6 ? 0.1 : 0);
  if (fits(bl + 0.6, d)) {
    add(bed(bw, bl), bx, 0, -d / 2 + bl / 2 + 0.08);
    if (fits(bx - bw / 2 + w / 2, 10) && bx - bw / 2 + w / 2 > 0.45) {
      add(cabinet(0.45, 0.45, 0.4, 1), bx - bw / 2 - 0.3, 0, -d / 2 + 0.25);
      add(lamp(), bx - bw / 2 - 0.3, 0.57, -d / 2 + 0.25);
    }
    add(cabinet(0.45, 0.45, 0.4, 1), bx + bw / 2 + 0.3, 0, -d / 2 + 0.25);
    add(lamp(), bx + bw / 2 + 0.3, 0.57, -d / 2 + 0.25);
    add(rug(Math.min(bw + 0.8, w - 0.3), 1.2), bx, 0.006, -d / 2 + bl + 0.1);
  }
  // Шкаф у левой стены, если хватает места по длине
  if (fits(bl + 0.3 + 1.6, d + 0.1)) add(cabinet(1.6, 2.1, 0.6, 3), -w / 2 + 0.32, 0, d / 2 - 1.0, Math.PI / 2);
}

function buildKitchen(w, d) {
  // Гарнитур вдоль задней стены: нижние шкафы, столешница, верхние шкафы
  const kl = Math.min(w - 1.6, 3.2); // справа остаётся место под окно
  const kx = -w / 2 + kl / 2;
  const z = -d / 2 + 0.3;
  add(cabinet(kl, 0.8, 0.58, Math.round(kl / 0.6)), kx, 0, z);
  add(rbox(kl + 0.02, 0.04, 0.62, 0.005, mats.wood), kx, 0.9, z + 0.01);
  add(cabinet(kl, 0.7, 0.34, Math.round(kl / 0.6)), kx, 1.4, -d / 2 + 0.17);
  add(box(0.5, 0.02, 0.4, mats.metal), kx + 0.3, 0.925, z);           // мойка
  add(box(0.6, 0.01, 0.5, mats.black), kx - kl / 2 + 0.6, 0.925, z);  // плита
  // Стол со стульями
  if (fits(2.6, d)) {
    const tx = Math.min(-0.2, w / 2 - 0.9), tz = Math.max(0.3, d / 2 - 1.4);
    add(table(1.2, 0.8, 0.75), tx, 0, tz);
    add(chair(), tx - 0.3, 0, tz - 0.55, 0);
    add(chair(), tx + 0.3, 0, tz - 0.55, 0);
    add(chair(), tx - 0.3, 0, tz + 0.55, Math.PI);
    add(chair(), tx + 0.3, 0, tz + 0.55, Math.PI);
  }
}

function buildKids(w, d) {
  const bl = 1.9, bw = 0.9;
  if (fits(bl + 0.2, d)) add(bed(bw, bl), -w / 2 + bw / 2 + 0.05, 0, -d / 2 + bl / 2 + 0.08);
  if (fits(2.4, w)) {
    add(table(1.0, 0.55, 0.72), w / 2 - 0.9, 0, -d / 2 + 0.3);
    add(chair(), w / 2 - 0.9, 0, -d / 2 + 0.75, Math.PI);
  }
  if (fits(bl + 1.1, d)) add(shelf(0.8, 1.5, 0.3), -w / 2 + 0.17, 0, d / 2 - 0.6, Math.PI / 2);
  // Игровой коврик
  const mat = new THREE.MeshStandardMaterial({ color: '#9cc3d5', roughness: 1, map: canvasTex(noiseCanvas(10), 'n-mat') });
  add(rbox(Math.min(1.4, w - 1.2), 0.015, 1.2, 0.006, mat), 0.2, 0.008, 0.3).castShadow = false;
}

function buildHall(w, d) {
  // Шкаф и обувница вдоль левой стены, зеркало
  if (fits(1.2, w)) {
    add(cabinet(1.2, 2.1, 0.55, 2), -w / 2 + 0.29, 0, -d / 2 + 0.7, Math.PI / 2);
    add(cabinet(0.9, 0.5, 0.32, 2), -w / 2 + 0.17, 0, -d / 2 + 1.9, Math.PI / 2);
    add(rbox(0.5, 0.9, 0.02, 0.01, new THREE.MeshStandardMaterial({ color: '#cfdde3', metalness: 0.2, roughness: 0.08 })),
      -w / 2 + 0.02, 1.45, -d / 2 + 1.9, Math.PI / 2);
  }
  add(rug(Math.min(0.8, w - 0.6), 1.2), 0.1, 0.006, d / 2 - 1.2);
}

// ================= Рисованные текстуры =================
function canvasTex(canvas, key) {
  if (texCache[key]) return texCache[key];
  const t = new THREE.CanvasTexture(canvas);
  t.colorSpace = THREE.SRGBColorSpace;
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  return (texCache[key] = t);
}

function mkCanvas(n = 256) { const c = document.createElement('canvas'); c.width = c.height = n; return c; }

// Лёгкий шум (для крашеных поверхностей)
function noiseCanvas(amp) {
  const c = mkCanvas(), g = c.getContext('2d'), img = g.createImageData(256, 256);
  for (let i = 0; i < img.data.length; i += 4) {
    const v = 245 + (Math.random() - 0.5) * amp;
    img.data[i] = img.data[i + 1] = img.data[i + 2] = v; img.data[i + 3] = 255;
  }
  g.putImageData(img, 0, 0);
  return c;
}

// Ткань: мелкое плетение
function fabricCanvas() {
  const c = noiseCanvas(30), g = c.getContext('2d');
  g.globalAlpha = 0.08;
  for (let i = 0; i < 256; i += 2) { g.fillStyle = i % 4 ? '#000' : '#fff'; g.fillRect(0, i, 256, 1); g.fillRect(i, 0, 1, 256); }
  return c;
}

// Дерево: волокна
function grainCanvas() {
  const c = mkCanvas(), g = c.getContext('2d');
  g.fillStyle = '#f0f0f0'; g.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 60; i++) {
    g.strokeStyle = `rgba(80,50,20,${0.05 + Math.random() * 0.08})`;
    g.lineWidth = 1 + Math.random() * 2;
    const y = Math.random() * 256;
    g.beginPath(); g.moveTo(0, y);
    g.bezierCurveTo(85, y + 6 * Math.random(), 170, y - 6 * Math.random(), 256, y); g.stroke();
  }
  return c;
}

// Стены: однотонная штукатурка или обои с рисунком
function wallCanvas(v) {
  const c = noiseCanvas(v.pattern ? 4 : 8), g = c.getContext('2d');
  if (!v.pattern) return c;
  g.fillStyle = v.color; g.globalAlpha = 1; g.fillRect(0, 0, 256, 256);
  if (v.pattern === 'stripe') {
    g.fillStyle = 'rgba(255,255,255,.45)';
    for (let x = 0; x < 256; x += 64) { g.fillRect(x, 0, 24, 256); g.fillRect(x + 30, 0, 3, 256); }
  } else {
    g.fillStyle = 'rgba(95,120,85,.28)';
    for (let y = 0; y < 256; y += 64) for (let x = 0; x < 256; x += 64) {
      const ox = (y / 64) % 2 ? 32 : 0;
      g.beginPath(); g.ellipse(x + ox + 16, y + 20, 7, 16, 0.6, 0, Math.PI * 2); g.fill();
      g.beginPath(); g.ellipse(x + ox + 28, y + 30, 7, 16, -0.6, 0, Math.PI * 2); g.fill();
    }
  }
  return c;
}

// ВРЕМЕННО: нарисованные доски, пока нет фото. Оттенок — по светлоте декора
function placeholderWood(decor) {
  const c = document.createElement('canvas');
  c.width = 1024; c.height = 620;
  const g = c.getContext('2d');
  const L = decor.lightness ?? 65;
  const rows = 5, rowH = c.height / rows;
  for (let r = 0; r < rows; r++) {
    let x = -((r * 373) % 700);
    while (x < c.width) {
      const len = 700 + (r * 97 % 200);
      const l = L + (Math.random() - 0.5) * 8;
      g.fillStyle = `hsl(32, 30%, ${l}%)`;
      g.fillRect(x, r * rowH, len, rowH);
      for (let i = 0; i < 40; i++) { // прожилки
        g.strokeStyle = `hsla(30, 30%, ${l - 12}%, .25)`;
        g.beginPath();
        const y = r * rowH + Math.random() * rowH;
        g.moveTo(x, y); g.bezierCurveTo(x + len / 3, y + 4, x + len * 2 / 3, y - 4, x + len, y);
        g.stroke();
      }
      g.strokeStyle = 'rgba(0,0,0,.25)';
      g.strokeRect(x, r * rowH, len, rowH);
      x += len;
    }
  }
  return c;
}
