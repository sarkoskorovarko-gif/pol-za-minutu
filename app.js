// Главный файл интерфейса. Формулы расчёта — в calc.js, 3D — в interior.js.
import { initInterior, setFloor, preload, setRoom, setWall, setTheme, setFurniture, setLight,
         setWindow, getWindow, placeholderWood, PRESETS, WALLS, THEMES } from './interior.js?v=9';
import { initPhoto, showPhoto, setPhotoFloor, setPhotoLight } from './photo.js?v=9';

const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const rub = x => x.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

const NAMES = { laminate: 'Ламинат', underlay: 'Подложка', skirting: 'Плинтус',
                corners: 'Уголки внутренние', caps: 'Заглушки' };
const COLOR_GROUPS = ['светлый', 'бежевый', 'серый', 'коричневый', 'тёмный'];
const BADGES = { hit: 'Хит', sale: 'Акция', new: 'Новинка' };

// ================= Хранилище (localStorage, всегда в try/catch) =================
const store = {
  get(k, def) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : def; } catch (e) { return def; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} },
};

// Настройки промоутера. При пустом хранилище — значения по умолчанию
const DEFAULTS = {
  pin: null,
  decors: {},            // id → { off, badge, price }
  order: [],             // порядок id (популярные первыми)
  hideOut: true,         // скрывать то, чего нет в наличии
  defaultDecor: null,
  defaultRoom: null,      // null — первое фото
  underlay: null, skirting: null,
  waste: { straight: 7, diagonal: 15 }, // %
  name: '', phone: '',
};
let S = { ...DEFAULTS, ...store.get('settings', {}) };
const saveSettings = () => store.set('settings', S);
let LOG = store.get('log', []); // журнал расчётов: { t, n, d, a, s, b }
const saveLog = () => store.set('log', LOG);

// ================= Состояние экрана =================
let catalog = null;
const state = {
  rooms: [{ length: '', width: '', doors: 1, diagonal: false, type: 'living' }],
  use: { underlay: true, skirting: true, accessories: true },
  decorId: null,
  number: calcNumber(),
  shared: false,       // после отправки следующее изменение получает новый номер
  view: 'living',      // пресет или 'my'
  myRoom: 0,           // какая комната расчёта показана в «Моей комнате»
  filter: { color: null, cls: null, water: false },
};

// Режим просмотра по ссылке (для покупателя)
const params = new URLSearchParams(location.search);
const VIEWER = params.has('d');

// ================= Декоры: видимые, порядок, цены =================
function decorPrice(d) {
  const p = parseNum(S.decors[d.id]?.price);
  return p > 0 ? p : d.price_m2;
}
// Все декоры, которые промоутер не выключил, в его порядке
function enabledDecors() {
  const list = catalog.decors.filter(d => !S.decors[d.id]?.off && !(S.hideOut && !d.in_stock));
  const pos = id => { const i = S.order.indexOf(id); return i < 0 ? 1e6 + catalog.decors.findIndex(d => d.id === id) : i; };
  return list.sort((a, b) => pos(a.id) - pos(b.id));
}
// С учётом фильтров покупателя
function visibleDecors() {
  const f = state.filter;
  return enabledDecors().filter(d =>
    (!f.color || d.color_group === f.color) && (!f.cls || d.class === f.cls) && (!f.water || d.water_resistant));
}
const current = () => catalog.decors.find(d => d.id === state.decorId);

// Светлота/теплота: из каталога; если текстуры ещё нет — примерно по группе цвета
const L_BY_GROUP = { 'светлый': 78, 'бежевый': 66, 'серый': 60, 'коричневый': 45, 'тёмный': 30 };
const lightness = d => d.lightness ?? L_BY_GROUP[d.color_group] ?? 55;
const warmth = d => d.warmth ?? (d.color_group === 'серый' ? 0 : 10);

// ================= Выбор декора =================
function pickDecor(id) {
  state.decorId = id;
  const d = current();
  if (!d) return;
  setFloor(d);
  photoFloor(d);
  $('#decorName').textContent = d.name;
  $('#decorInfo').textContent = `${d.id} · ${rub(decorPrice(d))} руб/м² · класс ${d.class ?? '—'}`
    + (d.in_stock ? '' : ' · нет в наличии') + (d.texture ? '' : ' · фото декора пока нет');
  $$('#ribbon .tile').forEach(t => t.classList.toggle('on', t.dataset.id === id));
  $('#ribbon .tile.on')?.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' });
  renderNeighbours();
  syncSliders();
  changed();
}

// Лента декоров
function renderRibbon() {
  const list = visibleDecors();
  $('#ribbon').innerHTML = list.length ? '' : '<p class="muted small">Нет декоров под этот фильтр</p>';
  for (const d of list) {
    const t = document.createElement('button');
    t.className = 'tile';
    t.dataset.id = d.id;
    const badge = BADGES[S.decors[d.id]?.badge];
    t.innerHTML = `<span class="sw" style="${swatchStyle(d)}"></span>`
      + (badge ? `<span class="badge b-${S.decors[d.id].badge}">${badge}</span>` : '')
      + `<span class="tn">${esc(d.name)}</span><span class="tp">${rub(decorPrice(d))}</span>`;
    t.onclick = () => pickDecor(d.id);
    $('#ribbon').appendChild(t);
  }
  if (!list.some(d => d.id === state.decorId) && list.length) pickDecor(list[0].id);
  else pickDecor(state.decorId);
}

function swatchStyle(d) {
  if (d.texture) return `background-image:url('data/${d.texture}')`;
  return `background:hsl(32,30%,${lightness(d)}%)`;
}

// Соседи по тону: чуть светлее слева, чуть темнее справа
function byLightness() { return visibleDecors().sort((a, b) => lightness(b) - lightness(a)); }
function renderNeighbours() {
  const list = byLightness(), i = list.findIndex(d => d.id === state.decorId);
  const set = (btn, d, arrow) => {
    btn.disabled = !d;
    btn.innerHTML = d ? `<span class="sw" style="${swatchStyle(d)}"></span>${arrow}` : '';
    btn.onclick = d ? () => pickDecor(d.id) : null;
  };
  set($('#lighter'), list[i - 1], '◀');
  set($('#darker'), list[i + 1], '▶');
}

// Ползунки «светлее/темнее», «теплее/холоднее» — прилипают к реальным декорам
function sliderList(kind) {
  const list = visibleDecors();
  return kind === 'L' ? list.sort((a, b) => lightness(b) - lightness(a))
                      : list.sort((a, b) => warmth(b) - warmth(a));
}
function syncSliders() {
  for (const k of ['L', 'W']) {
    const list = sliderList(k), el = $('#sl' + k);
    el.max = Math.max(0, list.length - 1);
    el.value = Math.max(0, list.findIndex(d => d.id === state.decorId));
    el.disabled = list.length < 2;
  }
}
for (const k of ['L', 'W']) {
  $('#sl' + k).oninput = e => {
    const d = sliderList(k)[+e.target.value];
    if (d && d.id !== state.decorId) pickDecor(d.id);
  };
}

// Фильтры
function renderFilters() {
  const chips = (box, items, key, label) => {
    box.innerHTML = '';
    for (const v of [null, ...items]) {
      const b = document.createElement('button');
      b.className = 'chip' + (state.filter[key] === v ? ' on' : '');
      b.textContent = v === null ? 'Все' : label(v);
      b.onclick = () => { state.filter[key] = v; renderFilters(); renderRibbon(); };
      box.appendChild(b);
    }
  };
  const en = enabledDecors();
  chips($('#colorFilter'), COLOR_GROUPS.filter(g => en.some(d => d.color_group === g)), 'color', v => v);
  chips($('#classFilter'), [...new Set(en.map(d => d.class).filter(Boolean))].sort(), 'cls', v => 'Класс ' + v);
}
$('#waterOnly').onchange = e => { state.filter.water = e.target.checked; renderRibbon(); };

// ================= Комнаты (размеры) =================
function renderRooms() {
  const box = $('#rooms');
  box.innerHTML = '';
  state.rooms.forEach((r, i) => {
    const el = $('#roomTpl').content.firstElementChild.cloneNode(true);
    el.querySelector('.room-title').textContent = 'Комната ' + (i + 1);
    el.querySelector('.del').hidden = state.rooms.length === 1 || VIEWER;
    const sel = el.querySelector('.rtype');
    sel.innerHTML = Object.entries(PRESETS).map(([k, p]) => `<option value="${k}">${p.name}</option>`).join('');
    sel.value = r.type;
    sel.onchange = () => { r.type = sel.value; if (state.view === 'my') showMyRoom(i); changed(); };
    const len = el.querySelector('.len'), wid = el.querySelector('.wid');
    len.value = r.length; wid.value = r.width;
    len.oninput = () => { r.length = len.value; changed(); };
    wid.oninput = () => { r.width = wid.value; changed(); };
    el.querySelector('.doors').textContent = r.doors;
    el.querySelector('.minus').onclick = () => { r.doors = Math.max(0, r.doors - 1); renderRooms(); };
    el.querySelector('.plus').onclick = () => { r.doors = Math.min(9, r.doors + 1); renderRooms(); };
    el.querySelectorAll('.lay').forEach(b => {
      b.classList.toggle('on', (b.dataset.d === '1') === r.diagonal);
      b.onclick = () => { r.diagonal = b.dataset.d === '1'; renderRooms(); };
    });
    el.querySelector('.del').onclick = () => {
      state.rooms.splice(i, 1);
      state.myRoom = Math.min(state.myRoom, state.rooms.length - 1);
      renderRooms();
    };
    if (VIEWER) el.querySelectorAll('input, button, select').forEach(x => x.disabled = true);
    box.appendChild(el);
  });
  changed();
}

function roomNums(r) {
  const l = parseNum(r.length), w = parseNum(r.width);
  if (!(l > 0 && l < 100 && w > 0 && w < 100)) return null;
  return { length: l, width: w, doors: r.doors, diagonal: r.diagonal };
}

$('#addRoom').onclick = () => {
  state.rooms.push({ length: '', width: '', doors: 1, diagonal: false, type: 'bedroom' });
  renderRooms();
  $$('.len')[state.rooms.length - 1].focus();
};

// ================= Интерьер: пресеты и «Моя комната» =================
function renderRoomNav() {
  const nav = $('#roomsNav');
  nav.innerHTML = '';
  const items = [...PHOTOS.map(p => ['photo:' + p.id, '', p.title, p.file]),
    ...Object.entries(PRESETS).map(([k, p]) => [k, p.icon, p.name + ' 3D']), ['my', '📐', 'Моя комната']];
  for (const [k, icon, name, file] of items) {
    const b = document.createElement('button');
    b.innerHTML = file ? `<img src="data/photos/thumbs/${file}" alt="">${name}` : `<span>${icon}</span>${name}`;
    if (file) b.classList.add('ph');
    b.classList.toggle('on', state.view === k);
    b.onclick = () => { state.view = k; renderRoomNav(); showView(); };
    nav.appendChild(b);
  }
}

// Показать выбранную комнату: фото или 3D
function showView() {
  const k = state.view, isPhoto = k.startsWith('photo:');
  document.body.classList.toggle('photo-mode', isPhoto);
  $('#scene').hidden = isPhoto;
  $('#photoView').hidden = !isPhoto;
  $('#myBar').hidden = k !== 'my';
  if (isPhoto) {
    const p = PHOTOS.find(x => 'photo:' + x.id === k);
    if (!photoReady) { initPhoto($('#photoView')); photoReady = true; applyLight(); }
    if (current()) photoFloor(current());
    showPhoto(p).catch(() => toast('Не удалось загрузить фото'));
  } else if (k === 'my') showMyRoom(state.myRoom);
  else setRoom(k);
  syncWindowUI();
}

// Пол на фото: фото декора с Материка или временная нарисованная текстура
let photoReady = false;
const decorImg = {};
function photoFloor(d) {
  if (!photoReady) return;
  if (decorImg[d.id]) return setPhotoFloor(decorImg[d.id], d.texture_scale_m);
  if (d.texture) {
    const img = new Image();
    img.onload = () => { decorImg[d.id] = img; if (state.decorId === d.id) setPhotoFloor(img, d.texture_scale_m); };
    img.src = 'data/' + d.texture;
  } else {
    // Фото декора ещё нет — временно демо-ламинат (Poly Haven, CC0), чтобы было видно качество
    const img = new Image();
    img.onload = () => { decorImg[d.id] = img; if (state.decorId === d.id) setPhotoFloor(img, 1.6); };
    img.src = 'data/demo/laminate_floor_02.jpg';
  }
}

// Комната из расчёта: тип и размеры клиента
function showMyRoom(i) {
  state.myRoom = i;
  const r = state.rooms[i], n = roomNums(r);
  setRoom(r.type, n?.length, n?.width);
  $('#myBar').hidden = false;
  $('#myRooms').innerHTML = '';
  state.rooms.forEach((room, j) => {
    const b = document.createElement('button');
    const nn = roomNums(room);
    b.className = 'chip' + (j === i ? ' on' : '');
    b.textContent = `${j + 1}. ${PRESETS[room.type].name}` + (nn ? ` ${nn.length}×${nn.width}` : '');
    b.onclick = () => showMyRoom(j);
    $('#myRooms').appendChild(b);
  });
  if (!n) $('#myRooms').insertAdjacentHTML('beforeend', '<span class="muted small">Введите размеры ниже</span>');
}
$('#furnOn').onchange = e => setFurniture(e.target.checked);

// Перестраивать «Мою комнату» при вводе размеров — не чаще раза в 0,4 с
let myTimer;
function refreshMyRoom() {
  if (state.view !== 'my') return;
  clearTimeout(myTimer);
  myTimer = setTimeout(() => showMyRoom(Math.min(state.myRoom, state.rooms.length - 1)), 400);
}

// ================= Стены, мебель, свет =================
function buttons(box, items, onPick, first, render) {
  box.innerHTML = '';
  for (const [id, it] of items) {
    const b = document.createElement('button');
    render(b, it);
    b.classList.toggle('on', id === first);
    b.onclick = () => { box.querySelectorAll('button').forEach(x => x.classList.remove('on')); b.classList.add('on'); onPick(id); };
    box.appendChild(b);
  }
}
buttons($('#walls'), WALLS.map(w => [w.id, w]), setWall, 'milk',
  (b, w) => { b.className = 'swatch' + (w.pattern ? ' pat-' + w.pattern : ''); b.style.background = w.color; b.title = w.name; b.setAttribute('aria-label', w.name); });
buttons($('#themes'), Object.entries(THEMES), setTheme, 'wood', (b, t) => b.textContent = t.name);

// Окно: стена и место вдоль стены
function syncWindowUI() {
  const [wall, pos] = getWindow();
  $$('#winWall button').forEach(b => b.classList.toggle('on', b.dataset.w === wall));
  $('#winPos').value = pos * 100;
  $('#winPosRow').hidden = wall === 'none';
}
$$('#winWall button').forEach(b => b.onclick = () => { setWindow(b.dataset.w); syncWindowUI(); });
let winTimer;
$('#winPos').oninput = e => {
  clearTimeout(winTimer); // перестраиваем не чаще 10 раз в секунду
  winTimer = setTimeout(() => setWindow(getWindow()[0], e.target.value / 100), 100);
};

// Ползунок «Свет»: слева тёплый, справа холодный
const applyLight = () => {
  const b = $('#bright').value / 100, w = -$('#lwarm').value / 100;
  setLight(b, w);
  if (photoReady) setPhotoLight(b, w);
};
$('#bright').oninput = $('#lwarm').oninput = applyLight;
// Плавный переход к «День» / «Вечер»
function animateLight(b, w) {
  const b0 = +$('#bright').value, w0 = +$('#lwarm').value, t0 = performance.now();
  const step = t => {
    const k = Math.min(1, (t - t0) / 600);
    $('#bright').value = b0 + (b - b0) * k;
    $('#lwarm').value = w0 + (w - w0) * k;
    applyLight();
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
$('#day').onclick = () => animateLight(85, 30);   // днём — чуть холоднее
$('#evening').onclick = () => animateLight(30, -80); // вечером — тёплые лампы

// ================= Расчёт =================
let lastResult = null;

function changed() {
  if (state.shared) { state.number = calcNumber(); state.shared = false; }
  update();
  refreshMyRoom();
}

function update() {
  document.querySelectorAll('.room').forEach((el, i) => {
    const r = state.rooms[i], n = roomNums(r);
    if (!r) return;
    el.querySelector('.room-area').textContent = n ? 'Площадь ' + rub(n.length * n.width) + ' м²' : '';
    el.querySelector('.len').classList.toggle('err', r.length !== '' && !(parseNum(r.length) > 0));
    el.querySelector('.wid').classList.toggle('err', r.width !== '' && !(parseNum(r.width) > 0));
  });

  const rooms = state.rooms.map(roomNums);
  const d = catalog && current();
  lastResult = null;
  if (!d || rooms.some(r => !r)) {
    $('#total').textContent = '—';
    $('#calcInfo').textContent = 'Введите длину и ширину каждой комнаты';
    $('#lines').innerHTML = '';
    return;
  }

  const decor = { ...d, price_m2: decorPrice(d) };
  const underlayItem = catalog.underlay.find(u => u.id === S.underlay) || catalog.underlay[0];
  const skirtingItem = catalog.skirting.find(u => u.id === S.skirting) || catalog.skirting[0];
  const underlay = state.use.underlay && underlayItem ? underlayItem : null;
  let skirting = state.use.skirting && skirtingItem ? { ...skirtingItem } : null;
  if (skirting && !state.use.accessories) skirting.needs_accessories = false;
  const waste = { straight: S.waste.straight / 100, diagonal: S.waste.diagonal / 100 };

  const res = calculate(rooms, decor, underlay, skirting, waste);
  lastResult = { res, decor, underlay, skirting };
  $('#total').textContent = rub(res.total);
  $('#calcInfo').textContent = `Расчёт № ${state.number} · площадь ${rub(res.area)} м²`;

  // Строки. Снятые галочкой — серым, чтобы можно было вернуть
  const lines = res.lines.slice();
  if (!state.use.underlay && underlayItem) lines.push({ key: 'underlay', off: true });
  if (!state.use.skirting && skirtingItem) lines.push({ key: 'skirting', off: true });
  if (skirtingItem?.needs_accessories && (!state.use.accessories || !state.use.skirting)) lines.push({ key: 'accessories', off: true });

  $('#lines').innerHTML = '';
  for (const l of lines) {
    const li = document.createElement('li');
    const toggle = l.key === 'laminate' ? null : (l.key === 'corners' || l.key === 'caps' ? 'accessories' : l.key);
    if (toggle && l.key !== 'caps' && !VIEWER) {
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = !l.off;
      cb.disabled = toggle === 'accessories' && !state.use.skirting;
      cb.onchange = () => { state.use[toggle] = cb.checked; changed(); };
      li.appendChild(cb);
    } else if (toggle && !VIEWER) {
      li.appendChild(Object.assign(document.createElement('span'), { style: 'width:24px' }));
    }
    const name = document.createElement('span');
    name.className = 'name';
    if (l.off) {
      if (VIEWER) continue;
      name.textContent = l.key === 'accessories' ? 'Уголки и заглушки' : NAMES[l.key];
      li.classList.add('off');
      li.appendChild(name);
    } else {
      name.innerHTML = `<b>${NAMES[l.key]}</b><br><span class="muted small">${esc(lineDetail(l, decor, underlay, skirting))}</span>`;
      li.appendChild(name);
      li.appendChild(Object.assign(document.createElement('span'), { className: 'sum', textContent: rub(l.sum) }));
    }
    $('#lines').appendChild(li);
  }
}

function lineDetail(l, decor, underlay, skirting) {
  let s = `${l.qty} ${l.unit}`;
  if (l.key === 'laminate') s += ` (${rub(l.m2)} м²) · ${decor.name} ${decor.id}`;
  if (l.key === 'underlay') s += ` · ${underlay.name}`;
  if (l.key === 'skirting') s += ` (нужно ${rub(l.len)} м) · ${skirting.name}`;
  return s;
}

// ================= Отправка =================
// Все параметры расчёта — в адресе ссылки, сервер не нужен
function shareUrl() {
  const p = new URLSearchParams();
  p.set('d', state.decorId);
  p.set('pm', decorPrice(current()));
  p.set('r', state.rooms.map(r => [parseNum(r.length), parseNum(r.width), r.doors, r.diagonal ? 1 : 0, r.type].join(',')).join(';'));
  p.set('u', [state.use.underlay, state.use.skirting, state.use.accessories].map(Number).join(''));
  if (lastResult?.underlay) p.set('ul', lastResult.underlay.id);
  if (lastResult?.skirting) p.set('sk', lastResult.skirting.id);
  p.set('w', S.waste.straight + ',' + S.waste.diagonal);
  p.set('n', state.number);
  if (state.view.startsWith('photo:')) p.set('v', state.view.slice(6));
  if (S.name) p.set('pn', S.name);
  if (S.phone) p.set('pp', S.phone);
  return location.origin + location.pathname + '?' + p.toString();
}

function shareText() {
  const { res, decor, underlay, skirting } = lastResult;
  const out = [`Расчёт пола № ${state.number}`, `Ламинат EGGER: ${decor.name} (${decor.id})`,
    `Площадь: ${rub(res.area)} м²`, ''];
  for (const l of res.lines) out.push(`${NAMES[l.key]}: ${lineDetail(l, decor, underlay, skirting)} — ${rub(l.sum)} руб.`);
  out.push('', `ИТОГО: ${rub(res.total)} руб.`, `Цены магазина «Материк» на ${$('#updated').textContent}.`);
  if (S.name || S.phone) out.push(`Консультант EGGER: ${[S.name, S.phone].filter(Boolean).join(', ')}`);
  out.push('', 'Посмотреть расчёт и пол в комнате:', shareUrl());
  return out.join('\n');
}

// Запись в журнал (для «Итогов»). Один номер — одна запись
function logCalc() {
  if (!lastResult || LOG.some(x => x.n === state.number)) return;
  LOG.push({ t: Date.now(), n: state.number, d: state.decorId, a: +lastResult.res.area.toFixed(2), s: lastResult.res.total, b: false });
  if (LOG.length > 2000) LOG = LOG.slice(-2000);
  saveLog();
}

function needResult() {
  if (lastResult) return true;
  alert('Сначала введите размеры комнаты');
  return false;
}

$('#share').onclick = async () => {
  if (!needResult()) return;
  const text = shareText();
  logCalc(); state.shared = true;
  if (navigator.share) {
    try { await navigator.share({ title: 'Расчёт пола ' + state.number, text }); } catch (e) { /* закрыли меню */ }
  } else {
    copyText(text);
  }
};
$('#copy').onclick = () => { if (needResult()) { copyText(shareText()); logCalc(); state.shared = true; } };
function copyText(text) {
  const ok = () => toast('Текст скопирован — вставьте его в Viber или Telegram');
  if (navigator.clipboard) navigator.clipboard.writeText(text).then(ok, () => fallbackCopy(text, ok));
  else fallbackCopy(text, ok);
}
function fallbackCopy(text, ok) {
  const t = document.createElement('textarea');
  t.value = text; document.body.appendChild(t); t.select();
  try { document.execCommand('copy'); ok(); } catch (e) { alert(text); }
  t.remove();
}
$('#qr').onclick = () => {
  if (!needResult()) return;
  logCalc(); state.shared = true;
  const q = qrcode(0, 'M');
  q.addData(shareUrl(), 'Byte');
  q.make();
  $('#qrBox').innerHTML = q.createSvgTag({ cellSize: 6, margin: 2, scalable: true });
  $('#qrDlg').showModal();
};

function toast(msg) {
  const t = Object.assign(document.createElement('div'), { className: 'toast', textContent: msg });
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 2500);
}

// ================= Меню промоутера =================
// Вход: долгое нажатие на логотип (0,8 с) + PIN
let pressTimer;
$('#logo').addEventListener('pointerdown', () => { pressTimer = setTimeout(askPin, 800); });
['pointerup', 'pointerleave', 'pointercancel'].forEach(e => $('#logo').addEventListener(e, () => clearTimeout(pressTimer)));
$('#logo').addEventListener('contextmenu', e => e.preventDefault());

function askPin() {
  if (VIEWER) return;
  const first = !S.pin;
  $('#pinMsg').textContent = first ? 'Придумайте PIN из 4 цифр' : 'Введите PIN';
  $('#pinInp').value = '';
  $('#pinDlg').showModal();
  $('#pinInp').focus();
  $('#pinOk').onclick = () => {
    const v = $('#pinInp').value.trim();
    if (!/^\d{4}$/.test(v)) { $('#pinMsg').textContent = 'Нужно ровно 4 цифры'; return; }
    if (first) { S.pin = v; saveSettings(); }
    else if (v !== S.pin) { $('#pinMsg').textContent = 'Неверный PIN'; $('#pinInp').value = ''; return; }
    $('#pinDlg').close();
    openPromo();
  };
}
$('#pinCancel').onclick = () => $('#pinDlg').close();
$('#pinInp').onkeydown = e => { if (e.key === 'Enter') $('#pinOk').click(); };
$('#pinReset').onclick = () => { S.pin = null; saveSettings(); $('#promo').hidden = true; askPin(); };

function openPromo() {
  $('#promo').hidden = false;
  document.body.style.overflow = 'hidden';
  $('#hideOut').checked = S.hideOut;
  $('#setUnderlay').innerHTML = catalog.underlay.map(u => `<option value="${u.id}">${esc(u.name)} — ${rub(u.price)} руб.</option>`).join('');
  $('#setUnderlay').value = S.underlay || catalog.underlay[0]?.id;
  $('#setSkirting').innerHTML = catalog.skirting.map(u => `<option value="${u.id}">${esc(u.name)} — ${rub(u.price)} руб.</option>`).join('');
  $('#setSkirting').value = S.skirting || catalog.skirting[0]?.id;
  $('#wasteS').value = S.waste.straight;
  $('#wasteD').value = S.waste.diagonal;
  $('#setRoom').innerHTML = [...PHOTOS.map(p => ['photo:' + p.id, '📷 ' + p.title]), ...Object.entries(PRESETS).map(([k, p]) => [k, p.name + ' 3D'])]
    .map(([k, n]) => `<option value="${k}">${n}</option>`).join('');
  $('#setRoom').value = S.defaultRoom;
  $('#pName').value = S.name;
  $('#pPhone').value = S.phone;
  renderDecorAdmin();
  renderStats();
}
$('#promoClose').onclick = () => {
  $('#promo').hidden = true;
  document.body.style.overflow = '';
  renderFilters(); renderRibbon(); changed();
};

// Сохраняем сразу при изменении
$('#hideOut').onchange = e => { S.hideOut = e.target.checked; saveSettings(); renderDecorAdmin(); };
$('#setUnderlay').onchange = e => { S.underlay = e.target.value; saveSettings(); };
$('#setSkirting').onchange = e => { S.skirting = e.target.value; saveSettings(); };
$('#wasteS').onchange = e => { const v = parseNum(e.target.value); if (v >= 0 && v < 50) S.waste.straight = v; e.target.value = S.waste.straight; saveSettings(); };
$('#wasteD').onchange = e => { const v = parseNum(e.target.value); if (v >= 0 && v < 50) S.waste.diagonal = v; e.target.value = S.waste.diagonal; saveSettings(); };
$('#setRoom').onchange = e => { S.defaultRoom = e.target.value; saveSettings(); };
$('#pName').oninput = e => { S.name = e.target.value.trim(); saveSettings(); };
$('#pPhone').oninput = e => { S.phone = e.target.value.trim(); saveSettings(); };

// Список декоров: вкл/выкл, порядок, значок, цена, по умолчанию
function orderedAll() {
  const pos = id => { const i = S.order.indexOf(id); return i < 0 ? 1e6 + catalog.decors.findIndex(d => d.id === id) : i; };
  return catalog.decors.slice().sort((a, b) => pos(a.id) - pos(b.id));
}
function renderDecorAdmin() {
  const box = $('#decorAdmin');
  box.innerHTML = '';
  const all = orderedAll();
  S.order = all.map(d => d.id);
  all.forEach((d, i) => {
    const cfg = S.decors[d.id] || (S.decors[d.id] = {});
    const row = document.createElement('div');
    const hidden = S.hideOut && !d.in_stock;
    row.className = 'adm' + (cfg.off || hidden ? ' off' : '');
    row.innerHTML = `
      <input type="checkbox" class="on" ${cfg.off ? '' : 'checked'} title="Показывать">
      <span class="sw" style="${swatchStyle(d)}"></span>
      <div class="adm-name"><b>${esc(d.name)}</b><span class="muted small">${d.id} · ${d.in_stock ? 'в наличии' : 'нет в наличии'}${hidden ? ' (скрыт)' : ''}</span>
        <div class="adm-ctl">
          <select class="bdg"><option value="">без значка</option>${Object.entries(BADGES).map(([k, v]) => `<option value="${k}">${v}</option>`).join('')}</select>
          <input class="pr" inputmode="decimal" placeholder="${rub(d.price_m2)}" title="Своя цена за м²">
          <button class="def ${S.defaultDecor === d.id ? 'is' : ''}" title="При открытии">●</button>
        </div>
      </div>
      <div class="arrows"><button class="up" ${i ? '' : 'disabled'}>▲</button><button class="dn" ${i < all.length - 1 ? '' : 'disabled'}>▼</button></div>`;
    row.querySelector('.bdg').value = cfg.badge || '';
    row.querySelector('.pr').value = cfg.price || '';
    row.querySelector('.on').onchange = e => { cfg.off = !e.target.checked; saveSettings(); renderDecorAdmin(); };
    row.querySelector('.bdg').onchange = e => { cfg.badge = e.target.value || undefined; saveSettings(); };
    row.querySelector('.pr').onchange = e => {
      const v = parseNum(e.target.value);
      cfg.price = v > 0 ? v : undefined; e.target.value = cfg.price || ''; saveSettings();
    };
    row.querySelector('.def').onclick = () => { S.defaultDecor = d.id; saveSettings(); renderDecorAdmin(); };
    const move = k => { const o = S.order; [o[i], o[i + k]] = [o[i + k], o[i]]; saveSettings(); renderDecorAdmin(); };
    row.querySelector('.up').onclick = () => move(-1);
    row.querySelector('.dn').onclick = () => move(1);
    box.appendChild(row);
  });
  saveSettings();
}

// Итоги за период
let statDays = 1;
$$('#statPeriod button').forEach(b => b.onclick = () => {
  $$('#statPeriod button').forEach(x => x.classList.toggle('on', x === b));
  statDays = +b.dataset.p; renderStats();
});
function renderStats() {
  const from = statDays ? new Date().setHours(0, 0, 0, 0) - (statDays - 1) * 864e5 : 0;
  const rows = LOG.filter(x => x.t >= from);
  const sum = rows.reduce((s, x) => s + x.s, 0);
  const top = {};
  rows.forEach(x => top[x.d] = (top[x.d] || 0) + 1);
  const topList = Object.entries(top).sort((a, b) => b[1] - a[1]).slice(0, 5)
    .map(([id, n]) => `${esc(catalog.decors.find(d => d.id === id)?.name || id)} (${id}) — ${n}`);
  const bought = rows.filter(x => x.b).length;
  $('#stats').innerHTML = `
    <div class="kpi"><div><b>${rows.length}</b><span>расчётов</span></div>
      <div><b>${rows.length ? rub(sum / rows.length) : '—'}</b><span>средний чек, руб.</span></div>
      <div><b>${bought}</b><span>купили</span></div></div>
    ${topList.length ? '<p class="small"><b>Чаще всего:</b><br>' + topList.join('<br>') + '</p>' : '<p class="muted small">Пока нет расчётов за период</p>'}
    <ul class="log">${rows.slice(-30).reverse().map(x => `
      <li><span>${new Date(x.t).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}
        · ${x.n} · ${x.d} · ${rub(x.a)} м² · <b>${rub(x.s)}</b></span>
        <label><input type="checkbox" data-n="${x.n}" ${x.b ? 'checked' : ''}> купил</label></li>`).join('')}</ul>`;
  $$('#stats .log input').forEach(cb => cb.onchange = () => {
    const x = LOG.find(r => r.n === cb.dataset.n);
    if (x) { x.b = cb.checked; saveLog(); renderStats(); }
  });
}

// Экспорт / импорт настроек файлом
$('#exportBtn').onclick = () => {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([JSON.stringify({ settings: S, log: LOG }, null, 1)], { type: 'application/json' }));
  a.download = 'pol-za-minutu-nastroyki.json';
  a.click();
};
$('#importBtn').onclick = () => $('#importFile').click();
$('#importFile').onchange = async e => {
  try {
    const data = JSON.parse(await e.target.files[0].text());
    if (!data.settings) throw new Error();
    S = { ...DEFAULTS, ...data.settings };
    if (Array.isArray(data.log)) LOG = data.log;
    saveSettings(); saveLog(); openPromo();
    toast('Настройки загружены');
  } catch (err) { alert('Не получилось прочитать файл настроек'); }
  e.target.value = '';
};

// ================= Режим просмотра по ссылке =================
function applyViewerParams() {
  const rooms = (params.get('r') || '').split(';').map(s => s.split(',')).filter(a => a.length >= 4)
    .map(([l, w, dr, dg, t]) => ({ length: l, width: w, doors: +dr || 0, diagonal: dg === '1', type: PRESETS[t] ? t : 'living' }));
  if (rooms.length) state.rooms = rooms;
  const u = params.get('u') || '111';
  state.use = { underlay: u[0] === '1', skirting: u[1] === '1', accessories: u[2] === '1' };
  const [ws, wd] = (params.get('w') || '').split(',').map(parseNum);
  if (ws >= 0 && wd >= 0) S.waste = { straight: ws, diagonal: wd };
  if (params.get('ul')) S.underlay = params.get('ul');
  if (params.get('sk')) S.skirting = params.get('sk');
  state.number = params.get('n') || state.number;
  state.decorId = params.get('d');
  // Цена — та, что была в расчёте у промоутера
  const pm = parseNum(params.get('pm'));
  S.decors = {}; S.hideOut = false; S.order = [];
  if (pm > 0) S.decors[state.decorId] = { price: pm };
  document.body.classList.add('viewer');
  const name = params.get('pn'), phone = params.get('pp');
  $('#viewerBar').hidden = false;
  $('#viewerBar').textContent = `Ваш расчёт № ${state.number}`;
  if (name || phone) {
    $('#contact').hidden = false;
    $('#contact').innerHTML = `Консультант EGGER: <b>${esc(name || '')}</b> `
      + (phone ? `<a href="tel:${esc(phone.replace(/[^\d+]/g, ''))}">${esc(phone)}</a>` : '');
  }
  $('#addRoom').hidden = true;
  const pv = params.get('v');
  state.view = pv && PHOTOS.some(p => p.id === pv) ? 'photo:' + pv : 'my';
}

// ================= Запуск =================
initInterior($('#scene'));
applyLight();

let PHOTOS = [];
Promise.all([
  fetch('data/catalog.json', { cache: 'no-cache' }).then(r => r.json()),
  fetch('data/photos.json', { cache: 'no-cache' }).then(r => r.json()).catch(() => []),
])
  .then(([c, photos]) => {
    PHOTOS = photos;
    catalog = c;
    $('#updated').textContent = new Date(c.updated).toLocaleDateString('ru-RU');
    preload(c.decors);
    if (VIEWER) applyViewerParams();
    else {
      const def = S.defaultRoom && (PRESETS[S.defaultRoom] || PHOTOS.some(p => 'photo:' + p.id === S.defaultRoom)) ? S.defaultRoom : null;
      state.view = def || (PHOTOS[0] ? 'photo:' + PHOTOS[0].id : 'living');
      if (PRESETS[state.view]) state.rooms[0].type = state.view;
    }
    renderRoomNav();
    showView();
    syncWindowUI();
    renderFilters();
    state.decorId = state.decorId || S.defaultDecor;
    renderRibbon();
    renderRooms();
  })
  .catch(err => {
    console.error(err);
    $('#calcInfo').textContent = 'Не удалось загрузить каталог (data/catalog.json)';
  });

// Работа без интернета: сохраняем файлы сайта в телефоне
if ('serviceWorker' in navigator && location.protocol === 'https:') {
  navigator.serviceWorker.register('sw.js').catch(() => {});
}
