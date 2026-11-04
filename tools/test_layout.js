// Проверка раскладки по ТЗ: node tools/test_layout.js
const { bestLayout } = require('../layout.js');
let bad = 0;
const ok = (c, m) => { if (!c) { bad++; console.log('ОШИБКА', m); } };

const rooms = [[4000, 3000], [5200, 3400]];
const boards = [[1292, 193], [1380, 159]];
const table = [];

for (const [L, W] of rooms) for (const [bl, bw] of boards)
  for (const dir of ['long', 'cross']) for (const scheme of ['deck', 'half', 'third']) {
    const tag = `${L}×${W} ${bl} ${dir}/${scheme}`;
    const t = bestLayout({ L, W, boardLen: bl, boardW: bw, dir, scheme });
    ok(t && t.rows && t.rows.length, `${tag}: нет результата`);
    if (!t || !t.rows) continue;
    const step = scheme === 'half' ? 2 : 3;

    // ряд: сумма кусков = run; не-целые куски не в середине; куски ≥ minPiece
    t.rows.forEach((row, r) => {
      const sum = row.pieces.reduce((s, p) => s + p.len, 0);
      ok(Math.abs(sum - t.run) <= 0.5, `${tag} ряд ${r}: сумма ${sum} ≠ run ${t.run}`);
      ok(row.pieces.every(p => p.src !== 'full' || p.end !== 'start' || p === row.pieces[0]),
        `${tag} ряд ${r}: целая доска с end=start не первая`);
      ok(row.pieces.every(p => p.len >= 300 - 1e-6), `${tag} ряд ${r}: кусок < 300`);
      const joints = []; let x = 0;
      row.pieces.slice(0, -1).forEach(p => { x += p.len; joints.push(x); });
      row.joints = joints;
      // заводские торцы: spare/cut только на краях ряда
      ok(row.pieces.every((p, i) =>
        p.src === 'full' || i === 0 || i === row.pieces.length - 1),
        `${tag} ряд ${r}: не-целый кусок в середине ряда`);
    });

    // deck: швы соседних рядов ≥ minShift (deviated не проверяем, их ≤ 1/3)
    if (scheme === 'deck') {
      let dev = 0;
      for (let r = 1; r < t.rows.length; r++) {
        if (t.rows[r].deviated || t.rows[r - 1].deviated) { dev++; continue; }
        const okShift = t.rows[r].joints.every(a =>
          t.rows[r - 1].joints.every(b => Math.abs(a - b) >= 300 - 1e-6));
        ok(okShift, `${tag} ряд ${r}: шов ближе 300 мм к прошлому ряду`);
      }
      ok(dev <= t.rows.length / 3, `${tag}: deviated больше трети рядов`);
    }

    // half/third: первый кусок по циклу с учётом s0; deviated ≤ 1/3.
    // Остаток нужной длины в начале ряда допустим (Claude: экономия, схема та же)
    if (scheme !== 'deck') {
      // цикл относительный: начало ряда i = s0 − фаза·доска (по модулю длины доски)
      const ph = i => scheme === 'half' ? (i % 2) / 2 : (i % 3) / 3;
      const m = x => { const v = ((x % bl) + bl) % bl; return v < 0.5 ? bl : v; };
      const clean = t.rows.filter(r => !r.deviated);
      ok(t.rows.length - clean.length <= Math.ceil(t.rows.length / 3), `${tag}: много отступлений`);
      for (const r of clean) {
        const want = Math.min(m(t.s0 - ph(r.i) * bl - r.u0), t.run);
        ok(Math.abs(r.pieces[0].len - want) <= 1, `${tag} ряд ${r.i}: первый кусок ${r.pieces[0].len}, по циклу ${want.toFixed(1)}`);
      }
    }

    const min = Math.ceil(t.run * t.across / (bl * bw));
    ok(t.boards >= min, `${tag}: досок ${t.boards} < нижней границы ${min}`);
    table.push([`${L}×${W}`, bl, dir, scheme, t.boards, min].join('  '));
  }

console.log('\nкомната      доска  dir    scheme  boards  нижняя граница');
table.forEach(r => console.log(r));

// Диагональ (тесты — Kimi)
// Диагональ: повёрнутая комната, у каждого ряда свои u0/len, короткие куски у углов — с warn
for (const [L, W] of rooms) for (const [bl, bw] of boards)
  for (const scheme of ['deck', 'half', 'third']) {
    const tag = `${L}×${W} ${bl} diag/${scheme}`;
    const t = bestLayout({ L, W, boardLen: bl, boardW: bw, dir: 'diag', scheme });
    ok(t && t.rows && t.rows.length, `${tag}: нет результата`);
    if (!t || !t.rows) continue;
    let prevJ = null;
    t.rows.forEach((r, i) => {
      const sum = r.pieces.reduce((s, p) => s + p.len, 0);
      ok(Math.abs(sum - r.len) <= 0.5, `${tag} ряд ${i}: сумма ${sum} ≠ len ${r.len}`);
      ok(r.pieces.every((p, j) => p.src === 'full' || j === 0 || j === r.pieces.length - 1),
        `${tag} ряд ${i}: не-целый кусок в середине`);
      ok(r.pieces.every(p => p.len >= 300 - 1e-6 || r.warn),
        `${tag} ряд ${i}: кусок < 300 без предупреждения`);
      const joints = []; let x = 0;
      r.pieces.slice(0, -1).forEach(p => { x += p.len; joints.push(r.u0 + x); });
      if (scheme === 'deck' && prevJ && !r.warn && joints.length)
        ok(joints.every(a => prevJ.every(b => Math.abs(a - b) >= 300 - 1e-6)),
          `${tag} ряд ${i}: шов ближе 300 мм к прошлому ряду`);
      if (!r.warn) prevJ = joints;
    });
    ok(t.boards >= t.lower, `${tag}: досок ${t.boards} < нижней границы ${t.lower}`);
    console.log(`${tag}: ${t.boards} досок (нижняя граница ${t.lower}), рядов ${t.rows.length}, с предупреждением ${t.warnings.length}`);
  }
console.log(bad ? `ошибок: ${bad}` : 'всё верно');
