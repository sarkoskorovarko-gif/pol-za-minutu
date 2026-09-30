// Расчёт материалов по SPEC, раздел 5.1 D. Только формулы, без интерфейса,
// чтобы их можно было проверить отдельно (tools/test_calc.js).

const DOOR_WIDTH_M = 0.9;   // ширина проёма, который не нужен плинтус
const UNDERLAY_EXTRA = 0.05; // запас подложки 5%
const SKIRTING_EXTRA = 0.05; // запас плинтуса 5%

// Число с запятой или точкой → число (или NaN)
function parseNum(s) {
  return parseFloat(String(s).replace(',', '.').trim());
}

// Округление денег до копеек
function money(x) {
  return Math.round(x * 100) / 100;
}

/**
 * rooms: [{ length, width, doors, diagonal }]
 * decor: { price_m2, pack_m2 }
 * underlay: { price, pack_m2 } или null (снята галочка)
 * skirting: { price, length_m, needs_accessories, corner_price, cap_price } или null
 * waste: { straight: 0.07, diagonal: 0.15 }
 */
function calculate(rooms, decor, underlay, skirting, waste) {
  let area = 0, areaWithWaste = 0, skirtingLen = 0, corners = 0, caps = 0;

  for (const r of rooms) {
    const s = r.length * r.width;
    area += s;
    // Ламинат считаем по каждой комнате со своим запасом, потом суммируем
    areaWithWaste += s * (1 + (r.diagonal ? waste.diagonal : waste.straight));
    // Плинтус: периметр минус двери, плюс 5%
    const len = 2 * (r.length + r.width) - DOOR_WIDTH_M * r.doors;
    skirtingLen += Math.max(0, len) * (1 + SKIRTING_EXTRA);
    corners += 4;          // прямоугольная комната — 4 внутренних угла
    caps += 2 * r.doors;   // 2 заглушки у каждой двери
  }

  const res = { area, areaWithWaste, lines: [] };

  const packs = Math.ceil(areaWithWaste / decor.pack_m2 - 1e-9);
  const lamSum = money(packs * decor.pack_m2 * decor.price_m2);
  res.lines.push({ key: 'laminate', qty: packs, unit: 'уп.', m2: money(packs * decor.pack_m2), sum: lamSum });

  if (underlay) {
    const n = Math.ceil(area * (1 + UNDERLAY_EXTRA) / underlay.pack_m2 - 1e-9);
    res.lines.push({ key: 'underlay', qty: n, unit: 'уп.', sum: money(n * underlay.price) });
  }

  if (skirting) {
    const n = Math.ceil(skirtingLen / skirting.length_m - 1e-9);
    res.lines.push({ key: 'skirting', qty: n, unit: 'шт.', len: money(skirtingLen), sum: money(n * skirting.price) });
    if (skirting.needs_accessories) {
      res.lines.push({ key: 'corners', qty: corners, unit: 'шт.', sum: money(corners * skirting.corner_price) });
      res.lines.push({ key: 'caps', qty: caps, unit: 'шт.', sum: money(caps * skirting.cap_price) });
    }
  }

  res.total = money(res.lines.reduce((t, l) => t + l.sum, 0));
  return res;
}

// Короткий номер расчёта, например A-0417
function calcNumber() {
  const letter = 'ABCEHKMPT'[Math.floor(Math.random() * 9)]; // латиница, как в SPEC
  return letter + '-' + String(Math.floor(Math.random() * 10000)).padStart(4, '0');
}

if (typeof module !== 'undefined') module.exports = { calculate, parseNum, calcNumber, money };
