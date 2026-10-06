// Мебель для фото-комнат: готовые наборы («Гостиная», «Спальня», «Столовая»).
// Современная мебель простой формы собирается здесь из скруглённых блоков с настоящими
// текстурами ткани и дерева (Poly Haven, CC0); кресла, столик и растение — готовые модели.
// Координаты набора: u — вправо (как видно с камеры), v — от дальней стены к камере, метры.
// Лицевая сторона каждого предмета смотрит на +v (к камере); rot — поворот, градусы.
import * as THREE from 'three';
import { RoundedBoxGeometry } from './lib/jsm/geometries/RoundedBoxGeometry.js';

export const PRESETS = {
  'Гостиная': [
    { m: 'sofa', u: 0, v: 0.5 },
    { m: 'coffee_table_round_01', u: 0, v: 1.55 },
    { m: 'modern_arm_chair_01', u: 1.5, v: 1.45, rot: -65 },
    { m: 'potted_plant_04', u: -1.45, v: 0.35 },
  ],
  'Спальня': [
    { m: 'bed', u: 0, v: 1.08 },
    { m: 'nightstand', u: -1.15, v: 0.25 },
    { m: 'nightstand', u: 1.15, v: 0.25 },
    { m: 'potted_plant_04', u: 1.75, v: 0.3 },
  ],
  'Столовая': [
    { m: 'dining_table', u: 0, v: 1.35 },
    { m: 'dining_chair', u: -0.42, v: 0.82 },
    { m: 'dining_chair', u: 0.42, v: 0.82 },
    { m: 'dining_chair', u: -0.42, v: 1.88, rot: 180 },
    { m: 'dining_chair', u: 0.42, v: 1.88, rot: 180 },
    { m: 'sideboard', u: 0, v: 0.24 },
    { m: 'potted_plant_04', u: 1.35, v: 0.3 },
  ],
};

// ---------- Материалы ----------
const base = () => (window.PHOTO_BASE || '') + 'data/furniture/tex/';
const loader = new THREE.TextureLoader();
const texCache = {};
function tx(name, srgb, rep) {
  const key = name + rep;
  if (!texCache[key]) {
    const t = loader.load(base() + name + '.jpg');
    t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(rep, rep);
    t.colorSpace = srgb ? THREE.SRGBColorSpace : THREE.NoColorSpace;
    texCache[key] = t;
  }
  return texCache[key];
}
const matCache = {};
function mat(kind) {
  if (matCache[kind]) return matCache[kind];
  const M = (tex, rep, color, rough, extra = {}) => new THREE.MeshStandardMaterial({
    map: tx(tex + '_diff', true, rep), normalMap: tx(tex + '_nor', false, rep),
    normalScale: new THREE.Vector2(0.6, 0.6), color, roughness: rough, ...extra });
  const m = {
    linenGrey: () => M('rough_linen', 2, 0xa8a49d, 0.95),       // диван
    linenWhite: () => M('rough_linen', 2, 0xf2f0ea, 0.95),      // постель
    linenSand: () => M('rough_linen', 2, 0xcdbfa8, 0.95),       // покрывало
    boucle: () => M('rough_linen', 3, 0xd9d2c4, 1.0),           // изголовье, стулья (светлая ткань)
    oak: () => M('oak_veneer_01', 1, 0xffffff, 0.6),
    walnut: () => M('walnut_veneer', 1, 0xffffff, 0.55),
    black: () => new THREE.MeshStandardMaterial({ color: 0x1c1c1c, roughness: 0.5, metalness: 0.4 }),
  }[kind]();
  return (matCache[kind] = m);
}

// Скруглённый блок: размеры w×h×d, центр низа в (x, y, z)
function blk(g, w, h, d, x, y, z, material, r = 0.02) {
  const rr = Math.min(r, w / 2 - 0.001, h / 2 - 0.001, d / 2 - 0.001);
  const m = new THREE.Mesh(new RoundedBoxGeometry(w, h, d, 3, rr), material);
  m.position.set(x, y + h / 2, z);
  g.add(m);
  return m;
}
function legs(g, w, d, h, inset, material, t = 0.035) {
  for (const sx of [-1, 1]) for (const sz of [-1, 1])
    blk(g, t, h, t, sx * (w / 2 - inset), 0, sz * (d / 2 - inset), material, 0.006);
}

// ---------- Предметы ----------
const BUILD = {
  sofa() {                                   // современный диван 2,1 м, ткань, ножки орех
    const g = new THREE.Group(), W = 2.1, D = 0.92, L = 0.1, f = mat('linenGrey');
    legs(g, W - 0.1, D - 0.1, L, 0.06, mat('walnut'), 0.04);
    blk(g, W, 0.24, D, 0, L, 0, f, 0.04);                                        // основание
    for (const s of [-1, 1]) blk(g, (W - 0.36) / 2 - 0.01, 0.16, D - 0.26, s * (W - 0.36) / 4 + s * 0.005, L + 0.24, 0.09, f, 0.06); // сиденья
    for (const s of [-1, 1]) blk(g, 0.17, 0.36, D, s * (W / 2 - 0.085), L + 0.12, 0, f, 0.06);  // подлокотники
    blk(g, W - 0.36, 0.42, 0.24, 0, L + 0.22, -D / 2 + 0.14, f, 0.08);           // спинка
    return g;
  },
  bed() {                                    // кровать 160×200, мягкое изголовье
    const g = new THREE.Group(), W = 1.6, Lg = 2.05;
    blk(g, W + 0.1, 0.3, Lg, 0, 0.05, 0, mat('boucle'), 0.05);                  // каркас
    blk(g, W + 0.06, 0.05, Lg - 0.1, 0, 0, 0, mat('black'), 0.01);               // цоколь (тень)
    blk(g, W, 0.2, Lg - 0.1, 0, 0.35, 0.02, mat('linenWhite'), 0.06);            // матрас
    blk(g, W + 0.06, 0.07, Lg * 0.62, 0, 0.53, Lg / 2 - Lg * 0.31 + 0.02, mat('linenSand'), 0.04); // покрывало
    for (const s of [-1, 1]) blk(g, 0.62, 0.15, 0.4, s * 0.38, 0.55, -Lg / 2 + 0.36, mat('linenWhite'), 0.07); // подушки
    blk(g, W + 0.16, 1.05, 0.1, 0, 0.05, -Lg / 2 - 0.02, mat('boucle'), 0.05);  // изголовье
    return g;
  },
  nightstand() {                             // тумбочка дуб
    const g = new THREE.Group();
    legs(g, 0.46, 0.38, 0.14, 0.04, mat('walnut'), 0.03);
    blk(g, 0.5, 0.4, 0.4, 0, 0.14, 0, mat('oak'), 0.015);
    blk(g, 0.42, 0.006, 0.01, 0, 0.34, 0.2, mat('black'), 0.002);                // щель ящика
    return g;
  },
  dining_table() {                           // стол 160×90 дуб
    const g = new THREE.Group();
    legs(g, 1.6, 0.9, 0.72, 0.1, mat('oak'), 0.05);
    blk(g, 1.6, 0.035, 0.9, 0, 0.72, 0, mat('oak'), 0.008);
    return g;
  },
  dining_chair() {                           // стул: дубовые ножки, сиденье и спинка букле
    const g = new THREE.Group(), S = 0.46;
    legs(g, S - 0.02, S - 0.04, 0.44, 0.03, mat('oak'), 0.03);
    blk(g, S, 0.06, S, 0, 0.42, 0, mat('boucle'), 0.025);
    blk(g, S - 0.02, 0.4, 0.06, 0, 0.46, -S / 2 + 0.04, mat('boucle'), 0.03);
    return g;
  },
  sideboard() {                              // комод/тумба орех 1,6 м
    const g = new THREE.Group();
    legs(g, 1.5, 0.4, 0.16, 0.06, mat('black'), 0.025);
    blk(g, 1.6, 0.56, 0.44, 0, 0.16, 0, mat('walnut'), 0.012);
    for (const x of [-0.4, 0, 0.4]) blk(g, 0.006, 0.5, 0.01, x, 0.19, 0.22, mat('black'), 0.002); // стыки дверок
    return g;
  },
};

export function isBuilt(m) { return !!BUILD[m]; }
export function build(m) {
  const g = BUILD[m]();
  g.traverse(o => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
  return g;
}
