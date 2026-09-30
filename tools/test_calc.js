// Проверка формул на тестовых комнатах. Запуск: node tools/test_calc.js
// Ожидаемые числа посчитаны вручную (расписано в комментариях).
const { calculate } = require('../calc.js');

const decor = { price_m2: 22.66, pack_m2: 1.99 };               // EPL038
const underlay = { price: 15, pack_m2: 10 };                      // ТЕСТ
const skirting = { price: 8.5, length_m: 2.5, needs_accessories: true, corner_price: 1.2, cap_price: 0.9 };
const waste = { straight: 0.07, diagonal: 0.15 };

const tests = [
  {
    // 5×4, 1 дверь, прямо. S=20, с запасом 21.4 → 21.4/1.99=10.75 → 11 уп = 21.89 м² × 22.66 = 496.03
    // подложка 21/10 → 3 уп = 45; плинтус (18−0.9)×1.05=17.955/2.5 → 8 шт = 68
    // уголки 4 = 4.80; заглушки 2 = 1.80. Итого 615.63
    name: 'Гостиная 5×4, прямо',
    rooms: [{ length: 5, width: 4, doors: 1, diagonal: false }],
    expect: { packs: 11, underlay: 3, skirting: 8, corners: 4, caps: 2, total: 615.63 },
  },
  {
    // 4×3.5, 1 дверь, диагональ. S=14 ×1.15=16.1/1.99=8.09 → 9 уп = 17.91 м² × 22.66 = 405.84
    // подложка 14.7/10 → 2 = 30; плинтус (15−0.9)×1.05=14.805/2.5 → 6 = 51; 4.80 + 1.80. Итого 493.44
    name: 'Спальня 4×3,5, по диагонали',
    rooms: [{ length: 4, width: 3.5, doors: 1, diagonal: true }],
    expect: { packs: 9, underlay: 2, skirting: 6, corners: 4, caps: 2, total: 493.44 },
  },
  {
    // 4×3 (1 дверь) + 4×1.5 (2 двери), прямо. S=18 ×1.07=19.26/1.99=9.68 → 10 уп = 19.9 × 22.66 = 450.93
    // подложка 18.9/10 → 2 = 30; плинтус (13.1+9.2)×1.05=23.415/2.5 → 10 = 85
    // уголки 8 = 9.60; заглушки 6 = 5.40. Итого 580.93
    name: 'Две комнаты: 4×3 + коридор 4×1,5',
    rooms: [{ length: 4, width: 3, doors: 1, diagonal: false },
            { length: 4, width: 1.5, doors: 2, diagonal: false }],
    expect: { packs: 10, underlay: 2, skirting: 10, corners: 8, caps: 6, total: 580.93 },
  },
];

let fails = 0;
for (const t of tests) {
  const r = calculate(t.rooms, decor, underlay, skirting, waste);
  const q = k => r.lines.find(l => l.key === k)?.qty;
  const got = { packs: q('laminate'), underlay: q('underlay'), skirting: q('skirting'),
                corners: q('corners'), caps: q('caps'), total: r.total };
  const ok = JSON.stringify(got) === JSON.stringify(t.expect);
  if (!ok) fails++;
  console.log((ok ? 'OK    ' : 'ОШИБКА') + ' ' + t.name + ' → итого ' + r.total + ' руб.');
  if (!ok) console.log('   ждали', t.expect, '\n   вышло', got);
}
console.log(fails ? `\nОшибок: ${fails}` : '\nВсе расчёты совпали с ручными.');
process.exit(fails ? 1 : 0);
