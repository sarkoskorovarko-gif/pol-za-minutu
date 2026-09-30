// Интерфейс: комнаты → расчёт. Формулы — в calc.js.

const WASTE = { straight: 0.07, diagonal: 0.15 }; // позже — из меню промоутера
const NAMES = { laminate: 'Ламинат', underlay: 'Подложка', skirting: 'Плинтус',
                corners: 'Уголки внутренние', caps: 'Заглушки' };

let catalog = null;
const state = {
  rooms: [{ length: '', width: '', doors: 1, diagonal: false }],
  use: { underlay: true, skirting: true, accessories: true }, // галочки сопутствующих
  number: calcNumber(),
};

const $ = s => document.querySelector(s);
const rub = x => x.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

// ---------- Комнаты ----------
function renderRooms() {
  const box = $('#rooms');
  box.innerHTML = '';
  state.rooms.forEach((r, i) => {
    const el = $('#roomTpl').content.firstElementChild.cloneNode(true);
    el.querySelector('.room-title').textContent = 'Комната ' + (i + 1);
    el.querySelector('.del').hidden = state.rooms.length === 1;
    const len = el.querySelector('.len'), wid = el.querySelector('.wid');
    len.value = r.length; wid.value = r.width;
    len.oninput = () => { r.length = len.value; update(); };
    wid.oninput = () => { r.width = wid.value; update(); };
    el.querySelector('.doors').textContent = r.doors;
    el.querySelector('.minus').onclick = () => { r.doors = Math.max(0, r.doors - 1); renderRooms(); };
    el.querySelector('.plus').onclick = () => { r.doors = Math.min(9, r.doors + 1); renderRooms(); };
    el.querySelectorAll('.lay').forEach(b => {
      b.classList.toggle('on', (b.dataset.d === '1') === r.diagonal);
      b.onclick = () => { r.diagonal = b.dataset.d === '1'; renderRooms(); };
    });
    el.querySelector('.del').onclick = () => { state.rooms.splice(i, 1); renderRooms(); };
    box.appendChild(el);
  });
  update();
}

// Размеры введены правильно? Возвращает комнату в числах или null
function roomNums(r) {
  const l = parseNum(r.length), w = parseNum(r.width);
  if (!(l > 0 && l < 100 && w > 0 && w < 100)) return null;
  return { length: l, width: w, doors: r.doors, diagonal: r.diagonal };
}

// ---------- Расчёт ----------
function update() {
  // Площадь под каждой комнатой и подсветка ошибок
  document.querySelectorAll('.room').forEach((el, i) => {
    const r = state.rooms[i], n = roomNums(r);
    el.querySelector('.room-area').textContent = n ? 'Площадь ' + rub(n.length * n.width) + ' м²' : '';
    el.querySelector('.len').classList.toggle('err', r.length !== '' && !(parseNum(r.length) > 0));
    el.querySelector('.wid').classList.toggle('err', r.width !== '' && !(parseNum(r.width) > 0));
  });

  const rooms = state.rooms.map(roomNums);
  if (!catalog || rooms.some(r => !r)) {
    $('#total').textContent = '—';
    $('#calcInfo').textContent = 'Введите длину и ширину каждой комнаты';
    $('#lines').innerHTML = '';
    return;
  }

  const decor = catalog.decors.find(d => d.id === $('#decor').value);
  const underlay = state.use.underlay ? catalog.underlay[0] : null;
  let skirting = state.use.skirting ? { ...catalog.skirting[0] } : null;
  if (skirting && !state.use.accessories) skirting.needs_accessories = false;

  const res = calculate(rooms, decor, underlay, skirting, WASTE);
  $('#total').textContent = rub(res.total);
  $('#calcInfo').textContent = `Расчёт № ${state.number} · площадь ${rub(res.area)} м²`;

  // Строки расчёта. Снятые галочкой позиции остаются видны серым
  const lines = res.lines.slice();
  const ghost = (key, q) => lines.push({ key, off: true, qty: q });
  if (!state.use.underlay) ghost('underlay');
  if (!state.use.skirting) ghost('skirting');
  if (catalog.skirting[0].needs_accessories && (!state.use.accessories || !state.use.skirting)) ghost('accessories');

  $('#lines').innerHTML = '';
  for (const l of lines) {
    const li = document.createElement('li');
    const toggle = l.key === 'laminate' ? null : (l.key === 'corners' || l.key === 'caps' ? 'accessories' : l.key);
    // Для уголков одна галочка на обе строки (уголки + заглушки)
    const showBox = toggle && !(l.key === 'caps');
    if (showBox) {
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = !l.off;
      cb.disabled = toggle === 'accessories' && !state.use.skirting;
      cb.onchange = () => { state.use[toggle] = cb.checked; update(); };
      li.appendChild(cb);
    } else if (toggle) {
      li.appendChild(Object.assign(document.createElement('span'), { style: 'width:24px' }));
    }
    const name = document.createElement('span');
    name.className = 'name';
    if (l.off) {
      name.textContent = l.key === 'accessories' ? 'Уголки и заглушки' : NAMES[l.key];
      li.classList.add('off');
    } else {
      let detail = `${l.qty} ${l.unit}`;
      if (l.key === 'laminate') detail += ` (${rub(l.m2)} м²) · ${decor.name} ${decor.id}`;
      if (l.key === 'underlay') detail += ` · ${underlay.name}`;
      if (l.key === 'skirting') detail += ` (нужно ${rub(l.len)} м) · ${skirting.name}`;
      name.innerHTML = `<b>${NAMES[l.key]}</b><br><span class="muted small">${detail}</span>`;
      li.appendChild(name);
      li.appendChild(Object.assign(document.createElement('span'), { className: 'sum', textContent: rub(l.sum) }));
      $('#lines').appendChild(li);
      continue;
    }
    li.appendChild(name);
    $('#lines').appendChild(li);
  }
}

// ---------- Запуск ----------
$('#addRoom').onclick = () => {
  state.rooms.push({ length: '', width: '', doors: 1, diagonal: false });
  renderRooms();
  document.querySelectorAll('.len')[state.rooms.length - 1].focus();
};
// Смена декора: пересчёт и пол в интерьере
function decorChanged() {
  window.currentDecor = catalog.decors.find(d => d.id === $('#decor').value);
  if (window.onDecorChange) window.onDecorChange(window.currentDecor);
  update();
}
$('#decor').onchange = decorChanged;

fetch('data/catalog.json')
  .then(r => r.json())
  .then(c => {
    catalog = c;
    $('#updated').textContent = new Date(c.updated).toLocaleDateString('ru-RU');
    $('#decor').innerHTML = c.decors
      .map(d => `<option value="${d.id}">${d.name} (${d.id}) — ${rub(d.price_m2)} руб/м²</option>`).join('');
    window.catalogLoaded = c;
    if (window.onCatalog) window.onCatalog(c);
    decorChanged();
    renderRooms();
  })
  .catch(() => { $('#calcInfo').textContent = 'Не удалось загрузить каталог (data/catalog.json)'; });

renderRooms();
