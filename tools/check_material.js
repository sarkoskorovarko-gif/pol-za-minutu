// Независимая проверка материала раскладки: node tools/check_material.js
// Не доверяет движку: пересчитывает по полю board у каждого куска.
const { bestLayout } = require('../layout.js');
let checked = 0, bad = 0, table = [];
const err = m => { bad++; console.log('ОШИБКА', m); };

const rooms = [[3000, 2500], [4000, 3000], [5200, 3400], [6100, 2900]];
const boards = [[1292, 193], [1380, 159], [1200, 190]];
for (const [L, W] of rooms) for (const [bl, bw] of boards)
  for (const dir of ['long', 'cross', 'diag']) for (const scheme of ['deck', 'half', 'third']) {
    const tag = `${L}×${W} ${bl} ${dir}/${scheme}`;
    const p = bestLayout({ L, W, boardLen: bl, boardW: bw, dir, scheme });
    checked++;
    if (!p) { err(`${tag}: нет плана`); continue; }
    // (6) сумма кусков ряда = длина ряда
    p.rows.forEach(r => {
      const sum = r.pieces.reduce((s, q) => s + q.len, 0);
      if (Math.abs(sum - r.len) > 0.5) err(`${tag} ряд ${r.i}: сумма ${sum} ≠ ${r.len}`);
    });
    // куски по доскам
    const byBoard = new Map();
    p.rows.forEach(r => r.pieces.forEach(q => {
      if (!byBoard.has(q.board)) byBoard.set(q.board, []);
      byBoard.get(q.board).push({ ...q, row: r.i });
    }));
    // (1) номера досок
    const ids = [...byBoard.keys()].sort((a, b) => a - b);
    if (ids.length !== p.boards) err(`${tag}: досок по кускам ${ids.length} ≠ ${p.boards}`);
    if (ids[0] !== 1 || ids[ids.length - 1] !== ids.length) err(`${tag}: номера досок не 1..N`);
    for (const [id, pcs] of byBoard) {
      // (2) сумма кусков + пропилы ≤ длины доски
      const cuts = pcs.length - 1;
      const sum = pcs.reduce((s, q) => s + q.len, 0);
      if (sum + cuts * 3 > bl + 0.5) err(`${tag} доска ${id}: ${sum} + ${cuts}×3 > ${bl}`);
      // (3) не больше 2 кусков и правильные торцы
      if (pcs.length > 2) err(`${tag} доска ${id}: ${pcs.length} кусков`);
      const ends = pcs.map(q => q.end);
      const sr = ends.filter(e => e === 'start' || e === 'only').length;
      const er = ends.filter(e => e === 'end').length;
      // один кусок — любой (целая, или подрезанная, а остаток в отход); два — правая часть в начало, левая в конец
      if (pcs.length === 2 && !(sr === 1 && er === 1))
        err(`${tag} доска ${id}: торцы ${ends.join(',')}`);
      // (4) mid — целая доска
      for (const q of pcs) if (q.end === 'mid' && (q.src !== 'full' || Math.abs(q.len - bl) > 0.5))
        err(`${tag} доска ${id}: mid не целая`);
      // (5) остаток использован позже, чем кусок, при резке которого он получился
      if (pcs.length === 2) {
        const [a, b] = pcs;
        // в том же ряду можно, если остаток лежит дальше по ряду, чем отрезанный кусок (Claude)
        const cutP = a.src === 'spare' ? b : a, spare = a.src === 'spare' ? a : b;
        if (spare.row === cutP.row && spare.x <= cutP.x)
          err(`${tag} доска ${id}: остаток раньше реза в том же ряду`);
        if (a.src === 'spare' && b.src === 'spare')
          err(`${tag} доска ${id}: оба куска из остатков`);
      }
      for (const q of pcs) if (q.src === 'spare' && pcs.some(o => o !== q && o.src !== 'spare' && o.row > q.row))
        err(`${tag} доска ${id}: остаток раньше реза`);
    }
    // (7) площадь
    const area = p.boards * bl * bw / 1e6;
    const room = p.room ? p.room.a * p.room.b / 1e6 : (p.run + 2 * p.gap) * (p.across + 2 * p.gap) / 1e6;
    if (area < room - 1e-6) err(`${tag}: досок на ${area.toFixed(2)} м² < комнаты ${room.toFixed(2)} м²`);
    table.push(`${tag}: ${p.boards} (граница ${p.lower})`);
  }
console.log(`проверено планов: ${checked}, ошибок: ${bad}`);
table.forEach(r => console.log(r));
process.exit(bad ? 1 : 0);
