// 3D-интерьер на three.js: комната, мебель простыми формами, пол из текстуры декора.
import * as THREE from './lib/three.module.min.js';

const ROOM_H = 2.7;            // высота потолка, м
const DEFAULT_TEX_W_M = 1.3;   // сколько метров пола по ширине на фото Материка (если не задано в каталоге)

// Пресет «Гостиная» (SPEC 5.1 C1). Размеры в метрах, x — ширина, z — глубина
export const PRESETS = {
  living: {
    name: 'Гостиная', w: 5, d: 4, wall: 0xe9e4da,
    furniture: [
      // [что, x, z, ширина(x), высота, глубина(z), цвет, подъём] — от центра комнаты
      // Диван вдоль левой стены, смотрит на ТВ у правой части задней стены
      ['диван',       -2.05,  0.2,  0.9,  0.45, 2.2,  0x8a8f96],
      ['спинка',      -2.4,   0.2,  0.2,  0.85, 2.2,  0x8a8f96],
      ['подлокотник', -2.05, -0.8,  0.9,  0.62, 0.2,  0x7d828a],
      ['подлокотник', -2.05,  1.2,  0.9,  0.62, 0.2,  0x7d828a],
      ['ковёр',       -0.8,   0.2,  1.7,  0.01, 2.4,  0xd8d2c6],
      ['столик',      -0.9,   0.2,  0.55, 0.42, 1.0,  0x3b3530],
      ['тумба ТВ',     0.9,  -1.78, 1.8,  0.45, 0.4,  0xf2f0ec],
      ['телевизор',    0.9,  -1.9,  1.25, 0.72, 0.05, 0x1a1a1a, 0.55],
    ],
  },
};

let renderer, scene, camera, floorMat, roomGroup;
const texCache = {};

export function initInterior(canvas) {
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0xf4f2ee);
  camera = new THREE.PerspectiveCamera(55, 1, 0.1, 50);

  // Свет: мягкий общий + «окно» сбоку
  scene.add(new THREE.HemisphereLight(0xffffff, 0xd9d2c5, 1.6));
  const sun = new THREE.DirectionalLight(0xfff4e5, 1.4);
  sun.position.set(-3, 4, 2);
  scene.add(sun);

  floorMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.75 });
  new ResizeObserver(resize).observe(canvas);
  buildRoom(PRESETS.living);
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

function render() { renderer.render(scene, camera); }

// Комната: пол, две дальние стены (ближние не строим — через них смотрит камера), мебель
function buildRoom(p) {
  if (roomGroup) scene.remove(roomGroup);
  roomGroup = new THREE.Group();
  const box = (w, h, d, color) => new THREE.Mesh(new THREE.BoxGeometry(w, h, d),
    new THREE.MeshStandardMaterial({ color, roughness: 0.9 }));

  const floor = new THREE.Mesh(new THREE.PlaneGeometry(p.w, p.d), floorMat);
  floor.rotation.x = -Math.PI / 2;
  roomGroup.add(floor);
  floorMat.userData.size = [p.w, p.d];

  const wallMat = new THREE.MeshStandardMaterial({ color: p.wall, roughness: 1 });
  const back = new THREE.Mesh(new THREE.PlaneGeometry(p.w, ROOM_H), wallMat);
  back.position.set(0, ROOM_H / 2, -p.d / 2);
  const left = new THREE.Mesh(new THREE.PlaneGeometry(p.d, ROOM_H), wallMat);
  left.rotation.y = Math.PI / 2;
  left.position.set(-p.w / 2, ROOM_H / 2, 0);
  roomGroup.add(back, left);

  // Плинтус вдоль двух стен
  const sk = 0xf5f3ef;
  const s1 = box(p.w, 0.07, 0.015, sk); s1.position.set(0, 0.035, -p.d / 2 + 0.008);
  const s2 = box(0.015, 0.07, p.d, sk); s2.position.set(-p.w / 2 + 0.008, 0.035, 0);
  roomGroup.add(s1, s2);

  for (const [, x, z, w, h, d, color, lift = 0] of p.furniture) {
    const m = box(w, h, d, color);
    m.position.set(x, lift + h / 2, z);
    roomGroup.add(m);
  }
  scene.add(roomGroup);

  // Камера из ближнего правого угла, на уровне глаз, смотрит в дальний левый
  camera.position.set(p.w / 2 - 0.2, 1.7, p.d / 2 - 0.2);
  camera.lookAt(-p.w * 0.25, 0.4, -p.d * 0.3);
  render();
}

// Сменить декор на полу. decor.texture — путь к фото; нет фото — временная текстура
export function setFloor(decor) {
  const key = decor.id;
  const apply = tex => {
    const [fw, fd] = floorMat.userData.size;
    const img = tex.image;
    const texW = decor.texture_scale_m || DEFAULT_TEX_W_M;           // м по ширине картинки
    const texH = texW * img.height / img.width;                       // м по высоте картинки
    tex.repeat.set(fw / texW, fd / texH);
    floorMat.map = tex;
    floorMat.needsUpdate = true;
    render();
  };
  if (texCache[key]) return apply(texCache[key]);
  const done = tex => {
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.wrapS = tex.wrapT = THREE.MirroredRepeatWrapping; // зеркальный повтор — меньше видны стыки
    tex.anisotropy = renderer.capabilities.getMaxAnisotropy();
    texCache[key] = tex;
    apply(tex);
  };
  if (decor.texture) new THREE.TextureLoader().load('data/' + decor.texture, done);
  else done(new THREE.CanvasTexture(placeholderWood(decor)));
}

// Заранее загрузить текстуры (первые 10 декоров), чтобы смена была мгновенной
export function preload(decors) {
  for (const d of decors.slice(0, 10)) {
    if (d.texture && !texCache[d.id]) new THREE.TextureLoader().load('data/' + d.texture, t => {
      t.colorSpace = THREE.SRGBColorSpace;
      t.wrapS = t.wrapT = THREE.MirroredRepeatWrapping;
      texCache[d.id] = t;
    });
  }
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
